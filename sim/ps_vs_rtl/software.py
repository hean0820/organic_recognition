"""Compile and call a complete CPU-only integer CNN. No PYNQ import."""
import ctypes
import hashlib
import json
import platform
import shutil
import subprocess
import threading
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
TRACE_SPECS = [
    ('conv1_acc_int32', (24,64,64), '<i4'), ('conv1_relu_int8', (24,64,64), 'u1'),
    ('pool1_int8', (24,32,32), 'u1'),
    ('conv2_acc_int32', (48,32,32), '<i4'), ('conv2_relu_int8', (48,32,32), 'u1'),
    ('pool2_int8', (48,16,16), 'u1'),
    ('conv3_acc_int32', (48,16,16), '<i4'), ('conv3_relu_int8', (48,16,16), 'u1'),
    ('pool3_int8', (48,8,8), 'u1'),
    ('fc1_acc_int32', (48,), '<i4'), ('fc1_relu_int8', (48,), 'u1'),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_manifest():
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files_sha256'].items():
        if sha(ROOT/name)!=digest:
            raise ValueError('Benchmark source/asset hash mismatch: '+name)
    return manifest


def build_library(cc=None):
    manifest=checked_manifest()
    compiler=shutil.which(cc or 'gcc')
    if not compiler:
        raise RuntimeError('gcc is required to compile the same C baseline on this machine')
    machine=platform.machine().lower()
    flags=['-O3','-std=c99','-Wall','-Wextra','-Werror','-shared']
    if platform.system()!='Windows': flags+=['-fPIC']
    if machine in ('armv7l','armv7'):
        flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-ftree-vectorize']
    version=subprocess.check_output([compiler,'--version'],universal_newlines=True).splitlines()[0]
    target=subprocess.check_output([compiler,'-dumpmachine'],universal_newlines=True).strip()
    key=hashlib.sha256(json.dumps([sha(ROOT/'ps_cnn.c'),compiler,version,target,flags]).encode()).hexdigest()[:16]
    cache=ROOT/'results'/'build';cache.mkdir(parents=True,exist_ok=True)
    output=cache/('ps_cnn_'+key+('.dll' if platform.system()=='Windows' else '.so'))
    command=[compiler]+flags+[str(ROOT/'ps_cnn.c'),'-o',str(output)]
    if not output.exists():
        completed=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
        (cache/('compile_'+key+'.log')).write_text(completed.stdout,encoding='utf-8')
        if completed.returncode: raise RuntimeError('CPU baseline compilation failed: '+completed.stdout)
    return output,dict(compiler=compiler,version=version,target=target,flags=flags,
                       command=command,library_sha256=sha(output),baseline_threads=1,
                       source_sha256=manifest['files_sha256']['ps_cnn.c'])


class SoftwareCnn:
    def __init__(self,cc=None):
        self.manifest=checked_manifest()
        path,self.build=build_library(cc)
        self.lib=ctypes.CDLL(str(path));self.lock=threading.RLock();self.context=None
        ptr=ctypes.c_void_p;u32=ctypes.c_uint
        self.lib.pscnn_create.argtypes=[ptr,u32,ptr,u32,ptr,u32];self.lib.pscnn_create.restype=ptr
        self.lib.pscnn_destroy.argtypes=[ptr];self.lib.pscnn_destroy.restype=None
        self.lib.pscnn_infer.argtypes=[ptr,ptr,ptr];self.lib.pscnn_infer.restype=ctypes.c_int
        self.lib.pscnn_trace.argtypes=[ptr,ptr,ptr,ctypes.POINTER(ptr)];self.lib.pscnn_trace.restype=ctypes.c_int
        self.lib.pscnn_quantize.argtypes=[ctypes.c_int32,ctypes.c_int32];self.lib.pscnn_quantize.restype=ctypes.c_uint8
        with np.load(ROOT/'assets/model.npz',allow_pickle=False) as data:
            self.weights=data['weights'].copy();self.biases=data['biases'].copy();self.multipliers=data['multipliers'].copy()
        if self.weights.dtype!=np.int8 or self.weights.shape!=(179832,) or self.biases.dtype!=np.int32 or self.biases.shape!=(190,):
            raise ValueError('Invalid fixed CNN parameter shapes')
        if self.multipliers.dtype!=np.int32 or self.multipliers.tolist()!=[3561711,3526514,6503432,3488065]:
            raise ValueError('Fixed Q30 multipliers differ')
        self.context=self.lib.pscnn_create(self.weights.ctypes.data,self.weights.size,
                         self.biases.ctypes.data,self.biases.size,self.multipliers.ctypes.data,4)
        if not self.context: raise MemoryError('Could not create CPU CNN context')

    @staticmethod
    def validate(image):
        if not isinstance(image,np.ndarray) or image.dtype!=np.uint8 or image.shape!=(64,64) or not image.flags.c_contiguous:
            raise ValueError('Expected contiguous 64x64 uint8 input')

    def infer(self,image,trace=False):
        self.validate(image)
        with self.lock:
            if not self.context: raise RuntimeError('CPU context closed')
            logits=np.empty(22,dtype=np.int32)
            if trace:
                arrays=[np.empty(shape,dtype=dtype) for _,shape,dtype in TRACE_SPECS]
                pointers=(ctypes.c_void_p*len(arrays))(*(a.ctypes.data for a in arrays))
                rc=self.lib.pscnn_trace(self.context,image.ctypes.data,logits.ctypes.data,pointers)
            else:
                rc=self.lib.pscnn_infer(self.context,image.ctypes.data,logits.ctypes.data)
            if rc: raise RuntimeError('CPU CNN failed: '+str(rc))
            if trace:
                out={name:a for (name,_,_),a in zip(TRACE_SPECS,arrays)}
                out['fc2_logits_int32']=logits
                return out
            return logits

    def close(self):
        with self.lock:
            if self.context:
                self.lib.pscnn_destroy(self.context);self.context=None

    def __enter__(self): return self
    def __exit__(self,*args): self.close()


def validate_software(software,progress=True):
    """Untimed: every provided intermediate array plus logits and fast path."""
    with np.load(ROOT/'assets/vectors.npz',allow_pickle=False) as data:
        inputs=data['inputs'].copy();logits=data['logits'].copy()
    cases=software.manifest['cases']
    checked=0;values=0
    for i,case in enumerate(cases):
        image=np.ascontiguousarray(inputs[i])
        actual=software.infer(image,trace=True)
        for name,digest in case['trace_sha256'].items():
            array=actual[name]
            if hashlib.sha256(array.tobytes()).hexdigest()!=digest:
                raise AssertionError('CPU differs from frozen reference: '+case['name']+' '+name)
            checked+=1;values+=array.size
        if not np.array_equal(actual['fc2_logits_int32'],logits[i]) or not np.array_equal(software.infer(image),logits[i]):
            raise AssertionError('CPU normal/trace logits mismatch: '+case['name'])
        if progress and (i+1)%20==0: print('CPU_REFERENCE_CHECK',i+1,'/',len(cases),flush=True)
    quant_checks=0
    for m in [0,1,3561711,3526514,6503432,3488065,1<<29,1<<30,2147483647]:
        for a in [-2147483648,-129,-2,-1,0,1,2,3,126,127,128,129,2147483647]:
            expected=max(0,min(127,(a*m+(1<<29))//(1<<30))) if a>0 else 0
            if software.lib.pscnn_quantize(a,m)!=expected: raise AssertionError('Q30 boundary mismatch')
            quant_checks+=1
    return dict(passed=True,hardware_accessed=False,cases=len(cases),arrays_checked=checked,
                array_values_checked=values,quantization_boundary_checks=quant_checks,
                scope='CPU baseline correctness only; no board performance or new accuracy claim')
