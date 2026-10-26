"""Same PCM, frozen and SPEED C; compute-only comparison, no device access."""
import argparse
import ctypes
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent))
from psv7_pynq.drivers.voice_runtime import ChemResult, ChemProfile, read_pcm

def compile_algorithm(source, headers, name):
    identity=hashlib.sha256(source.read_bytes()+b''.join(p.read_bytes() for p in headers)).hexdigest()
    folder=ROOT/'reports/voice_compare';folder.mkdir(parents=True,exist_ok=True)
    output=folder/(name+'_'+identity+('.dll' if os.name=='nt' else '.so'))
    if not output.exists():
        temporary=output.with_suffix(output.suffix+'.building')
        command=['gcc','-O2','-std=c99','-Wall','-Wextra','-Werror','-shared']
        if os.name!='nt':command.append('-fPIC')
        command+=['-I',str(source.parent),'-I',str(ROOT/'native'),str(source),'-lm','-o',str(temporary)]
        result=subprocess.run(command,capture_output=True,universal_newlines=True)
        if result.returncode:raise RuntimeError(result.stderr)
        temporary.replace(output)
    lib=ctypes.CDLL(str(output));ptr=ctypes.c_void_p;size=ctypes.c_size_t
    for fn,args,ret in [('chem22_predict_pcm',[ptr,size,ptr],ctypes.c_int),
                        ('chem22_frontend',[ptr,size,ptr],ctypes.c_int),('chem22_logits',[ptr,ptr],None)]:
        function=getattr(lib,fn);function.argtypes=args;function.restype=ret
    return lib,identity

def compare_pcm(file,input_source='UNDECLARED_PCM',repeats=3):
    if repeats not in range(1,11):raise ValueError('repeats must be 1..10')
    file=Path(file).resolve();pcm=read_pcm(file)
    if not 400<=pcm.size<=48000:raise ValueError('Use the segmented utterance.wav, 400..48000 samples')
    native=ROOT/'native';reference=ROOT/'assets/voice/reference_stage2'
    baseline,base_sha=compile_algorithm(reference/'chem22.c',[reference/'chem22.h',native/'chem22_weights.h'],'baseline')
    speed,speed_sha=compile_algorithm(native/'chem22.c',[native/'chem22.h',native/'chem22_weights.h',native/'speed_mel_sparse.h'],'speed')
    speed.chem22_last_profile.argtypes=[];speed.chem22_last_profile.restype=ctypes.POINTER(ChemProfile)
    arrays=[];decisions=[];timings=[];profile=None
    for lib in (baseline,speed):
        features=np.zeros(3840,np.float32);logits=np.zeros(24,np.float32);result=ChemResult()
        assert lib.chem22_frontend(pcm.ctypes.data,pcm.size,features.ctypes.data)==0
        lib.chem22_logits(features.ctypes.data,logits.ctypes.data)
        # Warm the library before recording compute-call wall measurements.
        assert lib.chem22_predict_pcm(pcm.ctypes.data,pcm.size,ctypes.byref(result))==0
        samples=[]
        for _ in range(repeats):
            start=time.perf_counter();assert lib.chem22_predict_pcm(pcm.ctypes.data,pcm.size,ctypes.byref(result))==0
            samples.append((time.perf_counter()-start)*1000)
        if lib is speed:
            current=speed.chem22_last_profile().contents
            profile={key:int(getattr(current,key)) for key,_ in ChemProfile._fields_}
            profile['clock']='PROCESS_CPU_CLOCK'
        arrays.append((features,logits));decisions.append({key:getattr(result,key) for key,_ in ChemResult._fields_})
        timings.append(samples)
    equal=np.array_equal(arrays[0][0],arrays[1][0]) and np.array_equal(arrays[0][1],arrays[1][1]) and decisions[0]==decisions[1]
    baseline_ms=statistics.median(timings[0]);speed_ms=statistics.median(timings[1])
    report={'passed':bool(equal),'input_file':str(file),'input_source':input_source,
            'pcm_file_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'samples':int(pcm.size),
            'algorithm_sha256':{'baseline':base_sha,'speed':speed_sha},
            'machine':platform.machine(),'system':platform.system(),'repeats':repeats,
            'features_max_abs':float(np.max(np.abs(arrays[0][0]-arrays[1][0]))),
            'logits_max_abs':float(np.max(np.abs(arrays[0][1]-arrays[1][1]))),'decisions':decisions,
            'baseline_call_wall_ms':timings[0],'speed_call_wall_ms':timings[1],
            'baseline_median_ms':baseline_ms,'speed_median_ms':speed_ms,
            'compute_call_wall_ratio':baseline_ms/speed_ms if speed_ms else None,
            'last_speed_profile':profile,'hardware_accessed':False,'overall_accuracy_measured':False,
            'scope':'same PCM and machine; warm compute calls; excludes audio, VAD, display, diagnostic recomputation; no whole-system speed claim'}
    folder=ROOT/'reports/voice_compare'
    output=folder/('comparison_'+str(time.time_ns())+'.json')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not equal:raise RuntimeError('SPEED differs on this PCM: '+str(output))
    print('VOICE_SAME_PCM_COMPARISON',str(output),flush=True)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pcm',required=True);parser.add_argument('--input-source',default='UNDECLARED_PCM')
    parser.add_argument('--repeats',type=int,default=3);args=parser.parse_args()
    print(json.dumps(compare_pcm(args.pcm,args.input_source,args.repeats),ensure_ascii=False,indent=2))
