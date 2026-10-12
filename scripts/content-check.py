#!/usr/bin/env python3
"""Bounded release-contract cases, including a disposable hypothetical update."""
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("absd_build", ROOT / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

with tempfile.TemporaryDirectory(prefix="absd-content-") as directory:
    fixture = pathlib.Path(directory) / "release.json"
    record = dict(build.RELEASE)
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
    homepage = copy / "site/index.html"
    homepage.write_text(homepage.read_text().replace(record["release_id"], "wrong-release"))
    mutated = subprocess.run(["python3", "scripts/check.py"], cwd=copy, capture_output=True, text=True)
    assert mutated.returncode != 0 and "snippet differs" in mutated.stdout
    subprocess.run(["python3", "build.py"], cwd=copy, check=True)
    record_path = copy / "content/release.json"
    changed = dict(record, release_id="absd-preview-hypothetical", release_date="2026-10-11")
    changed["evidence"] = [{"label": v["label"], "url": v["url"].replace(record["release_id"], changed["release_id"])} for v in record["evidence"]]
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
    qualified = dict(changed, qualification="qualified", standing="Hypothetical core qualification recorded.", kernel_suite_result="fixture kernel PASS",
                     core_profile_result="fixture core PASS extended=NOT_RUN", qualification_record="hypothetical receipt")
    record_path.write_text(json.dumps(qualified))
    subprocess.run(["python3", "build.py"], cwd=copy, check=True)
    subprocess.run(["python3", "scripts/check.py"], cwd=copy, check=True)
    text = (copy / "site/status/index.html").read_text()
    assert "fixture kernel PASS" in text and "fixture core PASS extended=NOT_RUN" in text
    assert "Physical hardware qualification: not yet established" in text
print("content-check: invalid records, stale build, hypothetical preview/qualified updates passed; fixture removed")
