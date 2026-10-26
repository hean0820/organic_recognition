"""Optional board replay of 20 complete CNN inputs; never publishes selection."""
import json,time
import numpy as np

def verify_unified_cnn(application):
    report={'passed':False,'hardware_accessed':True,'backend':'UNIFIED_HANDWRITTEN_RTL','vectors':[],
        'scope':'20 known frozen full inputs; logits + public Pool2/Pool3/hidden debug; not independent accuracy'}
    path=application.report_folder/('unified_cnn_acceptance_%s.json'%time.time_ns())
    try:
        with application.lock:
            application._check()
            if application.requests.status()['active'] or (application.voice_worker and application.voice_worker.is_alive()):
                raise RuntimeError('Finish/cancel active request before CNN replay')
            before=application.requests.status()
            with np.load(application.folder/'assets/golden_data.npz',allow_pickle=False) as golden:
                for i,image in enumerate(golden['inputs']):
                    actual=application._infer(np.ascontiguousarray(image.reshape(64,64)),None,diagnostics=True)
                    arrays=actual.pop('_diagnostic_arrays')
                    diff={key:int(np.count_nonzero(value!=golden[key][i])) for key,value in arrays.items()}
                    match=actual['predicted']==int(golden['predicted'][i])
                    report['vectors'].append({'case':i,'differences':diff,'decision_matches':match,'hardware':actual['hardware']})
                    if any(diff.values()) or not match:raise RuntimeError('Unified CNN differs at case '+str(i))
            if application.requests.status()!=before:raise RuntimeError('Request changed during replay')
            report.update(passed=True,request_unchanged=True,memory=application.memory.status())
    except Exception as error:
        report['error']=repr(error);raise
    finally:path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('UNIFIED_CNN_20_REPLAY_PASS',str(path),flush=True)
    return report
