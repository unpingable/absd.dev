#!/usr/bin/env python3
"""Render, stage, select or check release docs locally; never publishes.

render produces unsealed documentation before the producer hashes it.
stage verifies sealed assets and imports exact source metadata/manual pages.
select archives the previous binary record and selects a verified new one.
export/check writes or compares the release README fragment and quickstart.
"""
import argparse
import json
import pathlib
import sys
import datetime
import hashlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import release_docs


def write_exact(path, data):
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"refusing to overwrite historical record {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("render", "stage", "select", "export", "check", "reachable"))
    parser.add_argument("--record", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--assets", type=pathlib.Path)
    parser.add_argument("--source", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()
    record = json.loads(args.record.read_text())
    import build
    record = build.load_release(args.record, check_documentation=False)
    if args.command == "render":
        if args.manifest is None or args.out is None:
            parser.error("render requires --manifest and --out")
        doc = release_docs.manifest(record, args.manifest.read_bytes())
        args.out.mkdir(parents=True, exist_ok=True)
        for name, text in release_docs.exports(record, doc).items():
            (args.out / name).write_text(text)
        print("Rendered draft documentation; asset verification has not run.")
        return
    # Importing build validates the current selected record as well. A new
    # input is staged separately before it can replace that record.
    if record["binary_preview"] is None:
        raise ValueError("binary documentation requires a binary preview")
    if args.command == "stage":
        if args.assets is None or args.source is None:
            parser.error("stage requires --assets and --source")
        record = release_docs.stage(record, ROOT, args.assets, args.source)
        args.record.write_text(json.dumps(record, indent=2) + "\n")
        print("Staged verified asset metadata and exact source manual; no publication.")
        return
    doc = release_docs.load(record, ROOT)
    if args.command == "reachable":
        if args.out is None:
            parser.error("reachable requires --out for its separate receipt")
        if record['binary_preview']['documentation']['state'] != 'published':
            raise ValueError('reachable is a post-publication check; record state must be published')
        receipt = {'schema_version': 1, 'release_id': record['release_id'],
                   'time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'record_sha256': release_docs.digest(args.record.read_bytes()), 'files': [],
                   'disposition': 'INCOMPLETE', 'scope': 'Public bytes at pinned URLs; no authenticity, authorization or boot claim.'}
        try:
            for asset in record['binary_preview']['assets']:
                h, size = hashlib.sha256(), 0
                with urllib.request.urlopen(asset['url'], timeout=45) as response:
                    if not response.geturl().startswith('https://'):
                        raise ValueError('asset redirected away from HTTPS')
                    while chunk := response.read(1024 * 1024):
                        h.update(chunk)
                        size += len(chunk)
                        if size > asset['bytes']:
                            raise ValueError('published asset is larger than recorded: ' + asset['name'])
                if size != asset['bytes'] or h.hexdigest() != asset['sha256']:
                    raise ValueError('published asset differs: ' + asset['name'])
                receipt['files'].append({'url': asset['url'], 'bytes': size, 'sha256': h.hexdigest()})
            with urllib.request.urlopen(record['binary_preview']['sums_url'], timeout=45) as response:
                sums = response.read(1024 * 1024 + 1)
                if len(sums) > 1024 * 1024 or sums.decode('ascii').splitlines() != record['binary_preview']['sums']:
                    raise ValueError('published SHA256SUMS disagrees')
            receipt['disposition'] = 'PASS'
        except Exception as error:
            receipt['disposition'] = 'FAIL'
            receipt['error_type'] = type(error).__name__
            raise
        finally:
            # Never store redirect URLs: provider redirects may contain
            # temporary query parameters. The canonical public URL is enough.
            with args.out.open('x') as handle:
                handle.write(json.dumps(receipt, indent=2)+'\n')
        print('Public release reachability: PASS; boot rehearsal remains separate.')
        return
    if args.command == "select":
        if build.RELEASE["binary_preview"] is not None and build.RELEASE["release_id"] != record["release_id"]:
            old = release_docs.release_dir(ROOT, build.RELEASE) / "release.json"
            write_exact(old, build.RELEASE_PATH.read_bytes())
        build.RELEASE_PATH.write_text(args.record.read_text())
        print("Selected local release record; prior binary record preserved; no publication.")
        return
    if args.out is None:
        parser.error("export/check requires --out")
    for name, text in release_docs.exports(record, doc).items():
        path = args.out / name
        if args.command == "check":
            if not path.is_file() or path.read_text() != text:
                raise ValueError(f"release documentation disagrees: {name}")
        else:
            args.out.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    print(f"Release documentation {args.command}: PASS")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(f"release-docs: REFUSED {error}", file=sys.stderr)
        sys.exit(1)
