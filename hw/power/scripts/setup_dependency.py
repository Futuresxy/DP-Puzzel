#!/usr/bin/env python3
"""Extract only the pinned MIT power helpers from an existing upstream Git clone."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-repo', required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'dependencies/petile-power.json').read_text())
    destination = ROOT / manifest['directory']
    payload = {}
    for name, entry in manifest['files'].items():
        content = subprocess.check_output(['git', '-C', str(args.source_repo), 'show',
                                           manifest['commit'] + ':' + entry['upstream_path']])
        if hashlib.sha256(content).hexdigest() != entry['sha256']:
            raise ValueError('Pinned dependency hash mismatch: ' + name)
        payload[name] = content
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in payload.items():
        path = destination / name
        if path.exists() and path.read_bytes() != content:
            raise ValueError('Refusing to overwrite changed helper: ' + name)
        path.write_bytes(content)
    print('PASS pinned power helpers ' + manifest['commit'])


if __name__ == '__main__':
    main()
