"""Read-only file/hash/HWH contract validation; no board libraries required."""
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def validate(profile, root):
    root = Path(root).resolve()
    hashes = {}
    for role in ('bit', 'hwh'):
        entry = profile['files'][role]
        file = (root / entry['path']).resolve()
        if root not in file.parents or not file.is_file():
            raise ValueError('File outside package or missing: ' + role)
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        if digest != entry['sha256']:
            raise ValueError('File hash differs: ' + role)
        hashes[role] = digest
    xml = ET.parse(root / profile['files']['hwh']['path'])
    ranges = {}
    for node in xml.iter('MEMRANGE'):
        name = node.attrib.get('INSTANCE')
        if 'BASEVALUE' in node.attrib:
            ranges.setdefault(name, set()).add(int(node.attrib['BASEVALUE'], 0))
    for name, address in profile['ips'].items():
        address = int(address, 0) if isinstance(address, str) else int(address)
        if ranges.get(name) != {address}:
            raise ValueError('Missing or ambiguous HWH address: ' + name)
    return {'passed': True, 'kind': 'files_and_hwh_only', 'profile': profile['name'],
            'sha256': hashes, 'ip_count': len(profile['ips']), 'hardware_accessed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(json.loads(args.profile.read_text(encoding='utf-8')), args.root)
    except Exception as error:
        print(json.dumps({'passed': False, 'error': str(error)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
