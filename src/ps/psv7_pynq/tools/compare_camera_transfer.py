"""Same saved input, same existing app/mapping/PL FC; no new hardware owner."""
import hashlib
import json
import statistics
import time
from pathlib import Path
import numpy as np
from ..drivers.cnn_native_io import PythonReferenceCnnTransfer

def compare_camera_transfer(app,input_file,repeats=3):
    if not isinstance(repeats,int) or not 1<=repeats<=10:
        raise ValueError('Use 1..10 comparison pairs')
    path=Path(input_file).resolve()
    image=np.load(path,allow_pickle=False)
    # Do not silently convert the benchmark input or use a live camera frame.
    app.cnn_io.validate_input(image)
    input_sha=hashlib.sha256(path.read_bytes()).hexdigest()
    modes={'baseline':PythonReferenceCnnTransfer(app.cnn),'native':app.cnn_io}
    calls={key:[] for key in modes};numerical=[];reference=None;outputs={}
    with app.lock:
        app._check()
        before=app.requests.status()
        if before['mode']!='CAMERA' or before['active']:
            raise RuntimeError('Compare only while existing app is in inactive CAMERA mode')
        for index in range(repeats+1):
            # One warm pair; alternate measured order to reduce ordering bias.
            order=('baseline','native') if index%2==0 else ('native','baseline')
            for mode in order:
                if app.requests.status()['revision']!=before['revision']:
                    raise RuntimeError('Request changed during compute comparison; stop benchmark')
                result=app._infer(image,None,transfer=modes[mode],diagnostics=True)
                arrays=result.pop('_diagnostic_arrays')
                if reference is None:reference=arrays
                differences={key:int(np.max(np.abs(value.astype(np.int64)-reference[key].astype(np.int64))))
                             for key,value in arrays.items()}
                numerical.append({'mode':mode,'warmup':index==0,'max_abs':differences,
                                  'predicted':result['predicted']})
                if any(differences.values()):
                    raise RuntimeError('Same input numerical mismatch: '+repr(differences))
                if index:calls[mode].append(result)
                outputs[mode]=arrays
        after=app.requests.status()
        if after!=before:raise RuntimeError('Comparison must not publish or change application requests')
    medians={key:statistics.median(row['inference_wall_ms'] for row in rows) for key,rows in calls.items()}
    report={'passed':True,'input_file':str(path),'input_file_sha256':input_sha,
            'input_source':'SAVED_CAMERA_INPUT64_COMPUTE_COMPARISON','samples':int(image.size),
            'repeats':repeats,'warmup_pairs':1,'calls':calls,'numerical':numerical,
            'inference_median_ms':medians,
            'baseline_over_native_ratio':medians['baseline']/medians['native'],
            'decision_equal':len({row['predicted'] for row in numerical})==1,
            'hardware_accessed':True,'new_hardware_owner_created':False,
            'request_unchanged':True,'overall_accuracy_measured':False,
            'scope':'Same saved input64, same CNN and PL FC; inference setup/transfers/readback/compute/cache. Excludes live acquisition, PREP, UI, diagnostic files and final CNN ACK. No whole-system or teammate speed claim.'}
    if not report['decision_equal']:raise RuntimeError('Same input decision mismatch')
    output=app.folder/'reports/camera_compare'/('comparison_'+str(time.time_ns()))
    output.mkdir(parents=True)
    for mode,arrays in outputs.items():np.savez_compressed(output/(mode+'.npz'),**arrays)
    (output/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('CAMERA_SAME_INPUT_COMPARISON',str(output/'comparison.json'),flush=True)
    return report
