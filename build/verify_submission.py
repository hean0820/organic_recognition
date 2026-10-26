"""Check repository file identity and naming; does not execute hardware tools."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def submission_files(root):
    files={}
    for folder,directories,names in os.walk(root):
        # Root Git metadata is local version history, not a deliverable.
        if Path(folder)==root:
            directories[:]=[name for name in directories if name!='.git']
        for name in names:
            path=Path(folder)/name
            relative=path.relative_to(root).as_posix()
            if relative in ('.git','build/submission_manifest.json'):
                continue
            files[relative]=path
    return files

def verify(root=ROOT):
    root=Path(root).resolve()
    manifest=json.loads((root/'build/submission_manifest.json').read_text(encoding='utf-8'))
    expected=manifest['files']
    actual=submission_files(root)
    if set(actual)!=set(expected):raise ValueError('File set differs: '+repr(sorted(set(actual)^set(expected))[:12]))
    for name,path in actual.items():
        for part in Path(name).parts:
            if part not in ('README.md','.gitignore','.gitattributes') and not re.fullmatch(r'[a-z0-9_-]+(?:\.[a-z0-9_-]+)*',part):
                raise ValueError('Invalid submission name: '+name)
        item=expected[name]
        if path.stat().st_size!=item['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('File identity differs: '+name)
    return {'passed':True,'files_checked':len(expected),'english_lowercase_paths':True,'hardware_accessed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    print(json.dumps(verify(args.root),indent=2))
