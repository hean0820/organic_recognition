"""Verify SHA256 and safely unpack the supplied runtime ZIP to a NEW directory."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

def unpack(archive,output,expected):
    archive=Path(archive).resolve();output=Path(output).resolve()
    actual=hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual!=expected.lower():raise ValueError('ZIP SHA256 differs')
    if output.exists():raise FileExistsError('Output exists; choose a new runtime directory')
    with zipfile.ZipFile(archive) as z:
        names=set();items=z.infolist()
        if len(items)>2000 or sum(i.file_size for i in items)>256*1024*1024:raise ValueError('Unexpected ZIP size')
        for item in items:
            rel=PurePosixPath(item.filename)
            if (rel.is_absolute() or '..' in rel.parts or '\\' in item.filename or ':' in item.filename
                or len(rel.parts)<2 or rel.parts[0] not in ('psv7_pynq','ps_vs_rtl')
                or stat.S_ISLNK(item.external_attr>>16)):
                raise ValueError('Invalid ZIP member: '+item.filename)
            if any(not re.fullmatch(r'[a-z0-9_-]+(?:\.[a-z0-9_-]+)*',part) for part in rel.parts):
                raise ValueError('Unexpected filename: '+item.filename)
            if item.filename.lower() in names:raise ValueError('Duplicate ZIP member')
            names.add(item.filename.lower())
        if z.testzip() is not None:raise ValueError('ZIP CRC error')
        output.mkdir(parents=True)
        for item in items:
            target=output/item.filename
            if output not in target.resolve().parents:raise ValueError('Extraction outside target')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(z.read(item))
    subprocess.run([sys.executable,'-B',str(output/'psv7_pynq/tools/check_project.py')],check=True)
    return {'passed':True,'directory':str(output),'sha256':actual,'hardware_accessed':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--sha256',required=True)
    a=p.parse_args();print(json.dumps(unpack(a.archive,a.output,a.sha256),indent=2))
