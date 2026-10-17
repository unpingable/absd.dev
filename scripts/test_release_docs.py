#!/usr/bin/env python3
"""Exercise the release-docs boundary with a tiny real Git source fixture.

The bytes are synthetic: these checks establish metadata/generation behavior,
not a boot result or a public release. The native rehearsal is separate.
"""
import copy
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
import importlib.util
import io
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import release_docs as docs


def fixture(directory, tag="absd-preview-fixture"):
    directory = pathlib.Path(directory)
    source = directory / "source"
    assets = directory / "assets"
    source.mkdir(parents=True)
    assets.mkdir()
    record = json.loads((ROOT / "content/release.json").read_text())
    record.update(schema_version=2, release_id=tag, kernel_commit="1" * 40,
                  platform_commit="2" * 40, release_commit="3" * 40)
    source_manifest = (f'[release]\nid = "{tag}"\n'
                       '[[component]]\nname = "kernel"\ncommit = "' + record['kernel_commit'] + '"\n'
                       '[[component]]\nname = "platform"\ncommit = "' + record['platform_commit'] + '"\n')
    (source / "SOURCE-MANIFEST.toml").write_text(source_manifest)
    (source / "platform/man").mkdir(parents=True)
    (source / "platform/man/intro.1").write_text('.Dd October 17, 2026\n.Dt INTRO 1\n.Os ABSD\n.Sh NAME\n.Nm intro\n.Nd release fixture manual\n.Sh DESCRIPTION\nThis is a synthetic documentation fixture.\n')
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=ABSD fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "Synthetic documentation source"], check=True)
    record["release_commit"] = docs.git_bytes(source, "rev-parse", "HEAD").decode().strip()
    names = ["operator.iso", "enroll.iso", "disk.img.xz", "absd-try.py", "NOTICES.md", "MANIFEST.toml", "QUICKSTART.md"]
    base = "https://github.com/unpingable/absd/releases/download/" + tag + "/"
    record["binary_preview"] = p = {
        "tag": tag, "assets": [{"name": n, "url": base + n, "sha256": "0" * 64, "bytes": 1} for n in names],
        "manifest_url": base + "MANIFEST.toml", "sums_url": base + "SHA256SUMS", "sums": [],
        "signature": "unsigned", "qemu_profile": docs.PROFILE,
        "host_tiers": docs.HOSTS[:],
        "qualification": "built", "evidence": [],
        "quickstart_url": record["repository"] + "/blob/" + tag + "/QUICKSTART.md",
        "limitations": ["Physical hardware qualification is not yet established.", "Synthetic fixture; no public release or boot claim."],
        "documentation": {"state": "draft", "manual_sha256": "0" * 64},
    }
    for n in names:
        (assets / n).write_bytes((n + " synthetic bytes\n").encode())
    manifest = ['schema = "absd-preview-manifest/1"', 'signature = "unsigned"', 'qualification = "built"',
                'limitations = ' + json.dumps(p['limitations']), '[release]']
    for key, value in {"id": tag, "tag": tag, "source_commit": record["release_commit"],
                       "kernel_commit": record["kernel_commit"], "platform_commit": record["platform_commit"]}.items():
        manifest.append(f'{key} = "{value}"')
    for role, name in [("operator_iso", "operator.iso"), ("enroll_iso", "enroll.iso"), ("disk", "disk.img.xz")]:
        data = (assets / name).read_bytes()
        manifest += [f"[assets.{role}]", f'name = "{name}"', f'sha256 = "{docs.digest(data)}"', f"bytes = {len(data)}"]
        if role == "disk":
            manifest += ['raw_sha256 = "' + "4" * 64 + '"', 'raw_bytes = 512']
    manifest += ['[qemu]', f'cpu_tcg = "{docs.CPU}"', 'memory_mib = 256', 'smp = 1',
                 'nic = "e1000"', 'disk = "ide"', 'firmware = "SeaBIOS"']
    (assets / "MANIFEST.toml").write_text("\n".join(manifest) + "\n")
    # Render before sealing the checksums. The guide does not contain its
    # own digest or a Git commit that would need to include its own bytes.
    for a in p["assets"]:
        data = (assets / a["name"]).read_bytes()
        a.update(sha256=docs.digest(data), bytes=len(data))
    doc = {'qualification': 'built', 'limitations': p['limitations']}
    (assets / "QUICKSTART.md").write_text(docs.quickstart(record, doc))
    (source / "QUICKSTART.md").write_text(docs.quickstart(record, doc))
    (source / "README.md").write_text("# Synthetic source fixture\n\n" + docs.readme_fragment(record, doc))
    source_manifest += ('[documentation]\nquickstart_sha256 = "' + docs.digest((source / 'QUICKSTART.md').read_bytes())
                        + '"\nreadme_fragment_sha256 = "' + docs.digest(docs.readme_fragment(record, doc).encode()) + '"\n')
    (source / "SOURCE-MANIFEST.toml").write_text(source_manifest)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=ABSD fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "Bind fixture documentation"], check=True)
    old_revision = record["release_commit"]
    record["release_commit"] = docs.git_bytes(source, "rev-parse", "HEAD").decode().strip()
    path = assets / "MANIFEST.toml"
    path.write_text(path.read_text().replace(old_revision, record["release_commit"]))
    extra = []
    for index, name in enumerate(['absd-try.py', 'NOTICES.md', 'QUICKSTART.md']):
        data = (assets / name).read_bytes()
        extra += [f'[assets.extra_{index}]', f'name = "{name}"', f'sha256 = "{docs.digest(data)}"', f'bytes = {len(data)}']
    path.write_text(path.read_text().replace('[qemu]', '\n'.join(extra)+'\n[qemu]'))
    for a in p["assets"]:
        data = (assets / a["name"]).read_bytes()
        a.update(sha256=docs.digest(data), bytes=len(data))
    p["sums"] = [f"{a['sha256']}  {a['name']}" for a in p["assets"]]
    (assets / "SHA256SUMS").write_text("\n".join(p["sums"]) + "\n")
    return record, source, assets


