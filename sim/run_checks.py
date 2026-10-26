"""Run saved-input verification into a NEW external result directory."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sim'))

def checks(output,with_cpu=False):
    output=Path(output).resolve()
    if output.exists():raise FileExistsError('Choose a new verification directory')
    if output==ROOT or ROOT in output.parents:raise ValueError('Store new results outside the submission repository')
    output.mkdir(parents=True)
    from check_parameters import check
    from verify_cnn3_package import verify
    from audit_board_results import audit
    result={'passed':False,'python':sys.version,'platform':platform.platform(),'hardware_accessed':False,'new_synthesis_executed':False}
    try:
        result['parameter_identity']=check(ROOT)
        result['integer_reference']=verify(ROOT/'data/model/final_parameters')
        result['saved_board_audit']=audit()
        completed=subprocess.run([sys.executable,'-B',str(ROOT/'src/ps/psv7_pynq/tools/check_project.py')],capture_output=True,text=True,encoding='utf-8',check=True)
        result['ps_package']=json.loads(completed.stdout)
        completed=subprocess.run([sys.executable,'-B',str(ROOT/'skill/scripts/validate_overlay.py'),'--profile',str(ROOT/'skill/profiles/current.json'),'--root',str(ROOT/'src/ps/psv7_pynq')],capture_output=True,text=True,encoding='utf-8',check=True)
        result['overlay_profile']=json.loads(completed.stdout)
        if with_cpu:
            import shutil
            # The original CPU reference compiler writes a cache beside its source.
            # Run a private copy so the submission tree remains immutable.
            cpu_dir=output/'cpu_reference'
            shutil.copytree(ROOT/'sim/ps_vs_rtl',cpu_dir)
            command=[sys.executable,'-B','-c',
                'import json; from software import SoftwareCnn,validate_software; '
                'cpu=SoftwareCnn(); '
                'result=validate_software(cpu,progress=False); '
                'result["build"]=cpu.build; cpu.close(); print(json.dumps(result))']
            completed=subprocess.run(command,cwd=cpu_dir,capture_output=True,text=True,encoding='utf-8',check=True)
            result['cpu_reference']=json.loads(completed.stdout)
        result['passed']=True
    except Exception as error:
        result['error']=repr(error)
        raise
    finally:
        (output/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--with-cpu',action='store_true',help='Also compile GCC CPU reference and check 79 frozen cases')
    a=parser.parse_args();print(json.dumps(checks(a.output,a.with_cpu),ensure_ascii=False,indent=2))
