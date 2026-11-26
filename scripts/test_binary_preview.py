#!/usr/bin/env python3
"""The binary-only preview path against the committed RC1 inputs.

The committed record and sealed files must pass; each tampered or
contradictory copy must refuse by name; the source-release record and its
validator keep their earlier behaviour. These are metadata checks: boot, SSH
and persistence are the separate reader rehearsal's.
"""
import hashlib
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import binary_preview as bp
import release_docs

# The reviewed final release set (rc1-release-set-20261018T191939Z).
SEALED = {"MANIFEST.toml": "71066f42b41886834af4f56b8a98973635a4b2e617d355f4c806432a35246567",
          "QUICKSTART.md": "96c18db6bc8463b686012a6d49bc74eca0b0265a11640f8e1e8fb9049cead824",
          "SHA256SUMS": "22850b3193fbe99f0623970096f14e5ff4b941e9713e676f7fe103ed59913d71"}
SOURCE_ID = json.loads((ROOT / "content/release.json").read_text())["release_id"]


def preview1_record():
    path = ROOT / "content/binary-preview/absd-preview-rc1.json"
    if not path.exists():
        path = bp.record_path(ROOT)
    record = json.loads(path.read_text())
    assert record["tag"] == "absd-preview-rc1"
    return record


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Inputs:
    """A writable copy of the committed record and sealed inputs."""

    def __init__(self, directory):
        self.root = pathlib.Path(directory)
        self.record = preview1_record()
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
        record = preview1_record()
        files = bp.verify(record, bp.input_dir(ROOT, record), SOURCE_ID)
        self.assertEqual({n: sha(d) for n, d in files.items()}, SEALED)
        self.assertNotEqual(record["tag"], record["release_id"])
        doc = tomllib.loads(files["MANIFEST.toml"].decode())
        self.assertNotIn("source_commit", doc["release"])
        self.assertEqual(record["first_party_source"]["tag"], "absd-source-rc1")

    def test_source_association_refuses_wrong_components_and_tags(self):
        original = json.loads(json.dumps(self.inputs.record["first_party_source"]))
        for key, value in [("kernel_commit", "0" * 40), ("platform_commit", "0" * 40),
                           ("tag", self.inputs.record["tag"]), ("tag", SOURCE_ID),
                           ("commit", "latest"), ("tree", "x" * 40),
                           ("source_manifest_sha256", "bad")]:
            with self.subTest(key=key, value=value):
                self.inputs.record["first_party_source"] = dict(original, **{key: value})
                with self.assertRaises(ValueError):
                    self.inputs.verify()
        self.inputs.record["first_party_source"] = None
        self.inputs.verify()  # Original binary-only records remain supported.

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

    def test_first_party_source_requires_exact_structure_and_fields(self):
        self.inputs.record["first_party_source"] = "absd-preview-20261010"
        self.refuses("malformed first_party_source")
        self.inputs.record["first_party_source"] = None
        self.inputs.record["release_commit"] = "0" * 40
        self.refuses("exact fields")

    def test_later_notices_correction_is_separate_from_sealed_assets(self):
        original_assets = json.loads(json.dumps(self.inputs.record["assets"]))
        original_sums = self.inputs.read("SHA256SUMS")
        self.inputs.record["notices_correction"] = dict(bp.CORRECTION)
        self.inputs.verify()
        self.assertEqual(self.inputs.record["assets"], original_assets)
        self.assertEqual(self.inputs.read("SHA256SUMS"), original_sums)
        self.inputs.record["notices_correction"] = None
        self.inputs.verify()

    def test_later_notices_correction_refuses_changed_identity(self):
        variants = ["published", {}, dict(bp.CORRECTION, bytes=64836.0),
                    dict(bp.CORRECTION, bytes=True), dict(bp.CORRECTION, bytes=1),
                    dict(bp.CORRECTION, sha256="0" * 64),
                    dict(bp.CORRECTION, url="https://example.invalid/correction"),
                    dict(bp.CORRECTION, name="different.tar.gz"),
                    dict(bp.CORRECTION, extra="unknown")]
        for correction in variants:
            with self.subTest(correction=correction):
                self.inputs.record["notices_correction"] = correction
                self.refuses("notices_correction differs")


class PreviewSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="absd-preview-selection-")
        self.addCleanup(self.tmp.cleanup)
        self.inputs = Inputs(pathlib.Path(self.tmp.name) / "inputs-copy")
        self.record = json.loads(json.dumps(self.inputs.record))
        old_tag = self.record["tag"]
        self.record["tag"] = "absd-preview-2"
        self.record["display_name"] = "ABSD Developer Preview 2"
        self.record.pop("notices_correction", None)
        for asset in self.record["assets"]:
            asset["url"] = asset["url"].replace("/" + old_tag + "/", "/absd-preview-2/")
        self.record["first_party_source"]["tag"] = self.record["tag"]

    def archive(self):
        root = pathlib.Path(self.tmp.name) / "site-root"
        directory = root / "content/binary-preview"
        directory.mkdir(parents=True)
        old = preview1_record()
        (directory / (old["tag"] + ".json")).write_text(json.dumps(old))
        shutil.copytree(self.inputs.dir, directory / old["tag"])
        return root, old

    def test_common_preview2_source_tag_still_refuses_wrong_components(self):
        self.record.pop("display_name")
        bp.check_record(self.record, SOURCE_ID)
        self.record["first_party_source"]["kernel_commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "source components disagree"):
            bp.check_record(self.record, SOURCE_ID)

    def test_current_preview2_inputs_pass_with_their_sealed_bytes(self):
        record, files = bp.load(ROOT, SOURCE_ID)
        self.assertEqual(record['tag'], 'absd-preview-2')
        self.assertEqual({name: sha(data) for name, data in files.items()}, {
            'MANIFEST.toml': '21794d69f5bd0b7060a2ece719fd9ab112c09087b37e3a1d0f4f519045038eeb',
            'QUICKSTART.md': '45fccebacba15b93bd88838a952e83ee6c93975e5471e4b686dad816af9a63fc',
            'SHA256SUMS': '503d365bb9886a92b71f6856dc2b99c0d08248b65d2daf50a63e12879f177b2d',
        })

    def test_published_preview2_requires_its_matching_source_tag(self):
        bp.check_record(self.record, SOURCE_ID)
        source = self.record['first_party_source']
        for value in (None, dict(source, tag='absd-source-rc1')):
            with self.subTest(source=value):
                self.record['first_party_source'] = value
                with self.assertRaisesRegex(ValueError, 'published Preview 2 requires matching source'):
                    bp.check_record(self.record, SOURCE_ID)

    def test_names_and_primary_download_are_release_pinned(self):
        import build
        bp.check_record(self.record, SOURCE_ID)
        with patch.object(build, "BINARY", (self.record, {})):
            notice = build.binary_notice()
            started = build.binary_get_started()
        self.assertIn("ABSD Developer Preview 2", notice)
        self.assertIn('href="/releases/absd-preview-2/"', notice)
        self.assertNotIn('<code>absd-preview-2</code>', notice)
        self.assertNotIn('href="/try/"', notice)
        self.assertIn('href="/releases/absd-preview-2/"', started)
        self.assertNotIn('<code>absd-preview-2</code>', started)
        source_note = build.binary_source_note(self.record)
        self.assertIn('/docs/PREVIEW2-SOURCE.md', source_note)
        self.assertNotIn('archives still name the earlier public source preview', source_note)
        self.record["display_name"] = "ABSD Developer Preview 1"
        with self.assertRaisesRegex(ValueError, "display_name"):
            bp.check_record(self.record, SOURCE_ID)

    def test_selection_retains_preview1_page_and_exact_sealed_guide(self):
        import build
        root, old = self.archive()
        archived = bp.load_archives(root, SOURCE_ID, self.record)
        self.assertEqual(len(archived), 1)
        # Keep this control entirely offline: synthetic Preview2 metadata,
        # with the immutable Preview1 guide as the archived consumer input.
        with patch.object(build, "BINARY", (self.record, archived[0][1])), \
             patch.object(build, "BINARY_ARCHIVES", archived):
            outputs = build.binary_outputs()
        self.assertEqual(outputs['releases/absd-preview-rc1/QUICKSTART.md'], self.inputs.read('QUICKSTART.md'))
        self.assertIn(b'<h1>ABSD Developer Preview 1</h1>', outputs['releases/absd-preview-rc1/index.html'])
        self.assertIn(b'<h1>ABSD Developer Preview 2</h1>', outputs['try/index.html'])
        self.assertIn(b'href="/releases/absd-preview-rc1/"', outputs['try/index.html'])
        self.assertIn(b'href="/releases/absd-preview-2/"', outputs['releases/absd-preview-rc1/index.html'])

    def test_archived_guide_tampering_and_conflicting_selection_refuse(self):
        root, old = self.archive()
        guide = bp.input_dir(root, old) / 'QUICKSTART.md'
        guide.write_bytes(guide.read_bytes() + b'changed\n')
        with self.assertRaisesRegex(ValueError, "QUICKSTART.md bytes disagree"):
            bp.load_archives(root, SOURCE_ID, self.record)
        guide.write_bytes(self.inputs.read('QUICKSTART.md'))
        selected = json.loads(json.dumps(old))
        selected['works'].append('Conflicting editorial state')
        with self.assertRaisesRegex(ValueError, "conflict"):
            bp.load_archives(root, SOURCE_ID, selected)

    def test_archived_download_total_uses_its_own_sealed_checksum_file(self):
        import build
        selected = bp.load(ROOT, SOURCE_ID)
        archived = bp.load_archives(ROOT, SOURCE_ID, selected[0])
        self.assertEqual(len(selected[1]["SHA256SUMS"]), 1054)
        self.assertEqual(len(archived[0][1]["SHA256SUMS"]), 1107)
        with patch.object(build, "BINARY", selected), \
             patch.object(build, "BINARY_ARCHIVES", archived):
            outputs = build.binary_outputs()
        page = outputs["releases/absd-preview-rc1/index.html"].decode()
        total = re.search(r"The complete download is ([0-9,]+) bytes\.", page)
        self.assertIsNotNone(total)
        self.assertEqual(total.group(1), "91,756,032")


class SourcePathUnchanged(unittest.TestCase):
    def test_source_and_notice_pointers_survive_both_source_states(self):
        import build
        record = preview1_record()
        source = record["first_party_source"]
        for current in (source, None):
            with self.subTest(source=current):
                record["first_party_source"] = current
                record["notices_correction"] = dict(bp.CORRECTION)
                note = build.binary_source_note(record)
                for text in ("GRUB", "GNU Unifont", "absd-rc1-boot-corresponding-source.tar",
                             "absd-rc1-third-party-notices.tar.gz", "absd-preview-20261010",
                             bp.CORRECTION["name"], bp.CORRECTION["sha256"], "64,836 bytes",
                             "original SHA256SUMS and NOTICES.md are unchanged"):
                    self.assertIn(text, note)
                with patch.object(build, "BINARY", (record, {})):
                    if current is not None:
                        self.assertIn("states which checks ran", build.rc1_check_standing())
                        self.assertNotIn("what a public clone can re-run", build.rc1_check_standing())
        record.pop("notices_correction")
        self.assertNotIn(bp.CORRECTION["name"], build.binary_source_note(record))

    def test_absent_later_source_retains_binary_only_wording(self):
        import build
        record = preview1_record()
        record["first_party_source"] = None
        with patch.object(build, "BINARY", (record, {})):
            self.assertIn("No first-party ABSD source release accompanies", build.binary_source_note(record))
            self.assertIn("it has not happened yet", build.rc1_source_standing())
        with patch.object(build, "BINARY", None):
            self.assertIn("it has not happened yet", build.rc1_source_standing())

    def test_source_record_still_validates_alone(self):
        import build
        record = build.load_release(build.RELEASE_PATH)
        self.assertIsNone(record["binary_preview"])
        self.assertEqual(record["schema_version"], 1)

    def test_source_validator_still_refuses_the_binary_only_manifest(self):
        current = json.loads(bp.record_path(ROOT).read_text())
        for record in (preview1_record(), current):
            with self.subTest(tag=record["tag"]):
                data = (bp.input_dir(ROOT, record) / "MANIFEST.toml").read_bytes()
                reference = json.loads((ROOT / "scripts/testdata/schema1-rendering-v1.json").read_text())
                source = json.loads(reference["release_json"])
                source.update(schema_version=2, release_id=record["release_id"], release_commit="0" * 40,
                              kernel_commit=record["kernel_commit"], platform_commit=record["platform_commit"],
                              binary_preview={"signature": "unsigned"})
                with self.assertRaises(ValueError) as caught:
                    release_docs.manifest(source, data)
                field = "tag" if record["release_id"] != record["tag"] else "source_commit"
                self.assertIn(f"manifest release.{field} disagrees with release record", str(caught.exception))



class BuiltSite(unittest.TestCase):
    """Build a copy, check it, then tamper with the output."""

    def test_build_serves_sealed_guide_and_check_refuses_tampering(self):
        with tempfile.TemporaryDirectory(prefix="absd-binary-site-") as directory:
            copy = pathlib.Path(directory) / "site-source"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "site", "__pycache__"))
            bp.record_path(copy).write_text(json.dumps(preview1_record()))
            subprocess.run(["python3", "build.py"], cwd=copy, check=True, capture_output=True)
            ok = subprocess.run(["python3", "scripts/check.py"], cwd=copy, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            served = copy / "site/releases/absd-preview-rc1/QUICKSTART.md"
            self.assertEqual(sha(served.read_bytes()), SEALED["QUICKSTART.md"])
            page = (copy / "site/try/index.html").read_text()
            self.assertIn('href="/releases/absd-preview-rc1/QUICKSTART.md"', page)
            self.assertIn("First-party ABSD source for", page)
            sentence = ("RC1's first-party source is not yet published, so independent parties cannot currently "
                        "reproduce its builds from the published materials.")
            self.assertNotIn(sentence, page)
            source = preview1_record()["first_party_source"]
            link = "https://github.com/unpingable/absd/tree/" + source["tag"]
            self.assertIn(link, page)
            self.assertIn(link, (copy / "site/status/index.html").read_text())
            self.assertIn(source["commit"], page)
            self.assertIn("does not change the sealed binary manifest", page)
            self.assertIn("or establish byte-for-byte independent reproduction", page)
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


class KitRelease:
    """A kit-form release sealed the way the producer seals one: every kit
    file but the manifest is bound by the manifest, the kit's SHA256SUMS
    lists them all, and two outer lists cover the release assets."""
    TAG = "absd-preview-3"
    KIT = "absd-preview-3-operator.tar.gz"
    GUIDE = (ROOT / "scripts/testdata/preview3-kit-QUICKSTART.md").read_bytes()

    def __init__(self, directory):
        self.root = pathlib.Path(directory)
        self.dir = self.root / "inputs"
        self.dir.mkdir()
        self.members = {"operator.iso": b"operator", "enroll.iso": b"enroll", "disk.img.xz": b"disk",
                        "absd-try.py": b"helper", "absd_fs.py": b"module", "NOTICES.md": b"notices\n",
                        "QUICKSTART.md": self.GUIDE}
        self.attachments = {"absd-preview-3-source.tar.gz": b"source", "rust-src-1.95.0.tar.xz": b"rust"}
        self.guide = self.GUIDE
        self.limitations = [bp.HARDWARE_LIMIT, "No rehearsal of these exact media is recorded in this manifest."]
        self.release = {"id": self.TAG, "tag": self.TAG, "kernel_commit": "1" * 40, "platform_commit": "2" * 40,
                        "utils_commit": "3" * 40}
        self.record = None
        self.seal()

    def manifest(self):
        lines = ['schema = "absd-preview-manifest/1"', 'signature = "unsigned"', 'qualification = "built"',
                 "limitations = " + json.dumps(self.limitations), "[release]"]
        lines += [f"{key} = {json.dumps(value)}" for key, value in self.release.items()]
        lines += ["[qemu]", f'cpu_tcg = "{release_docs.CPU}"', "memory_mib = 256", "smp = 1", 'nic = "e1000"',
                  'disk = "ide"', 'firmware = "SeaBIOS"']
        roles = {"operator.iso": "operator_iso", "enroll.iso": "enroll_iso", "disk.img.xz": "disk"}
        for index, (name, data) in enumerate(sorted(self.members.items())):
            lines += [f"[assets.{roles.get(name, f'extra_{index}')}]", f'name = "{name}"',
                      f'sha256 = "{sha(data)}"', f"bytes = {len(data)}"]
            if name == "disk.img.xz":
                lines += [f'raw_sha256 = "{"4" * 64}"', "raw_bytes = 134217728"]
        return ("\n".join(lines) + "\n").encode()

    def seal(self, manifest=None):
        manifest = self.manifest() if manifest is None else manifest
        inner = {**self.members, "MANIFEST.toml": manifest}
        inner_sums = "".join(f"{sha(data)}  {name}\n" for name, data in sorted(inner.items())).encode()
        kit = self.root / self.KIT
        with tarfile.open(kit, "w:gz") as bundle:
            for name, data in sorted({**inner, "SHA256SUMS": inner_sums}.items()):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
        source_sums = "".join(f"{sha(data)}  {name}\n" for name, data in sorted(self.attachments.items())).encode()
        outer = {self.KIT: kit.read_bytes(), "QUICKSTART.md": self.guide, "SHA256SUMS.source": source_sums}
        outer_sums = "".join(f"{sha(data)}  {name}\n" for name, data in sorted(outer.items())).encode()
        for name, data in (("MANIFEST.toml", manifest), ("QUICKSTART.md", self.guide), ("SHA256SUMS", outer_sums),
                           ("SHA256SUMS.source", source_sums), ("KIT.SHA256SUMS", inner_sums)):
            (self.dir / name).write_bytes(data)
        base = f"{bp.ASSET_BASE}{self.TAG}/"
        self.record = {
            "schema": bp.SCHEMA, "repository": bp.REPOSITORY, "tag": self.TAG, "release_id": self.TAG,
            "kernel_commit": "1" * 40, "platform_commit": "2" * 40, "utils_commit": "3" * 40,
            "release_date": "2026-11-27", "state": "draft", "signature": "unsigned", "qualification": "built",
            "evidence": [], "sums_sha256": sha(outer_sums), "limitations": list(self.limitations),
            "works": ["Boots."], "not_in_preview": ["Hardware."], "first_party_source": None,
            "kit": {"name": self.KIT, "sums_sha256": sha(inner_sums)},
            "assets": [{"name": name, "url": base + name, "sha256": sha(data), "bytes": len(data)}
                       for name, data in sorted({**outer, **self.attachments}.items())],
        }
        return kit

    def verify(self):
        return bp.verify(self.record, self.dir, SOURCE_ID)


class KitPreview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="absd-kit-")
        self.addCleanup(self.tmp.cleanup)
        self.kit = KitRelease(self.tmp.name)

    def refuses(self, expect):
        with self.assertRaises(ValueError) as caught:
            self.kit.verify()
        self.assertIn(expect, str(caught.exception))

    def test_sealed_kit_release_passes_with_the_accepted_guide(self):
        files = self.kit.verify()
        self.assertEqual(sorted(files), sorted(bp.KIT_INPUTS))
        self.assertEqual(files["QUICKSTART.md"], KitRelease.GUIDE)
        self.assertEqual(bp.check_kit_archive(self.kit.record, self.kit.dir, self.kit.root / KitRelease.KIT),
                         sorted([*self.kit.members, "MANIFEST.toml", "SHA256SUMS"]))

    def test_flat_record_checks_are_unchanged_by_the_kit_form(self):
        record = preview1_record()
        self.assertNotIn("kit", record)
        bp.verify(record, bp.input_dir(ROOT, record), SOURCE_ID)

    def test_kit_record_needs_all_five_inputs_and_no_others(self):
        (self.kit.dir / "KIT.SHA256SUMS").rename(self.kit.root / "moved")
        self.refuses("exactly")
        (self.kit.root / "moved").rename(self.kit.dir / "KIT.SHA256SUMS")
        (self.kit.dir / "extra").write_text("x")
        self.refuses("exactly")

    def test_malformed_kit_field_refuses(self):
        for kit in (None, {}, {"name": KitRelease.KIT}, {"name": "QUICKSTART.md", "sums_sha256": "0" * 64},
                    {"name": ["x"], "sums_sha256": "0" * 64}, {"name": "absent.tar.gz", "sums_sha256": "0" * 64},
                    {"name": KitRelease.KIT, "sums_sha256": "short"}):
            with self.subTest(kit=kit):
                self.kit.record["kit"] = kit
                self.refuses("kit must name")

    def test_outer_list_must_be_exactly_kit_guide_and_source_list(self):
        sums = (self.kit.dir / "SHA256SUMS").read_bytes() + f"{sha(b'source')}  absd-preview-3-source.tar.gz\n".encode()
        (self.kit.dir / "SHA256SUMS").write_bytes(sums)
        self.kit.record["sums_sha256"] = sha(sums)
        self.refuses("must list exactly the kit")

    def test_asset_missing_from_both_lists_refuses(self):
        base = f"{bp.ASSET_BASE}{KitRelease.TAG}/"
        self.kit.record["assets"].append({"name": "unlisted.tar", "url": base + "unlisted.tar",
                                          "sha256": "5" * 64, "bytes": 1})
        self.refuses("record assets disagree")

    def test_tampered_guide_source_list_or_kit_list_refuses(self):
        for name, expect in (("QUICKSTART.md", "QUICKSTART.md bytes disagree"),
                             ("SHA256SUMS.source", "record assets disagree"),
                             ("KIT.SHA256SUMS", "kit's SHA256SUMS bytes disagree"),
                             ("MANIFEST.toml", "MANIFEST.toml bytes disagree with the kit")):
            with self.subTest(name=name):
                path = self.kit.dir / name
                original = path.read_bytes()
                path.write_bytes(original + (b"\n" if name in ("QUICKSTART.md", "MANIFEST.toml")
                                             else f"{'6' * 64}  another\n".encode()))
                self.refuses(expect)
                path.write_bytes(original)

    def test_manifest_must_bind_every_kit_member_with_its_digest(self):
        self.kit.members["absd_image.py"] = b"unbound"
        manifest = self.kit.manifest()
        del self.kit.members["absd_image.py"]
        unbound = self.kit.manifest()
        self.kit.members["absd_image.py"] = b"unbound"
        self.kit.seal(unbound)
        self.refuses("manifest must bind every kit member except itself")
        self.kit.seal(manifest.replace(sha(b"operator").encode(), b"7" * 64))
        self.refuses("manifest asset operator_iso disagrees with the kit's SHA256SUMS")

    def test_kit_must_carry_manifest_notices_helper_and_the_same_guide(self):
        del self.kit.members["NOTICES.md"]
        self.kit.seal()
        self.refuses("missing kit member NOTICES.md")
        self.kit.members["NOTICES.md"] = b"notices\n"
        self.kit.members["QUICKSTART.md"] = b"another guide\n"
        self.kit.seal()
        self.refuses("the kit's guide differs")

    def test_manifest_release_binds_utils_only_with_the_record(self):
        del self.kit.record["utils_commit"]
        self.refuses("manifest release table has unexpected keys")
        self.kit.record["utils_commit"] = "8" * 40
        self.refuses("manifest release.utils_commit disagrees")

    def test_media_keep_plain_names_and_source_may_share_the_tag(self):
        doc = tomllib.loads((self.kit.dir / "MANIFEST.toml").read_text())
        self.assertEqual(doc["assets"]["operator_iso"]["name"], "operator.iso")
        source = {"tag": KitRelease.TAG, "commit": "a" * 40, "tree": "b" * 40, "source_manifest_sha256": "c" * 64,
                  "kernel_commit": "1" * 40, "platform_commit": "2" * 40}
        self.kit.record["first_party_source"] = source
        self.kit.verify()
        self.kit.record.update(state="published", qualification="published", first_party_source=None,
                               evidence=[{"level": "published", "label": "Release", "url": "https://example.invalid/r"}])
        self.refuses("requires matching source at its release tag")

    def test_guide_must_gate_unpacking_on_the_digest_and_name_the_release(self):
        cases = (
            (b'echo "DIGEST  SHA256SUMS" | sha256sum -c --strict - &&\n', b"", "in that order"),
            (b"tar -xzf absd-preview-3-operator.tar.gz -C preview3-operator &&\n", b"", "in that order"),
            (b"VERIFIED release=absd-preview-3", b"VERIFIED", "VERIFIED release=absd-preview-3"),
            (b"sha256sum -c --strict SHA256SUMS.source\n", b"", "SHA256SUMS.source"),
            (b"`SHA256SUMS.source`", b"the source list", "does not name SHA256SUMS.source"),
        )
        for old, new, expect in cases:
            with self.subTest(old=old):
                self.assertIn(old, KitRelease.GUIDE)
                self.kit.guide = self.kit.members["QUICKSTART.md"] = KitRelease.GUIDE.replace(old, new)
                self.kit.seal()
                self.refuses(expect)
        swapped = KitRelease.GUIDE.replace(
            b'echo "DIGEST  SHA256SUMS" | sha256sum -c --strict - &&\nsha256sum -c --strict SHA256SUMS &&\n'
            b"mkdir preview3-operator &&\ntar -xzf absd-preview-3-operator.tar.gz -C preview3-operator &&\n",
            b"mkdir preview3-operator &&\ntar -xzf absd-preview-3-operator.tar.gz -C preview3-operator &&\n"
            b'echo "DIGEST  SHA256SUMS" | sha256sum -c --strict - &&\nsha256sum -c --strict SHA256SUMS &&\n')
        self.assertNotEqual(swapped, KitRelease.GUIDE)
        self.kit.guide = self.kit.members["QUICKSTART.md"] = swapped
        self.kit.seal()
        self.refuses("in that order")
        # The reviewer's two cases: a chain broken after the list check, so
        # the unpacking runs whatever the checks said; and an unpacking
        # spelled another way ahead of the checked chain.
        broken = KitRelease.GUIDE.replace(b"sha256sum -c --strict SHA256SUMS &&\nmkdir preview3-operator &&\n",
                                          b"sha256sum -c --strict SHA256SUMS\nmkdir preview3-operator &&\n")
        self.assertNotEqual(broken, KitRelease.GUIDE)
        self.kit.guide = self.kit.members["QUICKSTART.md"] = broken
        self.kit.seal()
        self.refuses("in that order")
        early = KitRelease.GUIDE.replace(b'echo "DIGEST  SHA256SUMS"',
                                         b'tar xzf absd-preview-3-operator.tar.gz\necho "DIGEST  SHA256SUMS"')
        self.assertNotEqual(early, KitRelease.GUIDE)
        self.kit.guide = self.kit.members["QUICKSTART.md"] = early
        self.kit.seal()
        self.refuses("runs tar outside its checked command chain")
        other = KitRelease.GUIDE + b"\nhttps://github.com/unpingable/absd/releases/download/absd-preview-2/x\n"
        self.kit.guide = self.kit.members["QUICKSTART.md"] = other
        self.kit.seal()
        self.refuses("names another release tag")

    def test_kit_archive_check_refuses_other_bytes_and_other_inputs(self):
        archive = self.kit.root / KitRelease.KIT
        record, inputs = json.loads(json.dumps(self.kit.record)), self.kit.root / "kept"
        shutil.copytree(self.kit.dir, inputs)
        self.kit.members["absd-try.py"] = b"another helper"
        self.kit.seal()  # a different kit at the same path
        with self.assertRaisesRegex(ValueError, "kit archive"):
            bp.check_kit_archive(record, inputs, archive)
        # The right archive, but a manifest committed from somewhere else.
        with self.assertRaisesRegex(ValueError, "not the files inside the kit archive"):
            (self.kit.dir / "MANIFEST.toml").write_bytes(b"other\n")
            bp.check_kit_archive(self.kit.record, self.kit.dir, archive)

    def test_kit_page_prints_the_digest_and_serves_the_five_inputs(self):
        import build
        binary = (self.kit.record, self.kit.verify())
        page = build.binary_page(binary)
        self.assertIn(f'<p><code class="digest">{self.kit.record["sums_sha256"]}</code></p>', page)
        self.assertIn("<code>SHA256SUMS</code></a></td>", page)
        self.assertIn('href="/releases/absd-preview-3/KIT.SHA256SUMS"', page)
        self.assertIn("<code>absd-preview-3-operator.tar.gz</code>", page)
        self.assertNotIn("curl", page)
        self.assertNotIn("its helper modules", page)
        self.assertIn("The other 2 files are the source and notice archives", page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
