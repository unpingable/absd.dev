"""Release-bound documentation inputs and rendering. Standard library only.

content/release.json remains the editorial record. Its binary metadata is
checked against the preview producer's MANIFEST.toml and SHA256SUMS. The
installed-release reconstruction manifest is a different input and is refused.
"""
import hashlib
import json
import pathlib
import re
import shlex
import subprocess
import tomllib

PROFILE = "QEMU 8.2, x86-64, TCG, one CPU, 256 MiB minimum, SeaBIOS, e1000, primary IDE disk"
CPU = "max,vendor=GenuineIntel,+rdrand"
HOSTS = ["Linux x86-64 with QEMU 8.2 TCG"]
STATES = ("draft", "staged", "published", "withdrawn")
QUALIFICATIONS = ("built", "offline-boot-tested", "qualified", "release-authorized", "published", "outsider-passed")
DOC_FIELDS = {"state", "manual_sha256"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def release_dir(root, record):
    tag = record["release_id"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", tag):
        raise ValueError("documentation: malformed release id")
    return pathlib.Path(root) / "content" / "releases" / tag


def file_bytes(directory, name):
    path = pathlib.Path(directory) / name
    if pathlib.PurePath(name).name != name or name in (".", "..") or path.is_symlink() or not path.is_file():
        raise ValueError(f"documentation: expected regular input {name}")
    return path.read_bytes()


def manifest(record, data):
    doc = tomllib.loads(data.decode("utf-8"))
    if doc.get("schema") != "absd-preview-manifest/1":
        raise ValueError("documentation: expected absd-preview-manifest/1, not an installed-release manifest")
    expected = {"id": record["release_id"], "tag": record["release_id"],
                "source_commit": record["release_commit"], "kernel_commit": record["kernel_commit"],
                "platform_commit": record["platform_commit"]}
    for key, value in expected.items():
        if doc.get("release", {}).get(key) != value:
            raise ValueError(f"documentation: manifest release.{key} disagrees with release record")
    preview = record["binary_preview"]
    if doc.get("signature") != preview["signature"]:
        raise ValueError("documentation: manifest signature disagrees with release record")
    level = doc.get("qualification")
    current = preview["qualification"]
    if (level not in QUALIFICATIONS or current not in QUALIFICATIONS
            or QUALIFICATIONS.index(level) > QUALIFICATIONS.index(current)):
        raise ValueError("documentation: manifest qualification exceeds release record")
    limits = doc.get("limitations")
    if (not isinstance(limits, list) or not limits or any(not isinstance(s, str) or not s.strip() for s in limits)
            or "Physical hardware qualification is not yet established." not in limits
            or any(s not in preview["limitations"] for s in limits)):
        raise ValueError("documentation: frozen manifest limitations must remain in release record")
    # This is the existing absd-try launcher profile, not a new configurable
    # launcher. Other profiles need their own implementation and rehearsal.
    qemu = doc.get("qemu", {})
    expected_qemu = {"cpu_tcg": CPU, "memory_mib": 256, "smp": 1,
                     "nic": "e1000", "disk": "ide", "firmware": "SeaBIOS"}
    if (qemu != expected_qemu or any(type(qemu.get(k)) is not type(v) for k, v in expected_qemu.items())
            or preview["qemu_profile"] != PROFILE):
        raise ValueError("documentation: unsupported or contradictory QEMU profile")
    if preview['host_tiers'] != HOSTS:
        raise ValueError('documentation: unsupported or contradictory host profile')
    assets = {a["name"]: a for a in preview["assets"]}
    roles = doc.get("assets", {})
    if not isinstance(roles, dict) or not {"operator_iso", "enroll_iso", "disk"} <= roles.keys():
        raise ValueError("documentation: preview requires operator, enrollment and disk assets")
    seen = set()
    for role, entry in roles.items():
        if not isinstance(entry, dict) or entry.get("name") in seen:
            raise ValueError("documentation: malformed or repeated manifest asset")
        name = entry.get("name")
        if name not in assets or any(entry.get(k) != assets[name][k] for k in ("sha256", "bytes")):
            raise ValueError(f"documentation: manifest asset {role} disagrees with release record")
        seen.add(name)
    manifest_name = preview['manifest_url'].rsplit('/', 1)[-1]
    if seen != set(assets) - {manifest_name, 'SHA256SUMS.sig'}:
        raise ValueError('documentation: manifest must bind every asset except itself and a checksum signature')
    disk = roles["disk"]
    if (not re.fullmatch(r"[0-9a-f]{64}", str(disk.get("raw_sha256", "")))
            or type(disk.get("raw_bytes")) is not int or disk["raw_bytes"] <= 0 or disk["raw_bytes"] % 512):
        raise ValueError("documentation: malformed decompressed disk identity")
    for name in ("absd-try.py", "QUICKSTART.md", "NOTICES.md"):
        if name not in assets:
            raise ValueError(f"documentation: missing release asset {name}")
    if preview["signature"] != "unsigned":
        raise ValueError("documentation: v0 owner decision is an explicitly unsigned preview")
    return doc


def manual_sums(directory):
    directory = pathlib.Path(directory)
    pages = sorted(p for p in directory.iterdir() if re.fullmatch(r"[a-z0-9.-]+\.[1-9]", p.name))
    if not pages or any(p.is_symlink() or not p.is_file() for p in pages):
        raise ValueError("documentation: manual requires regular mdoc pages")
    return "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in pages).encode()


def load(record, root):
    preview = record["binary_preview"]
    settings = preview.get("documentation")
    if (not isinstance(settings, dict) or set(settings) != DOC_FIELDS
            or settings["state"] not in STATES
            or not re.fullmatch(r"[0-9a-f]{64}", str(settings["manual_sha256"]))):
        raise ValueError("documentation: expected state and manual_sha256")
    if (settings['state'] == 'published'
            and QUALIFICATIONS.index(preview['qualification']) < QUALIFICATIONS.index('published')):
        raise ValueError('documentation: published state requires the published qualification/evidence level')
    directory = release_dir(root, record)
    name = preview["manifest_url"].rsplit("/", 1)[-1]
    data = file_bytes(directory, name)
    asset = next(a for a in preview["assets"] if a["name"] == name)
    if digest(data) != asset["sha256"] or len(data) != asset["bytes"]:
        raise ValueError("documentation: manifest bytes disagree with release record")
    doc = manifest(record, data)
    sums = file_bytes(directory, "SHA256SUMS").decode("ascii").splitlines()
    if sums != preview["sums"]:
        raise ValueError("documentation: SHA256SUMS disagrees with release record")
    source = tomllib.loads(file_bytes(directory, "SOURCE-MANIFEST.toml").decode())
    check_source(record, source, doc)
    actual = manual_sums(directory / "manual")
    if (actual != file_bytes(directory / "manual", "SHA256SUMS")
            or digest(actual) != settings["manual_sha256"]):
        raise ValueError("documentation: release manual disagrees with its pinned digest")
    return doc


def check_source(record, source, doc=None):
    if source.get("release", {}).get("id") != record["release_id"]:
        raise ValueError("documentation: source manifest release id disagrees")
    for name in ("kernel", "platform"):
        rows = [c for c in source.get("component", []) if c.get("name") == name]
        if len(rows) != 1 or rows[0].get("commit") != record[name + "_commit"]:
            raise ValueError(f"documentation: source manifest {name} commit disagrees")
    if doc is None:
        raise ValueError("documentation: source check requires the exact artifact manifest")
    expected = {"quickstart_sha256": digest(quickstart(record, doc).encode()),
                "readme_fragment_sha256": digest(readme_fragment(record, doc).encode())}
    if any(source.get("documentation", {}).get(k) != v for k, v in expected.items()):
        raise ValueError("documentation: source documentation hashes disagree with release record")


def quickstart(record, doc):
    """No asset digests or source-release commit here: this file is itself
    an asset, and may be committed in the source tag. Avoid self-reference."""
    p = record["binary_preview"]
    tag = record["release_id"]
    base = f"{record['repository']}/releases/download/{tag}/"
    downloads = "\n".join(f"curl --fail --location --remote-name {shlex.quote(a['url'])}" for a in p["assets"])
    limits = "\n".join("- " + line for line in doc["limitations"])
    return f"""# Try ABSD {tag}

Developer preview for a local Linux x86-64 host with QEMU 8.2, Python 3.11+,
OpenSSH, curl, xz and sha256sum. No Rust, Clang, GRUB or source checkout is
needed. Profile: {PROFILE}. Use TCG for this guide; KVM and other hosts are
separate qualification cases. Kernel {record['kernel_commit']}; platform
{record['platform_commit']}. Artifact standing when sealed: {doc['qualification']}.
Check https://absd.dev/releases/{tag}/ for subsequent qualification,
availability and withdrawal notices before using these files.

## Download and verify

Run in a new empty directory on your host. Every URL names this exact tag.
These files are unsigned. A checksum downloaded beside a file detects
corruption; it does not prove who produced it.

```sh
{downloads}
curl --fail --location --remote-name {base}SHA256SUMS
sha256sum -c SHA256SUMS
python3 absd-try.py verify .
```

Stop if either verification fails. Do not run an unverified helper.
Download all helper modules listed above beside absd-try.py.

## Create your machine

Generate a fresh key at a new path; keep the private file on this host.
The helper receives only its .pub file. It decompresses a fresh writable
disk and runs the release's enrollment image. The serial enrollment channel
is trusted only inside this local QEMU environment. It is not an unattended
remote enrollment service. Downloaded media carries no reusable host key or
login identity. Copies initially share the filesystem id; SSH identities are
generated for each machine.

```sh
ssh-keygen -t ed25519 -N '' -f ./absd-key
python3 absd-try.py create ./machine --assets . --key ./absd-key.pub --accel tcg
python3 absd-try.py boot ./machine --port 2222 --accel tcg
```

Leave boot running in that terminal. It records the host key from the local
VM console in machine/known_hosts and prints READY. In a second terminal in
the same directory, use that file and the exact key:

```sh
ssh -F /dev/null -p 2222 -i ./absd-key -o IdentitiesOnly=yes -o IdentityAgent=none -o ForwardAgent=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile=./machine/known_hosts operator@127.0.0.1
```

In ABSD, read the manual, exercise commands and write a file:

```text
man intro
uptime
cd /home/operator
echo release-check > release-check.txt
cat release-check.txt
shutdown
```

The helper should report HALTED cleanly. Boot the same machine again, SSH
using the same command, then run `cat /home/operator/release-check.txt` and
`shutdown`. The file should contain `release-check`. Keep machine/disk.img
for your state; do not run create again or replace it to reboot. The manual
installed in this image is for platform {record['platform_commit']}; the
site's older milestone manual describes its own earlier revision.

## Troubleshooting

- Checksum failure: stop and re-download the exact tagged files into a fresh directory.
- Enrollment refusal: read machine/enroll-console.log; use a plain ssh-ed25519 .pub file and leave the guest stopped while enrolling.
- Port 2222 busy: stop your other guest, or choose a different --port and use that same SSH port.
- No READY: inspect machine/console.log and machine/qemu.log. Use --accel tcg and the recorded files. Do not switch device models.
- Login refused: use the enrolled private key and machine/known_hosts. A changed host key requires diagnosis; do not disable verification.
- Ctrl-C stops QEMU abruptly. Use shutdown inside ABSD for the documented clean stop. Never run two guests on one writable disk.

## Limits and provenance

{limits}

This rehearsal is separate from long-running U1 qualification, release
authorization, publication and a reader's successful download from public
URLs. The release manifest, SHA256SUMS and NOTICES.md travel with the files.
"""


def readme_fragment(record, doc):
    p = record["binary_preview"]
    return f"""<!-- BEGIN ABSD RELEASE DOWNLOAD -->
## Download and try this release

Developer preview **{record['release_id']}**: [download and quickstart]({p['quickstart_url']}).
No Rust, Clang, GRUB or source checkout is needed for the binary path.
{PROFILE}. Artifact standing when sealed: **{doc['qualification']}**.
Read https://absd.dev/releases/{record['release_id']}/ for later qualification,
availability and withdrawal notices before using the files.
The preview is unsigned; checksums detect corruption and do not establish authenticity.
The manual in this release is pinned to platform `{record['platform_commit']}`.
Build-from-source instructions continue below.
<!-- END ABSD RELEASE DOWNLOAD -->
"""


def exports(record, doc):
    return {"QUICKSTART.md": quickstart(record, doc),
            "README-download.md": readme_fragment(record, doc)}


def git_bytes(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def stage(record, root, assets, source):
    """Import exact source metadata and manual, and check actual candidate
    assets before accepting their metadata. Never changes the input assets."""
    p = record["binary_preview"]
    name = p["manifest_url"].rsplit("/", 1)[-1]
    raw = file_bytes(assets, name)
    doc = manifest(record, raw)
    for a in p["assets"]:
        path = pathlib.Path(assets) / a["name"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size >= 2**31:
            raise ValueError(f"documentation: expected a regular release asset under 2 GiB: {a['name']}")
        h, size = hashlib.sha256(), 0
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
                size += len(chunk)
                if size >= 2**31:
                    raise ValueError(f"documentation: asset reached 2 GiB: {a['name']}")
        if h.hexdigest() != a["sha256"] or size != a["bytes"]:
            raise ValueError(f"documentation: asset bytes disagree: {a['name']}")
    if file_bytes(assets, "SHA256SUMS").decode("ascii").splitlines() != p["sums"]:
        raise ValueError("documentation: asset SHA256SUMS disagrees")
    if file_bytes(assets, "QUICKSTART.md") != quickstart(record, doc).encode():
        raise ValueError("documentation: QUICKSTART.md is stale; render before sealing asset digests")
    rev = record["release_commit"]
    src = git_bytes(source, "show", f"{rev}:SOURCE-MANIFEST.toml")
    check_source(record, tomllib.loads(src.decode()), doc)
    if git_bytes(source, "show", f"{rev}:QUICKSTART.md") != quickstart(record, doc).encode():
        raise ValueError("documentation: source QUICKSTART.md disagrees with release record")
    readme = git_bytes(source, "show", f"{rev}:README.md").decode()
    fragment = readme_fragment(record, doc)
    if (readme.count("<!-- BEGIN ABSD RELEASE DOWNLOAD -->") != 1
            or readme.count("<!-- END ABSD RELEASE DOWNLOAD -->") != 1 or fragment.rstrip() not in readme):
        raise ValueError("documentation: source README download section disagrees with release record")
    # Read the named commit, never a mutable worktree's manual.
    paths = git_bytes(source, "ls-tree", "-r", "--name-only", rev, "platform/man/").decode().splitlines()
    pages = {path.rsplit("/", 1)[-1]: git_bytes(source, "show", f"{rev}:{path}") for path in paths
             if re.fullmatch(r"platform/man/[a-z0-9.-]+\.[1-9]", path)}
    if not pages:
        raise ValueError("documentation: source commit has no manual")
    directory = release_dir(root, record)
    files = {name: raw, "SHA256SUMS": file_bytes(assets, "SHA256SUMS"), "SOURCE-MANIFEST.toml": src}
    files.update({"manual/" + name: data for name, data in pages.items()})
    sums = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(pages.items())).encode()
    files["manual/SHA256SUMS"] = sums
    # An existing release's inputs are immutable. Identical replay is allowed.
    for name, data in files.items():
        dest = directory / name
        if dest.exists() and (dest.is_symlink() or dest.read_bytes() != data):
            raise ValueError(f"documentation: refusing to overwrite release input {name}")
    for name, data in files.items():
        dest = directory / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(data)
    p["documentation"]["manual_sha256"] = digest(sums)
    load(record, root)
    return record
