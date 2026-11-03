"""Host-side functional checks for the submitted PREP C++ and voice recognition C."""
import argparse
import ctypes as ct
import json
from pathlib import Path
import shutil
import subprocess
import wave
import numpy as np

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    root = args.root.resolve()
    voice = root / 'src/ps/psv7_pynq'
    prep = root / 'src/hls/prep_only'
    def compile_lib(compiler, source, name):
        binary = out / (name + '.dll')
        subprocess.run([shutil.which(compiler) or compiler, '-O2', '-shared', str(source), '-o', str(binary), '-lm'], check=True)
        return ct.CDLL(str(binary))
    lib = compile_lib('g++', prep / 'prep_accel.cpp', 'prep')
    fn = lib.prep_only_accel
    fn.argtypes = [ct.c_void_p]*5 + [ct.c_uint32]*2
    # Constant neutral BGR pixels stay constant through resampling and gray conversion.
    # The normalized background equals the input, giving zero ink everywhere.
    arrays = [np.full(n,v,np.uint32) for n,v in [(691200,0x80808080),(147720,0xffffffff),(30240,0xffffffff),(60256,0xffffffff),(30240,0xffffffff)]]
    if fn(*(a.ctypes.data for a in arrays),960,0) != 0:
        raise RuntimeError('PREP mode 0 failed')
    detection=arrays[1].view(np.uint8)[:640*267]
    gray=arrays[2].view(np.uint8).reshape(224,540)
    if not (np.all(detection==128) and np.all(gray[:,:537]==128) and np.all(gray[:,537:]==0) and np.all(arrays[4]==0)):
        raise RuntimeError('PREP constant frame mismatch')
    lib = compile_lib('gcc', voice/'native/chem22.c', 'voice')
    class Result(ct.Structure):
        _fields_=[('class_id',ct.c_int),('raw_class',ct.c_int),('confidence',ct.c_float),('margin',ct.c_float),('reason',ct.c_int)]
    audio = voice/'assets/voice/selftest_ethene_training.wav'
    with wave.open(str(audio)) as stream:
        assert (stream.getframerate(),stream.getsampwidth(),stream.getnchannels())==(16000,2,1)
        pcm=np.frombuffer(stream.readframes(stream.getnframes()),dtype='<i2')
    result=Result()
    lib.chem22_predict_pcm.argtypes=[ct.c_void_p,ct.c_size_t,ct.POINTER(Result)]
    status=lib.chem22_predict_pcm(pcm.ctypes.data,len(pcm),ct.byref(result))
    summary={'prep_mode':0,'constant_input':128,'gray_pixels_checked':224*537,'detection_pixels_checked':640*267,'ink_expected':0,
             'wav':audio.name,'expected_class_id':0,'actual_class_id':result.class_id,'reason':result.reason,'confidence':result.confidence,'hardware_accessed':False}
    summary['passed']=status==0 and result.class_id==0 and result.reason==0
    print(json.dumps(summary,indent=2))
    (out/'sample_result.json').write_text(json.dumps(summary,indent=2)+'\n')
    if not summary['passed']: raise SystemExit(1)
if __name__=='__main__':main()
