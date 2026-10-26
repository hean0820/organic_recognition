"""Same saved BGR frame and same hardware; no acquisition/UI/publication."""
import hashlib
import json
import statistics
import time
from pathlib import Path
import numpy as np
from ..drivers.reference_pipeline import REPORT_FIELDS

def compare_camera_pipeline(app,frame_file=None,repeats=3):
    if not isinstance(repeats,int) or not 1<=repeats<=10:raise ValueError('Use 1..10 measured pairs')
    path=Path(frame_file) if frame_file else app.folder/'assets/reference/frame_bgr.npy'
    frame=np.load(path,allow_pickle=False)
    if app.page.validate_frame(frame):raise ValueError('Saved source fails RGB565 format')
    output=app.folder/'reports/camera_pipeline_compare'/('comparison_'+str(time.time_ns()))
    output.mkdir(parents=True)
    report={'passed':False,'input_source':'SAVED_BGR_PIPELINE_COMPARISON','input_file':str(path),
      'input_file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
      'baseline_source_sha256':hashlib.sha256((app.folder/'assets/camera_pipeline_reference/preprocess_0_7_0.c').read_bytes()).hexdigest(),
      'repeats':repeats,'warmup_pairs':1,'calls':{'baseline':[],'optimized':[]},'numerical':[],
      'hardware_accessed':True,'new_hardware_owner_created':False,'overall_accuracy_measured':False,
      'scope':'Same saved frame, normal RAM snapshot copy/validation, same PL PREP/native postprocess/native CNN transfer/PL FC and ACK. Excludes fresh camera wait/invalidate, UI, file saving and initial display-frame preservation. No whole-system or live acquisition speed claim.'}
    reference=None;last_arrays={}
    try:
        with app.lock:
            app._check();before=app.requests.status()
            if before['mode']!='CAMERA' or before['active']:raise RuntimeError('Use inactive CAMERA mode')
            # Last live snapshot may alias the private PREP input. Preserve the
            # current preview source before benchmarking that workspace.
            if app.last_frame is not None:app.last_frame=np.array(app.last_frame,copy=True,subok=False)
            for index in range(repeats+1):
                for mode in (('baseline','optimized') if index%2==0 else ('optimized','baseline')):
                    if app.requests.status()!=before:raise RuntimeError('Request changed; stop comparison')
                    timings={};started=time.perf_counter();phase=started
                    if mode=='baseline' or app.capture.snapshot_policy=='HEAP_MEMCPY_CHECK':
                        snapshot=np.array(frame,copy=True,subok=False)
                        if app.page.validate_frame(snapshot):raise RuntimeError('Reference copy format failure')
                        timings['snapshot_copy_validate_ms']=(time.perf_counter()-phase)*1000;phase=time.perf_counter()
                        filtered,pl=app.prep.run(snapshot)
                        timings['prep_call_ms']=(time.perf_counter()-phase)*1000;phase=time.perf_counter()
                        image,raw,prep=app.page.postprocess(filtered,reference=mode=='baseline')
                    else:
                        snapshot=np.empty_like(frame)
                        if app.page.copy_validate_frame(frame,snapshot):raise RuntimeError('Fused copy format failure')
                        timings['snapshot_copy_validate_ms']=(time.perf_counter()-phase)*1000;phase=time.perf_counter()
                        filtered,pl=app.prep.run(snapshot)
                        timings['prep_call_ms']=(time.perf_counter()-phase)*1000;phase=time.perf_counter()
                        image,raw,prep=app.page.postprocess(filtered)
                    timings['postprocess_call_ms']=(time.perf_counter()-phase)*1000;phase=time.perf_counter()
                    if prep['code']!=0:raise RuntimeError('Comparison input PREP rejected: '+prep['code_name'])
                    cnn=app._infer(image,None,diagnostics=True);arrays=cnn.pop('_diagnostic_arrays')
                    timings['cnn_fc_ack_ms']=(time.perf_counter()-phase)*1000
                    total_ms=(time.perf_counter()-started)*1000
                    if reference is None:reference=(image.copy(),dict(prep),arrays,cnn['predicted'])
                    differences={key:int(np.max(np.abs(value.astype(np.int64)-reference[2][key].astype(np.int64))))
                                 for key,value in arrays.items()}
                    record={'mode':mode,'warmup':index==0,
                      'input64_max_abs':int(np.max(np.abs(image.astype(np.int16)-reference[0].astype(np.int16)))),
                      'prep_fields_differences':[key for key in REPORT_FIELDS if prep[key]!=reference[1][key]],
                      'cnn_arrays_max_abs':differences,'predicted':cnn['predicted'],
                      'decision_equal':cnn['predicted']==reference[3]}
                    report['numerical'].append(record)
                    if record['input64_max_abs'] or record['prep_fields_differences'] or any(differences.values()) or not record['decision_equal']:
                        raise RuntimeError('Pipeline numerical mismatch: '+repr(record))
                    call={'pipeline_wall_ms':total_ms,'phase_wall_ms':timings,'pl':pl,'prep':prep,'cnn':cnn}
                    if index:report['calls'][mode].append(call)
                    last_arrays[mode]=dict(input64=image.copy(),**arrays)
            if app.requests.status()!=before:raise RuntimeError('Comparison changed application request')
            report['request_unchanged']=True
        medians={mode:statistics.median(row['pipeline_wall_ms'] for row in calls) for mode,calls in report['calls'].items()}
        report.update(passed=True,pipeline_median_ms=medians,baseline_over_optimized_ratio=medians['baseline']/medians['optimized'],optimized_snapshot_policy=app.capture.snapshot_policy)
        for mode,arrays in last_arrays.items():np.savez_compressed(output/(mode+'.npz'),**arrays)
    except Exception as error:
        report['error']=repr(error);raise
    finally:
        (output/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('CAMERA_PIPELINE_COMPARISON',str(output/'comparison.json'),flush=True)
    return report
