"""Create a new board ZIP, optionally using a freshly rebuilt bit/HWH pair."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def package(output,hardware_output=None):
    output=Path(output).resolve()
    if output.exists():raise FileExistsError('Choose a NEW runtime ZIP')
    with tempfile.TemporaryDirectory(prefix='chem_runtime_') as folder:
        work=Path(folder).resolve()
        ps=work/'psv7_pynq'
        shutil.copytree(ROOT/'src/ps/psv7_pynq',ps,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copytree(ROOT/'sim/ps_vs_rtl',work/'ps_vs_rtl',ignore=shutil.ignore_patterns('__pycache__','*.pyc','results'))
        if hardware_output:
            hardware_output=Path(hardware_output).resolve()
            for ext in ['bit','hwh']:
                source=hardware_output/('psv7_camera_audio.'+ext)
                if not source.is_file():raise FileNotFoundError(source)
                shutil.copyfile(source,ps/'overlay'/('psv7.'+ext))
            cfg=json.loads((ps/'project.json').read_text(encoding='utf-8'))
            for ext in ['bit','hwh']:cfg['sha256']['psv7.'+ext]=sha(ps/'overlay'/('psv7.'+ext))
            cfg['submission_rebuilt_overlay']={'source_output':str(hardware_output),'board_tested':False,'note':'Original acceptance records apply to the supplied reference pair, not automatically to this rebuild'}
            save(ps/'project.json',cfg)
        manifest=json.loads((ps/'release_manifest.json').read_text(encoding='utf-8'))
        editable=manifest['editable_notebooks']
        manifest['sha256']={p.relative_to(ps).as_posix():sha(p) for p in sorted(ps.rglob('*')) if p.is_file() and p.name!='release_manifest.json' and p.relative_to(ps).as_posix() not in editable}
        if hardware_output:manifest['rebuilt_overlay_board_tested']=False
        save(ps/'release_manifest.json',manifest)
        bench=work/'ps_vs_rtl'
        bm=json.loads((bench/'manifest.json').read_text(encoding='utf-8'))
        bm['runtime_sha256']={name:sha(ps/name) for name in bm['runtime_sha256']}
        save(bench/'manifest.json',bm)
        checked=subprocess.run([sys.executable,'-B',str(ps/'tools/check_project.py')],capture_output=True,text=True,encoding='utf-8',check=True)
        verification=json.loads(checked.stdout)
        output.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(work.rglob('*')):
                if not p.is_file() or '__pycache__' in p.parts:continue
                info=zipfile.ZipInfo(p.relative_to(work).as_posix(),(2026,10,22,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                info.create_system=3;info.external_attr=0o644<<16
                archive.writestr(info,p.read_bytes())
        with zipfile.ZipFile(output) as archive:
            if archive.testzip() is not None:raise ValueError('ZIP CRC verification failed')
            members=len(archive.infolist())
    return {'passed':True,'archive':str(output),'sha256':sha(output),'members':members,
            'project_check':verification,'rebuilt_pair_used':bool(hardware_output),'board_accessed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--hardware-output',type=Path,help='New build run/output directory; omit for supplied reference Overlay')
    args=parser.parse_args()
    print(json.dumps(package(args.output,args.hardware_output),indent=2))
