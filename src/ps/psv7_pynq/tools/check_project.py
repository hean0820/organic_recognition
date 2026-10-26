"""Verify complete package and resources without importing PYNQ or probing AXI."""
import ast
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from psv7_pynq.app.config import load_config, verify_project
from psv7_pynq.app.host_service import validate_host_assets


def main():
    report = verify_project(ROOT)
    _, config = load_config(ROOT)
    count = 0
    for file in ROOT.rglob('*.py'):
        if 'reports' not in file.relative_to(ROOT).parts:
            ast.parse(file.read_text(encoding='utf-8'), feature_version=(3, 8))
            count += 1
    xml = ET.parse(ROOT / 'overlay/psv7.hwh')
    ranges = {node.attrib.get('INSTANCE'): node.attrib for node in xml.iter('MEMRANGE')}
    for name, address in config['ip_addresses'].items():
        if name not in ranges or int(ranges[name]['BASEVALUE'], 0) != address:
            raise RuntimeError('HWH address mismatch: ' + name)
    report.update(python38_modules_checked=count, hwh_ip_addresses_checked=len(config['ip_addresses']),
                  host_assets_checked=validate_host_assets(ROOT))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    main()
