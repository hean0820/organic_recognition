"""Verify frozen parameters, restore vendor paths, then run Vivado 2020.2."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from prepare_workspace import ROOT,prepare

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vivado',required=True,help='Vivado 2020.2 executable or vivado.bat')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--prepare-only',action='store_true',help='No Vivado execution; does not confirm synthesis')
    args=parser.parse_args()
    out=args.output.resolve()
    if out.exists():raise FileExistsError('Choose a new build output directory')
    if out==ROOT or ROOT in out.parents:raise ValueError('Build outside the submission directory')
    subprocess.run([sys.executable,'-B',str(ROOT/'sim/check_parameters.py')],check=True)
    if not args.prepare_only:
        executable=shutil.which(args.vivado)
        if not executable:raise FileNotFoundError('Vivado 2020.2 executable not found: '+args.vivado)
    out.mkdir(parents=True)
    prepared=prepare(out/'sources')
    (out/'preparation.json').write_text(json.dumps(prepared,indent=2)+'\n',encoding='utf-8')
    if args.prepare_only:
        print(json.dumps({'prepared':True,'synthesis_executed':False,'output':str(out)},indent=2));return
    command=[executable,'-mode','batch','-source',str(out/'sources/vivado/build_repro.tcl'),'-tclargs',str(out/'run')]
    env=os.environ.copy();env['PSV7_PYTHON']=sys.executable
    if os.name=='nt' and str(executable).lower().endswith(('.bat','.cmd')):
        if any(any(c in value for c in '&|<>^%!\r\n') for value in command):raise ValueError('Use plain build/tool paths')
        command=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c',subprocess.list2cmdline(command)]
    subprocess.run(command,cwd=out,env=env,check=True)
    print(json.dumps({'built':True,'output':str(out/'run/output'),'board_tested':False},indent=2))

if __name__=='__main__':main()
