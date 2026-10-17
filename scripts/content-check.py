#!/usr/bin/env python3
"""Bounded release-contract cases, including a disposable hypothetical update."""
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("absd_build", ROOT / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

with tempfile.TemporaryDirectory(prefix="absd-content-") as directory:
    fixture = pathlib.Path(directory) / "release.json"
    record = dict(build.RELEASE)
    # The loader adds binary_preview=None in memory for a schema 1 record;
    # the file has no such field, so fixtures built from `record` must not either.
    assert record.pop("binary_preview") is None
    for field, value in (("qualification", "unknown"), ("release_commit", "short"),
                         ("release_date", "2026-02-30"), ("schema_version", True),
                         ("qualification", "qualified")):
        changed = dict(record, **{field: value})
        fixture.write_text(json.dumps(changed))
        try:
            build.load_release(fixture)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid {field}")
    copy = pathlib.Path(directory) / "site-source"
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "site", "__pycache__"))
    subprocess.run(["python3", "build.py"], cwd=copy, check=True)
    # The live record has no binary preview: schema 1, no download page, no link.
    assert record["schema_version"] == 1 and "binary_preview" not in json.loads((ROOT / "content/release.json").read_text())
    assert not (copy / "site/try").exists(), "live record built a download page"
    assert 'href="/try/"' not in (copy / "site/index.html").read_text()
    print("content-check: binary-preview absent-live PASS")
    homepage = copy / "site/index.html"
    homepage.write_text(homepage.read_text().replace(record["release_id"], "wrong-release"))
    mutated = subprocess.run(["python3", "scripts/check.py"], cwd=copy, capture_output=True, text=True)
    assert mutated.returncode != 0 and "snippet differs" in mutated.stdout
    subprocess.run(["python3", "build.py"], cwd=copy, check=True)
    record_path = copy / "content/release.json"
    changed = dict(record, release_id="absd-preview-hypothetical", release_date="2026-10-11")
    changed["evidence"] = [{"label": v["label"], "url": v["url"].replace(record["release_id"], changed["release_id"])} for v in record["evidence"]]
    changed["preview_summary"] = "Hypothetical preview: QEMU smoke only; suites scheduled after 2026-11-01."
    changed["preview_details"] = "Hypothetical exact revisions built and booted; qualification remains pending until 2026-11-01."
    changed["standing"] = "Hypothetical public preview status update."
    changed["editorial_updated"] = "2026-10-12"
    changed["demonstrated"] = ["Hypothetical demonstration with bounded QEMU scope."]
    changed["limitations"] = ["Hypothetical limit; no physical hardware qualification."]
    record_path.write_text(json.dumps(changed, indent=2) + "\n")
    stale = subprocess.run(["python3", "scripts/check.py"], cwd=copy, capture_output=True, text=True)
    assert stale.returncode != 0 and "stale" in stale.stdout, stale.stdout + stale.stderr
    subprocess.run(["python3", "build.py"], cwd=copy, check=True)
    subprocess.run(["python3", "scripts/check.py"], cwd=copy, check=True)
    for page in ("index.html", "status/index.html"):
        text = (copy / "site" / page).read_text()
        assert "absd-preview-hypothetical" in text
        assert record["release_id"] not in text
        assert "absd-20261003.1" in text
        assert "QEMU" in text
        assert changed["standing"] in text and changed["editorial_updated"] in text
        assert changed["demonstrated"][0] in text and changed["limitations"][0] in text
    assert "Physical hardware qualification: not yet established" in (copy / "site/status/index.html").read_text()
    status = (copy / "site/status/index.html").read_text()
    assert changed["preview_summary"] in status and changed["preview_details"] in status
    assert "2026-10-17" not in status.split('<h3 id="source-run">')[0]
    qualified = dict(changed, qualification="qualified", standing="Hypothetical core qualification recorded.", kernel_suite_result="fixture kernel PASS",
                     core_profile_result="fixture core PASS extended=NOT_RUN", qualification_record="hypothetical receipt")
    record_path.write_text(json.dumps(qualified))
    subprocess.run(["python3", "build.py"], cwd=copy, check=True)
    subprocess.run(["python3", "scripts/check.py"], cwd=copy, check=True)
    text = (copy / "site/status/index.html").read_text()
    assert "fixture kernel PASS" in text and "fixture core PASS extended=NOT_RUN" in text
    assert "Physical hardware qualification: not yet established" in text

    # Binary preview (absd-coord #31/#32): a synthetic record, every refusal by name.
    import hashlib
    tag = record["release_id"]
    base = build.ASSET_BASE + tag + "/"
    names = [f"absd-{tag}-operator.iso", f"absd-{tag}-enroll.iso", f"absd-{tag}-disk.img.xz", "absd-try.py",
             "MANIFEST.toml", "QUICKSTART.md", "NOTICES.md"]
    digest = {n: hashlib.sha256(n.encode()).hexdigest() for n in names}

    def synthetic():
        return {
            "tag": tag,
            "assets": [{"name": n, "url": base + n, "sha256": digest[n], "bytes": 1000 + i} for i, n in enumerate(names)],
            "manifest_url": base + "MANIFEST.toml", "sums_url": base + "SHA256SUMS",
            "sums": [f"{digest[n]}  {n}" for n in names], "signature": "unsigned",
            "qemu_profile": "x86-64, one CPU, e1000 user network, IDE disk",
            "host_tiers": ["Linux x86-64 with KVM", "Linux x86-64 without KVM (TCG)"],
            "qualification": "offline-boot-tested",
            "evidence": [{"level": "offline-boot-tested", "label": "Offline boot receipt", "url": "/evidence/"}],
            "quickstart_url": f"{record['repository']}/blob/{tag}/QUICKSTART.md",
            "limitations": [build.HARDWARE_LIMIT, "Developer preview for QEMU only."],
            "documentation": {"state": "draft", "manual_sha256": "0" * 64},
        }

    def bad(name, change, expect):
        preview = synthetic()
        change(preview)
        fixture.write_text(json.dumps(dict(record, schema_version=2, binary_preview=preview)))
        try:
            build.load_release(fixture)
        except ValueError as error:
            assert expect in str(error), (name, str(error))
            print(f"content-check: binary-preview {name} REFUSED ({error})")
        else:
            raise AssertionError(f"binary preview accepted: {name}")

    def asset(p, n):
        return next(a for a in p["assets"] if a["name"] == n)

    bad("tag-mismatch", lambda p: p.update(tag="absd-preview-other"), "tag differs from release_id")
    bad("url-not-pinned", lambda p: asset(p, "absd-try.py").update(url=build.ASSET_BASE + "absd-preview-other/absd-try.py"),
        "not at its tagged release address")
    bad("releases-latest", lambda p: p.update(manifest_url="https://github.com/unpingable/absd/releases/latest/download/MANIFEST.toml"),
        "releases/latest")
    bad("digest-differs-from-sums", lambda p: asset(p, "absd-try.py").update(sha256="0" * 64), "digest differs from the record's SHA256SUMS")
    bad("asset-absent-from-sums", lambda p: p["sums"].pop(), "digest differs from the record's SHA256SUMS")
    bad("sums-lists-extra-file", lambda p: p["sums"].append("1" * 64 + "  extra.bin"), "lists files that are not assets")
    bad("malformed-sha256", lambda p: asset(p, "absd-try.py").update(sha256=digest["absd-try.py"].upper()), "malformed sha256")
    bad("malformed-sums-line", lambda p: p["sums"].__setitem__(0, "not a sums line"), "malformed sums line")
    bad("bytes-zero", lambda p: asset(p, "absd-try.py").update(bytes=0), "malformed bytes")
    bad("asset-over-size-limit", lambda p: asset(p, "absd-try.py").update(bytes=2**31), "under 2 GiB")
    bad("sums-url-wrong", lambda p: p.update(sums_url=base + "SUMS"), "sums_url is not the tagged SHA256SUMS")
    bad("quickstart-not-at-tag", lambda p: p.update(quickstart_url=base + "QUICKSTART.md"),
        "quickstart_url is not QUICKSTART.md at the tag")
    bad("duplicate-sums-line", lambda p: p["sums"].append(p["sums"][0]), "lists absd-")
    bad("dotdot-asset-name", lambda p: p["assets"].append({"name": "..", "url": base + "..", "sha256": "2" * 64, "bytes": 1}),
        "malformed asset name")
    bad("duplicate-asset", lambda p: p["assets"].append(dict(p["assets"][0])), "listed twice")
    sig = {"name": "SHA256SUMS.sig", "url": base + "SHA256SUMS.sig", "sha256": "3" * 64, "bytes": 300}
    bad("sig-when-unsigned", lambda p: p["assets"].append(dict(sig)), "listed but the record says unsigned")
    verify = "ssh-keygen -Y verify -f allowed_signers -I release@absd.dev -n file -s SHA256SUMS.sig"
    bad("signed-without-sig", lambda p: p.update(signature=verify), "must list SHA256SUMS.sig")
    signed = synthetic()
    signed.update(signature=verify)
    signed["assets"].append(dict(sig))
    fixture.write_text(json.dumps(dict(record, schema_version=2, binary_preview=signed)))
    assert build.load_release(fixture, check_documentation=False)["binary_preview"]["signature"] == verify
    print("content-check: binary-preview signed-with-sig PASS")
    for name, doc, expect in (("schema2-without-preview", dict(record, schema_version=2, binary_preview=None),
                               "schema 2 requires a binary preview"),
                              ("schema1-with-field", dict(record, binary_preview=None), "exact fields")):
        fixture.write_text(json.dumps(doc))
        try:
            build.load_release(fixture)
        except ValueError as error:
            assert expect in str(error), (name, str(error))
            print(f"content-check: binary-preview {name} REFUSED ({error})")
        else:
            raise AssertionError(f"accepted: {name}")
    bad("qualification-unknown", lambda p: p.update(qualification="validated"), "qualification must be one of")
    bad("qualification-without-evidence", lambda p: p.update(qualification="published"), "has no evidence entry of that level")
    bad("limitations-missing", lambda p: p.update(limitations=[]), "limitations requires")
    bad("hardware-limit-removed", lambda p: p.update(limitations=["Developer preview for QEMU only."]), "physical hardware limitation")
    bad("signature-malformed", lambda p: p.update(signature="gpg --verify SHA256SUMS.asc"), "signature must be")

    # Positive: the synthetic record builds a pinned /try/ page that the checker accepts.
    preview_copy = pathlib.Path(directory) / "preview-source"
    shutil.copytree(ROOT, preview_copy, ignore=shutil.ignore_patterns(".git", "site", "__pycache__"))
    sys.path.insert(0, str(ROOT / "scripts"))
    from test_release_docs import fixture as documentation_fixture
    preview_record, source, assets = documentation_fixture(pathlib.Path(directory) / "preview-inputs", tag)
    build.release_docs.stage(preview_record, preview_copy, assets, source)
    (preview_copy / "content/release.json").write_text(json.dumps(preview_record, indent=2) + "\n")
    subprocess.run(["python3", "build.py"], cwd=preview_copy, check=True, capture_output=True)
    subprocess.run(["python3", "scripts/check.py"], cwd=preview_copy, check=True, capture_output=True)
    page = (preview_copy / "site/try/index.html").read_text()
    for item in preview_record["binary_preview"]["assets"]:
        assert item["url"] in page and item["sha256"] in page, item["name"]
    assert 'href="/try/"' in (preview_copy / "site/index.html").read_text()
    print("content-check: binary-preview synthetic-page PASS")
    # A page whose digest no longer matches the record is refused.
    helper_digest = next(a["sha256"] for a in preview_record["binary_preview"]["assets"] if a["name"] == "absd-try.py")
    (preview_copy / "site/try/index.html").write_text(page.replace(helper_digest, "f" * 64))
    tampered = subprocess.run(["python3", "scripts/check.py"], cwd=preview_copy, capture_output=True, text=True)
    assert tampered.returncode != 0 and "binary preview value missing" in tampered.stdout, tampered.stdout
    print("content-check: binary-preview tampered-page REFUSED")
    subprocess.run(["python3", "build.py"], cwd=preview_copy, check=True, capture_output=True)
    guide = preview_copy / 'site/releases' / tag / 'QUICKSTART.md'
    guide.write_text(guide.read_text().replace('--accel tcg', '--accel kvm'))
    drift = subprocess.run(['python3', 'scripts/check.py'], cwd=preview_copy, capture_output=True, text=True)
    assert drift.returncode != 0 and 'release documentation differs' in drift.stdout, drift.stdout+drift.stderr
    print('content-check: contradictory-generated-instructions REFUSED')

    # Switch releases through the actual command. Both manuals and pinned
    # old artifact URLs must remain, while /try/ selects only the new one.
    next_record, next_source, next_assets = documentation_fixture(pathlib.Path(directory) / 'next-inputs', 'absd-preview-next-fixture')
    build.release_docs.stage(next_record, preview_copy, next_assets, next_source)
    next_path = pathlib.Path(directory) / 'next-record.json'
    next_path.write_text(json.dumps(next_record))
    subprocess.run(['python3', 'scripts/release-docs.py', 'select', '--record', str(next_path)], cwd=preview_copy, check=True, capture_output=True)
    subprocess.run(['python3', 'build.py'], cwd=preview_copy, check=True, capture_output=True)
    final_check = subprocess.run(['python3', 'scripts/check.py'], cwd=preview_copy, capture_output=True, text=True)
    assert final_check.returncode == 0, final_check.stdout+final_check.stderr
    assert (preview_copy/'site/releases'/tag/'manual/index.html').exists()
    assert (preview_copy/'site/releases/absd-preview-next-fixture/manual/index.html').exists()
    assert base+'operator.iso' in (preview_copy/'site/releases'/tag/'index.html').read_text()
    assert 'absd-preview-next-fixture' in (preview_copy/'site/try/index.html').read_text()
    print('content-check: release-switch-history-and-manuals PASS')

    # Later editorial evidence and withdrawal must not change the sealed
    # source guide. No source tag, artifact or manual is rewritten.
    next_record['binary_preview']['documentation']['state'] = 'withdrawn'
    next_record['binary_preview']['limitations'].append('Withdrawn fixture; retained for history.')
    next_path.write_text(json.dumps(next_record))
    subprocess.run(['python3', 'scripts/release-docs.py', 'select', '--record', str(next_path)], cwd=preview_copy, check=True, capture_output=True)
    subprocess.run(['python3', 'build.py'], cwd=preview_copy, check=True, capture_output=True)
    final_check = subprocess.run(['python3', 'scripts/check.py'], cwd=preview_copy, capture_output=True, text=True)
    assert final_check.returncode == 0, final_check.stdout+final_check.stderr
    assert '<strong>withdrawn</strong>' in (preview_copy/'site/try/index.html').read_text()
    print('content-check: withdrawal-without-retargeting PASS')
print("content-check: invalid records, stale build, hypothetical preview/qualified updates, binary preview cases passed; fixtures removed")
