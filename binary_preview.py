"""Binary developer preview: a sealed release set and later source association.

content/release.json stays the source-release record and keeps its own
validation (release_docs.py). A binary-only preview has no source commit, its
public tag may differ from the media's release id, and its QUICKSTART.md is
served exactly as sealed: it is checked against the record, the manifest and
SHA256SUMS, never re-rendered. Standard library only.

    content/binary-preview.json                 the selected record
    content/binary-preview/<tag>/MANIFEST.toml  sealed inputs, byte for byte
    content/binary-preview/<tag>/SHA256SUMS
    content/binary-preview/<tag>/QUICKSTART.md
"""
import hashlib
import json
import pathlib
import re
import tomllib

import release_docs

SCHEMA = "absd-binary-preview/1"
FIELDS = {"schema", "repository", "tag", "release_id", "kernel_commit", "platform_commit", "release_date",
          "state", "signature", "qualification", "evidence", "assets", "sums_sha256", "limitations",
          "works", "not_in_preview", "first_party_source"}
CORRECTION = {
    "name": "absd-rc1-third-party-notices-correction-1.tar.gz",
    "url": "https://github.com/unpingable/absd/releases/download/absd-preview-rc1/absd-rc1-third-party-notices-correction-1.tar.gz",
    "sha256": "4c3096ab9a4a7a41b39bdf382c57f471ad30c2fdcd5439b315b9674552667c4a",
    "bytes": 64836,
}
STATES = ("draft", "published", "withdrawn")
REPOSITORY = "https://github.com/unpingable/absd"
ASSET_BASE = REPOSITORY + "/releases/download/"
HARDWARE_LIMIT = "Physical hardware qualification is not yet established."
INPUTS = ("MANIFEST.toml", "SHA256SUMS", "QUICKSTART.md")
REQUIRED = ("MANIFEST.toml", "QUICKSTART.md", "NOTICES.md", "absd-try.py")
ROLES = (("operator_iso", "operator.iso"), ("enroll_iso", "enroll.iso"), ("disk", "disk.img.xz"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def record_path(root):
    return pathlib.Path(root) / "content" / "binary-preview.json"


def input_dir(root, record):
    return pathlib.Path(root) / "content" / "binary-preview" / record["tag"]


def base(record):
    return ASSET_BASE + record["tag"] + "/"


def statements(record, field):
    value = record[field]
    if not isinstance(value, list) or not value or any(not isinstance(s, str) or not s.strip() for s in value):
        raise ValueError(f"binary-only preview: {field} requires a nonempty list of statements")
    return value


def check_record(record, source_release_id):
    if not isinstance(record, dict) or set(record) - {"notices_correction"} != FIELDS or record["schema"] != SCHEMA:
        raise ValueError(f"binary-only preview: expected {SCHEMA} and its exact fields")
    if "releases/latest" in json.dumps(record):
        raise ValueError("binary-only preview: releases/latest is never a canonical address")
    if record["repository"] != REPOSITORY:
        raise ValueError("binary-only preview: repository must be the public source repository")
    # Both names stay in the native helper's domain; they may differ.
    for name in ("tag", "release_id"):
        if not isinstance(record[name], str) or not re.fullmatch(r"[a-z0-9.-]{1,64}", record[name]):
            raise ValueError(f"binary-only preview: malformed {name}")
    if record["tag"] == source_release_id:
        raise ValueError("binary-only preview: tag must not name the source release")
    for name in ("kernel_commit", "platform_commit"):
        if not isinstance(record[name], str) or not re.fullmatch(r"[0-9a-f]{40}", record[name]):
            raise ValueError(f"binary-only preview: malformed {name}")
    if not isinstance(record["release_date"], str) or not re.fullmatch(r"20\d\d-[01]\d-[0-3]\d", record["release_date"]):
        raise ValueError("binary-only preview: malformed release_date")
    if record["state"] not in STATES:
        raise ValueError(f"binary-only preview: state must be one of {', '.join(STATES)}")
    if record["signature"] != "unsigned":
        raise ValueError("binary-only preview: v0 owner decision is an explicitly unsigned preview")
    source = record["first_party_source"]
    if source is not None:
        fields = {"tag", "commit", "tree", "source_manifest_sha256", "kernel_commit", "platform_commit"}
        if not isinstance(source, dict) or set(source) != fields:
            raise ValueError("binary-only preview: malformed first_party_source")
        if (not isinstance(source["tag"], str) or not re.fullmatch(r"[a-z0-9.-]{1,64}", source["tag"])
                or source["tag"] in (record["tag"], source_release_id)):
            raise ValueError("binary-only preview: source association needs a separate source tag")
        for name in ("commit", "tree", "kernel_commit", "platform_commit"):
            if not isinstance(source[name], str) or not re.fullmatch(r"[0-9a-f]{40}", source[name]):
                raise ValueError(f"binary-only preview: malformed source {name}")
        if not isinstance(source["source_manifest_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", source["source_manifest_sha256"]):
            raise ValueError("binary-only preview: malformed source manifest digest")
        if any(source[name] != record[name] for name in ("kernel_commit", "platform_commit")):
            raise ValueError("binary-only preview: source components disagree with binary record")
    level = record["qualification"]
    if level not in release_docs.QUALIFICATIONS:
        raise ValueError("binary-only preview: unknown qualification")
    evidence = record["evidence"]
    if not isinstance(evidence, list) or any(
            not isinstance(e, dict) or set(e) != {"level", "label", "url"}
            or e["level"] not in release_docs.QUALIFICATIONS
            or not all(isinstance(v, str) and v.strip() for v in e.values())
            or not (e["url"].startswith("https://") or (e["url"].startswith("/") and not e["url"].startswith("//")))
            for e in evidence):
        raise ValueError("binary-only preview: malformed evidence entry")
    if level != "built" and level not in {e["level"] for e in evidence}:
        raise ValueError(f"binary-only preview: qualification {level} has no evidence entry of that level")
    reached = release_docs.QUALIFICATIONS.index(level) >= release_docs.QUALIFICATIONS.index("published")
    if record["state"] == "published" and not reached:
        raise ValueError("binary-only preview: published state requires the published qualification/evidence level")
    if record["state"] == "draft" and reached:
        raise ValueError("binary-only preview: a draft record cannot claim publication")
    if HARDWARE_LIMIT not in statements(record, "limitations"):
        raise ValueError("binary-only preview: the physical hardware limitation must remain")
    statements(record, "works")
    statements(record, "not_in_preview")
    if not re.fullmatch(r"[0-9a-f]{64}", str(record["sums_sha256"])):
        raise ValueError("binary-only preview: malformed sums_sha256")
    assets = record["assets"]
    if not isinstance(assets, list) or not assets or len(assets) > 1000:
        raise ValueError("binary-only preview: assets required")
    names = set()
    for a in assets:
        if not isinstance(a, dict) or set(a) != {"name", "url", "sha256", "bytes"}:
            raise ValueError("binary-only preview: malformed asset")
        name = a["name"]
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", name)
                or name in (".", "..", "SHA256SUMS", "SHA256SUMS.sig") or name in names):
            raise ValueError(f"binary-only preview: malformed or repeated asset name {name!r}")
        if a["url"] != base(record) + name:
            raise ValueError(f"binary-only preview: {name} is not at its tagged release address")
        if not isinstance(a["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", a["sha256"]):
            raise ValueError(f"binary-only preview: malformed sha256 for {name}")
        if type(a["bytes"]) is not int or not 0 < a["bytes"] < 2**31:
            raise ValueError(f"binary-only preview: {name} bytes must be positive and under 2 GiB")
        names.add(name)
    for name in REQUIRED:
        if name not in names:
            raise ValueError(f"binary-only preview: missing release asset {name}")
    # A later addition is separate from the sealed asset set. Setting this
    # requires owner publication authority and verified remote bytes; this
    # offline check only validates the one reviewed correction's identity.
    correction = record.get("notices_correction")
    if correction is not None and (not isinstance(correction, dict)
                                   or type(correction.get("bytes")) is not int
                                   or record["tag"] != "absd-preview-rc1" or correction != CORRECTION):
        raise ValueError("binary-only preview: notices_correction differs from the reviewed RC1 addition")


def check_manifest(record, data):
    doc = tomllib.loads(data.decode("utf-8"))
    if doc.get("schema") != "absd-preview-manifest/1":
        raise ValueError("binary-only preview: expected absd-preview-manifest/1")
    release = doc.get("release", {})
    if "source_commit" in release:
        raise ValueError("binary-only preview: manifest binds a source commit; use the source-release path")
    expected = {"id": record["release_id"], "tag": record["tag"],
                "kernel_commit": record["kernel_commit"], "platform_commit": record["platform_commit"]}
    if set(release) != set(expected):
        raise ValueError("binary-only preview: manifest release table has unexpected keys")
    for key, value in expected.items():
        if release[key] != value:
            raise ValueError(f"binary-only preview: manifest release.{key} disagrees with record")
    if doc.get("signature") != record["signature"]:
        raise ValueError("binary-only preview: manifest signature disagrees with record")
    order = release_docs.QUALIFICATIONS
    if doc.get("qualification") not in order or order.index(doc["qualification"]) > order.index(record["qualification"]):
        raise ValueError("binary-only preview: manifest qualification exceeds record")
    limits = doc.get("limitations")
    if (not isinstance(limits, list) or HARDWARE_LIMIT not in limits
            or any(s not in record["limitations"] for s in limits)):
        raise ValueError("binary-only preview: every sealed manifest limitation must remain in the record")
    expected_qemu = {"cpu_tcg": release_docs.CPU, "memory_mib": 256, "smp": 1,
                     "nic": "e1000", "disk": "ide", "firmware": "SeaBIOS"}
    qemu = doc.get("qemu", {})
    if qemu != expected_qemu or any(type(qemu[k]) is not type(v) for k, v in expected_qemu.items()):
        raise ValueError("binary-only preview: unsupported or contradictory QEMU profile")
    roles = doc.get("assets", {})
    if not isinstance(roles, dict) or any(r not in roles for r, _ in ROLES):
        raise ValueError("binary-only preview: manifest requires operator, enrollment and disk assets")
    for role, suffix in ROLES:
        if roles[role].get("name") != f"{record['release_id']}-{suffix}":
            raise ValueError(f"binary-only preview: unexpected filename for {role}")
    assets = {a["name"]: a for a in record["assets"]}
    seen = set()
    for role, entry in roles.items():
        if not isinstance(entry, dict) or entry.get("name") in seen:
            raise ValueError("binary-only preview: malformed or repeated manifest asset")
        name = entry.get("name")
        if name not in assets or any(entry.get(k) != assets[name][k] for k in ("sha256", "bytes")):
            raise ValueError(f"binary-only preview: manifest asset {role} disagrees with record")
        seen.add(name)
    if seen != set(assets) - {"MANIFEST.toml"}:
        raise ValueError("binary-only preview: manifest must bind every asset except itself")
    disk = roles["disk"]
    if (not re.fullmatch(r"[0-9a-f]{64}", str(disk.get("raw_sha256", "")))
            or type(disk.get("raw_bytes")) is not int or disk["raw_bytes"] <= 0 or disk["raw_bytes"] % 512):
        raise ValueError("binary-only preview: malformed decompressed disk identity")
    return doc


def check_guide(record, guide):
    """Reference checks only: the sealed guide must download this record's
    files from this tag and verify them. It is not regenerated or compared
    with a template, so sections appended before sealing are kept."""
    text = guide.decode("utf-8")
    for url in [a["url"] for a in record["assets"]] + [base(record) + "SHA256SUMS"]:
        if f"curl --fail --location --remote-name {url}\n" not in text:
            raise ValueError(f"binary-only preview: QUICKSTART.md does not download {url}")
    if len(set(re.findall(r"https://github\.com/unpingable/absd/releases/download/([^/\s]+)/", text))) != 1:
        raise ValueError("binary-only preview: QUICKSTART.md names another release tag")
    for line in ("sha256sum -c SHA256SUMS\n", "python3 absd-try.py verify .\n"):
        if line not in text:
            raise ValueError(f"binary-only preview: QUICKSTART.md lacks {line.strip()!r}")


def regular(directory, name):
    path = pathlib.Path(directory) / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"binary-only preview: expected regular input {name}")
    return path.read_bytes()


def verify(record, directory, source_release_id):
    """Every check, against the committed inputs. Returns {name: bytes}."""
    check_record(record, source_release_id)
    directory = pathlib.Path(directory)
    if sorted(p.name for p in directory.iterdir()) != sorted(INPUTS):
        raise ValueError("binary-only preview: input directory must hold exactly " + ", ".join(INPUTS))
    files = {name: regular(directory, name) for name in INPUTS}
    assets = {a["name"]: a for a in record["assets"]}
    if digest(files["SHA256SUMS"]) != record["sums_sha256"]:
        raise ValueError("binary-only preview: SHA256SUMS bytes disagree with record")
    sums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
        if not m or m.group(2) in sums:
            raise ValueError(f"binary-only preview: malformed or repeated SHA256SUMS line {line!r}")
        sums[m.group(2)] = m.group(1)
    if sums != {n: a["sha256"] for n, a in assets.items()}:
        raise ValueError("binary-only preview: SHA256SUMS and record assets disagree")
    for name in ("MANIFEST.toml", "QUICKSTART.md"):
        if digest(files[name]) != assets[name]["sha256"] or len(files[name]) != assets[name]["bytes"]:
            raise ValueError(f"binary-only preview: {name} bytes disagree with record and SHA256SUMS")
    check_manifest(record, files["MANIFEST.toml"])
    check_guide(record, files["QUICKSTART.md"])
    return files


def load(root, source_release_id):
    """The selected binary-only record and its verified inputs, or None."""
    path = record_path(root)
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    check_record(record, source_release_id)
    files = verify(record, input_dir(root, record), source_release_id)
    return record, files
