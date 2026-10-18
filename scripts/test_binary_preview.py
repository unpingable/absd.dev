#!/usr/bin/env python3
"""The binary-only preview path against the committed RC1 inputs.

The committed record and sealed files must pass; each tampered or
contradictory copy must refuse by name; the source-release record and its
validator keep their earlier behaviour. These are metadata checks: boot, SSH
and persistence are the separate reader rehearsal's.
"""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import binary_preview as bp
import release_docs

# The reviewed final release set (rc1-release-set-20261018T191939Z).
SEALED = {"MANIFEST.toml": "71066f42b41886834af4f56b8a98973635a4b2e617d355f4c806432a35246567",
          "QUICKSTART.md": "96c18db6bc8463b686012a6d49bc74eca0b0265a11640f8e1e8fb9049cead824",
          "SHA256SUMS": "22850b3193fbe99f0623970096f14e5ff4b941e9713e676f7fe103ed59913d71"}
SOURCE_ID = json.loads((ROOT / "content/release.json").read_text())["release_id"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Inputs:
    """A writable copy of the committed record and sealed inputs."""

    def __init__(self, directory):
        self.root = pathlib.Path(directory)
        self.record = json.loads(bp.record_path(ROOT).read_text())
        self.dir = self.root / "inputs"
        shutil.copytree(bp.input_dir(ROOT, self.record), self.dir)

    def read(self, name):
        return (self.dir / name).read_bytes()

    def write(self, name, data):
        (self.dir / name).write_bytes(data)

    def asset(self, name):
        return next(a for a in self.record["assets"] if a["name"] == name)

    def reseal(self):
        """Recompute every digest from the current bytes, as a producer that
        sealed these contents consistently would: guide, manifest, sums."""
        guide = self.read("QUICKSTART.md")
        manifest = self.read("MANIFEST.toml").decode()
        old = re.search(r'name = "QUICKSTART.md"\nsha256 = "([0-9a-f]{64})"\nbytes = (\d+)', manifest)
        manifest = manifest.replace(old.group(0), f'name = "QUICKSTART.md"\nsha256 = "{sha(guide)}"\nbytes = {len(guide)}')
        self.write("MANIFEST.toml", manifest.encode())
        for name in ("QUICKSTART.md", "MANIFEST.toml"):
            data = self.read(name)
            self.asset(name).update(sha256=sha(data), bytes=len(data))
        sums = "".join(f"{a['sha256']}  {a['name']}\n" for a in self.record["assets"])
        self.write("SHA256SUMS", sums.encode())
        self.record["sums_sha256"] = sha(sums.encode())

    def verify(self):
        return bp.verify(self.record, self.dir, SOURCE_ID)


class BinaryPreview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="absd-binary-")
        self.inputs = Inputs(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def refuses(self, expect):
        with self.assertRaises(ValueError) as caught:
            self.inputs.verify()
        self.assertIn(expect, str(caught.exception))

    def test_committed_rc1_inputs_pass_and_are_the_sealed_bytes(self):
        record, files = bp.load(ROOT, SOURCE_ID)
        self.assertEqual({n: sha(d) for n, d in files.items()}, SEALED)
        self.assertNotEqual(record["tag"], record["release_id"])
        doc = tomllib.loads(files["MANIFEST.toml"].decode())
        self.assertNotIn("source_commit", doc["release"])
        self.assertEqual(record["first_party_source"], None)

    def test_tampered_quickstart_refuses(self):
        self.inputs.write("QUICKSTART.md", self.inputs.read("QUICKSTART.md") + b"\n")
        self.refuses("QUICKSTART.md bytes disagree")

    def test_consistently_resealed_guide_for_another_tag_refuses(self):
        guide = self.inputs.read("QUICKSTART.md").replace(b"/download/absd-preview-rc1/", b"/download/absd-preview-other/", 1)
        self.inputs.write("QUICKSTART.md", guide)
        self.inputs.reseal()
        self.refuses("QUICKSTART.md")

    def test_resealed_appended_section_is_served_not_rerendered(self):
        # A guide with a further appended section, sealed consistently, is
        # accepted as shipped: the path never compares it with a template.
        self.inputs.write("QUICKSTART.md", self.inputs.read("QUICKSTART.md") + b"\n## Another appended note\n\nText.\n")
        self.inputs.reseal()
        files = self.inputs.verify()
        self.assertTrue(files["QUICKSTART.md"].endswith(b"Text.\n"))

    def test_manifest_hash_mismatch_refuses(self):
        self.inputs.write("MANIFEST.toml", self.inputs.read("MANIFEST.toml").replace(b'qualification = "built"', b'qualification = "built" '))
        self.refuses("MANIFEST.toml bytes disagree")

    def test_sums_bytes_mismatch_refuses(self):
        self.inputs.write("SHA256SUMS", self.inputs.read("SHA256SUMS") + b"\n")
        self.refuses("SHA256SUMS bytes disagree")

    def test_record_asset_digest_mismatch_refuses(self):
        self.inputs.asset("absd-try.py")["sha256"] = "0" * 64
        self.refuses("SHA256SUMS and record assets disagree")

    def test_media_digest_mismatch_in_manifest_refuses(self):
        name = self.inputs.record["release_id"] + "-operator.iso"
        manifest = self.inputs.read("MANIFEST.toml").replace(self.inputs.asset(name)["sha256"].encode(), b"1" * 64)
        self.inputs.write("MANIFEST.toml", manifest)
        self.inputs.reseal()
        self.refuses("manifest asset operator_iso disagrees with record")

    def test_manifest_with_source_commit_refuses(self):
        manifest = self.inputs.read("MANIFEST.toml").replace(b'[release]\n', b'[release]\nsource_commit = "' + b"3" * 40 + b'"\n')
        self.inputs.write("MANIFEST.toml", manifest)
        self.inputs.reseal()
        self.refuses("binds a source commit")

    def test_manifest_tag_or_id_contradiction_refuses(self):
        manifest = self.inputs.read("MANIFEST.toml").replace(b'tag = "absd-preview-rc1"', b'tag = "absd-preview-rc2"')
        self.inputs.write("MANIFEST.toml", manifest)
        self.inputs.reseal()
        self.refuses("manifest release.tag disagrees")

    def test_tag_naming_the_source_release_refuses(self):
        self.inputs.record["tag"] = SOURCE_ID
        self.refuses("must not name the source release")

    def test_extra_or_linked_input_refuses(self):
        (self.inputs.dir / "extra.txt").write_text("x")
        self.refuses("exactly")
        (self.inputs.dir / "extra.txt").unlink()
        guide = self.inputs.dir / "QUICKSTART.md"
        real = self.inputs.root / "guide"
        guide.rename(real)
        guide.symlink_to(real)
        self.refuses("expected regular input QUICKSTART.md")

    def test_sealed_limitation_and_hardware_limit_must_remain(self):
        sealed = tomllib.loads(self.inputs.read("MANIFEST.toml").decode())["limitations"]
        self.inputs.record["limitations"] = [s for s in self.inputs.record["limitations"] if s != sealed[-1]]
        self.refuses("every sealed manifest limitation")
        self.inputs.record["limitations"] = [s for s in sealed if s != bp.HARDWARE_LIMIT]
        self.refuses("physical hardware limitation")

    def test_publication_claim_needs_published_level_and_evidence(self):
        record = self.inputs.record
        self.inputs.verify()
        record.update(state="published", qualification="built", evidence=[])
        self.refuses("published state requires")
        record["qualification"] = "published"
        self.refuses("has no evidence entry")
        record.update(state="draft", evidence=[{"level": "published", "label": "Release", "url": "https://example.invalid/r"}])
        self.refuses("a draft record cannot claim publication")

    def test_first_party_source_must_stay_null_and_fields_exact(self):
        self.inputs.record["first_party_source"] = "absd-preview-20261010"
        self.refuses("first_party_source must be null")
        self.inputs.record["first_party_source"] = None
        self.inputs.record["release_commit"] = "0" * 40
        self.refuses("exact fields")


class SourcePathUnchanged(unittest.TestCase):
    def test_source_record_still_validates_alone(self):
        import build
        record = build.load_release(build.RELEASE_PATH)
        self.assertIsNone(record["binary_preview"])
        self.assertEqual(record["schema_version"], 1)

    def test_source_validator_still_refuses_the_binary_only_manifest(self):
        record = json.loads(bp.record_path(ROOT).read_text())
        data = (bp.input_dir(ROOT, record) / "MANIFEST.toml").read_bytes()
        reference = json.loads((ROOT / "scripts/testdata/schema1-rendering-v1.json").read_text())
        source = json.loads(reference["release_json"])
        source.update(schema_version=2, release_id=record["release_id"], release_commit="0" * 40,
                      kernel_commit=record["kernel_commit"], platform_commit=record["platform_commit"],
                      binary_preview={"signature": "unsigned"})
        with self.assertRaises(ValueError) as caught:
            release_docs.manifest(source, data)
        self.assertIn("manifest release.tag disagrees with release record", str(caught.exception))


class BuiltSite(unittest.TestCase):
    """Build a copy, check it, then tamper with the output."""

    def test_build_serves_sealed_guide_and_check_refuses_tampering(self):
        with tempfile.TemporaryDirectory(prefix="absd-binary-site-") as directory:
            copy = pathlib.Path(directory) / "site-source"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "site", "__pycache__"))
            subprocess.run(["python3", "build.py"], cwd=copy, check=True, capture_output=True)
            ok = subprocess.run(["python3", "scripts/check.py"], cwd=copy, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            served = copy / "site/releases/absd-preview-rc1/QUICKSTART.md"
            self.assertEqual(sha(served.read_bytes()), SEALED["QUICKSTART.md"])
            page = (copy / "site/try/index.html").read_text()
            self.assertIn('href="/releases/absd-preview-rc1/QUICKSTART.md"', page)
            self.assertIn("No first-party ABSD source release accompanies", page)
            sentence = ("RC1's first-party source is not yet published, so independent parties cannot currently "
                        "reproduce its builds from the published materials.")
            self.assertIn(sentence, page)
            self.assertIn(sentence, (copy / "site/status/index.html").read_text())
            self.assertIn("absd-rc1-boot-corresponding-source.tar", page)
            self.assertIn("Standing: <strong>published</strong>. Not yet reached: outsider-passed.", page)
            self.assertNotIn(" of 6 steps", page)
            self.assertNotIn("on the ladder", page)
            self.assertIn("quoted from the release's MANIFEST.toml, written before publication", page)
            # #62: the complete set, its size from the sealed metadata, host packages, QEMU versions,
            # helper modules before verification, and why the sealed guide says "built".
            self.assertIn("Both verification commands need all 13 files", page)
            self.assertIn("(46,561,280 bytes)", page)
            self.assertIn("The complete download is 91,756,032 bytes.", page)
            self.assertIn("qemu-system-x86 python3 openssh-client curl xz-utils", page)
            self.assertIn("the helper does not check the QEMU version", page)
            self.assertLess(page.index("<code>absd_fs.py</code>"), page.index("python3 absd-try.py verify ."))
            self.assertIn("reports its artifact standing as <q>built</q>", page)
            home =(copy / "site/index.html").read_text()
            self.assertLess(home.index("Current release:"), home.index("Source release absd-preview-20261010 standing:"))
            served.write_bytes(served.read_bytes().replace(b"absd-preview-rc1", b"absd-preview-rcX", 1))
            bad = subprocess.run(["python3", "scripts/check.py"], cwd=copy, capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("served bytes differ from the sealed input", bad.stdout)
            # A tampered input refuses at build time.
            sealed = copy / "content/binary-preview/absd-preview-rc1/QUICKSTART.md"
            sealed.write_bytes(sealed.read_bytes() + b"x")
            failed = subprocess.run(["python3", "build.py"], cwd=copy, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("QUICKSTART.md bytes disagree", failed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