class ReleaseDocs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="absd-release-docs-")
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.record, self.source, self.assets = fixture(self.root)

    def stage(self):
        return docs.stage(self.record, self.root, self.assets, self.source)

    def test_exact_source_and_asset_import_then_manual_mutation_refuses(self):
        # Working-tree content is deliberately different from the named commit.
        (self.source / "platform/man/intro.1").write_text("uncommitted manual")
        self.stage()
        directory = docs.release_dir(self.root, self.record)
        page = directory / "manual/intro.1"
        self.assertIn(b"synthetic documentation fixture", page.read_bytes())
        docs.load(self.record, self.root)
        page.write_bytes(page.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "manual disagrees"):
            docs.load(self.record, self.root)

    def test_changed_actual_asset_is_not_accepted_by_consistent_metadata(self):
        (self.assets / "operator.iso").write_bytes(b"different image")
        with self.assertRaisesRegex(ValueError, "asset bytes disagree: operator.iso"):
            self.stage()

    def test_contradictory_pair_profile_qualification_and_manifest_schema(self):
        raw = (self.assets / "MANIFEST.toml").read_bytes()
        changes = [(b"1" * 40, b"9" * 40, "kernel_commit"),
                   (b'memory_mib = 256', b'memory_mib = 128', "QEMU profile"),
                   (b'qualification = "built"', b'qualification = "qualified"', "qualification"),
                   (b'absd-preview-manifest/1', b'absd-release-manifest/2', "expected absd-preview")]
        for before, after, reason in changes:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                docs.manifest(self.record, raw.replace(before, after))

    def test_internal_release_id_matches_native_helper_domain(self):
        original = self.record['release_id']
        changed = copy.deepcopy(self.record)
        changed['release_id'] = original.upper()
        changed['binary_preview']['tag'] = original.upper()
        raw = (self.assets/'MANIFEST.toml').read_bytes().replace(original.encode(), original.upper().encode())
        with self.assertRaisesRegex(ValueError, 'outside the native helper profile'):
            docs.manifest(changed, raw)

    def test_stale_quickstart_and_wrong_source_refuse(self):
        (self.assets / "QUICKSTART.md").write_text("old release guide")
        a = next(a for a in self.record["binary_preview"]["assets"] if a["name"] == "QUICKSTART.md")
        old_digest = a['sha256']
        a.update(sha256=docs.digest(b"old release guide"), bytes=len(b"old release guide"))
        p = self.record["binary_preview"]
        path = self.assets / 'MANIFEST.toml'
        text = path.read_text().replace(old_digest, a['sha256'])
        # Keep all three metadata views consistent; the stale prose must
        # still be refused by generation, rather than only by a hash check.
        role = text.index('[assets.extra_2]')
        before, after = text[:role], text[role:]
        after = re.sub(r'bytes = [0-9]+', 'bytes = '+str(a['bytes']), after, count=1)
        path.write_text(before+after)
        m = next(a for a in p['assets'] if a['name'] == 'MANIFEST.toml')
        m.update(sha256=docs.digest(path.read_bytes()), bytes=path.stat().st_size)
        p["sums"] = [f"{a['sha256']}  {a['name']}" for a in p["assets"]]
        (self.assets / "SHA256SUMS").write_text("\n".join(p["sums"]) + "\n")
        with self.assertRaisesRegex(ValueError, "QUICKSTART.md is stale"):
            self.stage()

    def test_restage_cannot_replace_historical_input(self):
        self.stage()
        page = docs.release_dir(self.root, self.record) / "manual/intro.1"
        page.write_text("retained changed input")
        with self.assertRaisesRegex(ValueError, "refusing to overwrite release input"):
            self.stage()

    def test_editorial_qualification_and_withdrawal_do_not_rewrite_frozen_instructions(self):
        self.stage()
        frozen = docs.exports(self.record, docs.load(self.record, self.root))
        updated = copy.deepcopy(self.record)
        updated['binary_preview']['qualification'] = 'qualified'
        updated['binary_preview']['documentation']['state'] = 'withdrawn'
        updated['binary_preview']['limitations'].append('Subsequent review withdrew this preview.')
        self.assertEqual(frozen, docs.exports(updated, docs.load(updated, self.root)))

    def test_shared_documentation_vector(self):
        self.stage()
        vector = json.loads((ROOT / 'scripts/testdata/release-documentation-v1.json').read_text())
        doc = docs.load(self.record, self.root)
        self.assertEqual(vector['quickstart_sha256'], docs.digest(docs.quickstart(self.record, doc).encode()))
        self.assertEqual(vector['readme_fragment_sha256'], docs.digest(docs.readme_fragment(self.record, doc).encode()))

    def test_post_publication_byte_check_keeps_separate_pass_and_fail_receipts(self):
        self.stage()
        p = self.record['binary_preview']
        p['documentation']['state'] = 'published'
        p['qualification'] = 'published'
        p['evidence'] = [{'level': 'published', 'label': 'Synthetic publication fixture', 'url': '/evidence/'}]
        record_path = self.root/'record.json'
        record_path.write_text(json.dumps(self.record))
        spec = importlib.util.spec_from_file_location('docs_cli', ROOT/'scripts/release-docs.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        cli.ROOT = self.root
        payload = {a['url']: (self.assets/a['name']).read_bytes() for a in p['assets']}
        payload[p['sums_url']] = (self.assets/'SHA256SUMS').read_bytes()

        class Response(io.BytesIO):
            def geturl(self):
                return 'https://release-assets.example.invalid/object?temporary=not-recorded'

        def fetch(url, timeout):
            return Response(payload[url])

        for failed in [False, True]:
            receipt = self.root/('failed.json' if failed else 'passed.json')
            if failed:
                payload[p['assets'][0]['url']] = b'changed image'
            with mock.patch.object(sys, 'argv', ['release-docs.py', 'reachable', '--record', str(record_path), '--out', str(receipt)]), \
                    mock.patch.object(cli.urllib.request, 'urlopen', fetch):
                if failed:
                    with self.assertRaisesRegex(ValueError, 'published asset differs'):
                        cli.main()
                else:
                    cli.main()
            data = json.loads(receipt.read_text())
            self.assertEqual(data['disposition'], 'FAIL' if failed else 'PASS')
            self.assertNotIn('temporary=', receipt.read_text())

    def test_source_readme_mutation_at_a_new_commit_is_refused(self):
        self.stage()
        (self.source / 'README.md').write_text('# Wrong release README\n')
        subprocess.run(['git', '-C', str(self.source), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.source), '-c', 'user.name=ABSD fixture', '-c', 'user.email=fixture@example.invalid',
                        'commit', '-qm', 'Wrong source README control'], check=True)
        old = self.record['release_commit']
        self.record['release_commit'] = docs.git_bytes(self.source, 'rev-parse', 'HEAD').decode().strip()
        path = self.assets / 'MANIFEST.toml'
        path.write_text(path.read_text().replace(old, self.record['release_commit']))
        p = self.record['binary_preview']
        a = next(a for a in p['assets'] if a['name'] == 'MANIFEST.toml')
        a.update(sha256=docs.digest(path.read_bytes()), bytes=path.stat().st_size)
        p['sums'] = [f"{a['sha256']}  {a['name']}" for a in p['assets']]
        (self.assets / 'SHA256SUMS').write_text('\n'.join(p['sums'])+'\n')
        with self.assertRaisesRegex(ValueError, 'source README download section disagrees'):
            self.stage()

    def test_source_manifest_identity_and_export_identity(self):
        self.stage()
        bad = copy.deepcopy(self.record)
        bad["platform_commit"] = "9" * 40
        with self.assertRaisesRegex(ValueError, "platform commit disagrees"):
            docs.check_source(bad, {"release": {"id": bad["release_id"]},
                                   "component": [{"name": "kernel", "commit": bad["kernel_commit"]},
                                                 {"name": "platform", "commit": "2" * 40}]})
        doc = docs.load(self.record, self.root)
        exports = docs.exports(self.record, doc)
        self.assertIn(self.record["release_id"], exports["QUICKSTART.md"])
        self.assertIn("--assets . --key ./absd-key.pub --accel tcg", exports["QUICKSTART.md"])
        self.assertIn("StrictHostKeyChecking=yes", exports["QUICKSTART.md"])
        self.assertNotIn(self.record["release_commit"], exports["README-download.md"])
        self.assertNotIn(self.record["release_commit"], exports["QUICKSTART.md"])


if __name__ == "__main__":
    unittest.main()
