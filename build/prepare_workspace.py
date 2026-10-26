"""Restore vendor-sensitive file names into a NEW external build workspace."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]

def prepare(output):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:
        raise ValueError('Use an output directory outside the submission repository')
    if output.exists(): raise FileExistsError('Output exists; choose a new directory: '+str(output))
    entries=json.loads((ROOT/'build/layout_manifest.json').read_text(encoding='utf-8'))['entries']
    names=set()
    for row in entries:
        rel=PurePosixPath(row['destination'])
        if rel.is_absolute() or '..' in rel.parts or '\\' in str(rel) or ':' in str(rel):
            raise ValueError('Unsafe workspace destination')
        source=(ROOT/row['source']).resolve()
        if ROOT not in source.parents or source.is_symlink():raise ValueError('Unsafe source')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Build source hash differs: '+row['source'])
        if str(rel).lower() in names:raise ValueError('Workspace path collision')
        names.add(str(rel).lower())
    output.mkdir(parents=True)
    for row in entries:
        target=output/row['destination']
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/row['source']).read_bytes())
    return {'passed':True,'workspace':str(output),'files_restored':len(entries),'hardware_accessed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare(args.output),indent=2))
