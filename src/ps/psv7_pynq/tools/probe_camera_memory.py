"""Same parked live VDMA source: copy/check/render paths, without PL START."""
import json
import statistics
import time
from pathlib import Path
import numpy as np

def _metadata(buffer):
    return {'class':type(buffer).__name__,'shape':[int(n) for n in buffer.shape],
      'dtype':str(buffer.dtype),'bytes':int(buffer.nbytes),
      'owns_data':bool(buffer.flags.owndata),
      'base_class':None if buffer.base is None else type(buffer.base).__name__,
      'cacheable':None if getattr(buffer,'cacheable',None) is None else bool(buffer.cacheable),
      'coherent':None if getattr(buffer,'coherent',None) is None else bool(buffer.coherent),
      'virtual_address':int(buffer.ctypes.data),'physical_address':int(getattr(buffer,'physical_address',0)),
      'note':'Object flags reported by PYNQ; not an independent inspection of kernel page attributes'}

def probe_camera_memory(app,repeats=3,select_heap_policy=True):
    if not isinstance(repeats,int) or not 1<=repeats<=10:raise ValueError('Use 1..10 measured rounds')
    names=('HEAP_MEMCPY_CHECK','HEAP_FUSED_CHECK','EXPERIMENTAL_DIRECT_PREP')
    output=app.folder/'reports/camera_memory_probe'/('probe_'+str(time.time_ns()))
    output.mkdir(parents=True)
    report={'passed':False,'repeats':repeats,'warmup_rounds':1,'samples':[],'calls':{name:[] for name in names},
      'hardware_accessed':True,'PREP_or_CNN_START_issued':False,'new_hardware_owner_created':False,
      'scope':'One same completed/parked real VDMA slot, source invalidate before each trial, copy/check then native render to inactive display back buffer. No display present, PREP/CNN/FC, files or acquisition in measured times.',
      'selection_scope':'Only independent HEAP policies eligible. Three-round local sample is not a universal or end-to-end speed claim.'}
    try:
        with app.lock:
            app._check();before=app.requests.status()
            if before['mode']!='CAMERA' or before['active']:raise RuntimeError('Use inactive CAMERA mode')
            app.prep._idle()
            if app.prep.dma_owned:raise RuntimeError('PREP ownership unresolved')
            cnn_before={offset:int(app.cnn.read(offset)) for offset in (0,8,0x10,0x14,0x18,0x1c,0x20)}
            expected,slot=app.capture.acquire()
            source=app.capture.frames[slot]
            writer=(int(app.vdma.read(0x28))>>24)&31
            back=app.display.back();destination=app.display.frames[back]
            report.update(source_slot=slot,parked_writer_slot=writer,
              source_memory=_metadata(source),private_PREP_memory=_metadata(app.prep.frames[0]),
              heap_memory=_metadata(expected),display_back_memory=_metadata(destination),
              acquisition_timings_ms=dict(app.capture.last_timing))
            if app.last_frame is not None and np.shares_memory(app.last_frame,app.prep.frames[0]):
                app.last_frame=np.array(app.last_frame,copy=True,subok=False)
            app._sync_request()
            def guard():
                if app.requests.status()!=before:raise RuntimeError('Request changed; stop probe')
                current=(int(app.vdma.read(0x28))>>24)&31
                if current!=writer or current==slot:raise RuntimeError('Source VDMA slot is no longer frozen')
                if int(app.vdma.read(0x34))&0x8ff0:raise RuntimeError('Capture channel error')
                if int(app.vdma.read(4))&0x8ff0:raise RuntimeError('Display channel error')
            def trial(name,target=None):
                guard();started=time.perf_counter();source.invalidate()
                invalidate_ms=(time.perf_counter()-started)*1000;started=time.perf_counter()
                if name=='HEAP_MEMCPY_CHECK':
                    snapshot=np.array(source,copy=True,subok=False)
                    bad=app.page.validate_frame(snapshot)
                else:
                    snapshot=target if target is not None else np.empty((720,1280,3),np.uint8)
                    bad=app.page.copy_validate_frame(np.asarray(source),snapshot)
                copy_ms=(time.perf_counter()-started)*1000
                if bad:raise RuntimeError('Probe snapshot fails RGB565 check')
                started=time.perf_counter()
                app.page.render(snapshot,destination,back,app.fps10,app.frames_presented,0,0)
                render_ms=(time.perf_counter()-started)*1000
                # Validate after measuring render: a NumPy scan beforehand
                # would change the source-cache state of that render trial.
                equal=bool(np.array_equal(snapshot,expected));guard()
                if not equal:raise RuntimeError('Same frozen source bytes differ')
                return {'invalidate_ms':invalidate_ms,'copy_validate_ms':copy_ms,'render_ms':render_ms,
                        'copy_plus_render_ms':copy_ms+render_ms,'pixel_bytes_equal':equal,'violations':int(bad)}
            for index in range(repeats+1):
                order=names[index%3:]+names[:index%3]
                for name in order:
                    if name=='EXPERIMENTAL_DIRECT_PREP':
                        with app.prep.input_target() as target:row=trial(name,target)
                    else:row=trial(name)
                    row.update(policy=name,warmup=index==0,round=index)
                    report['samples'].append(row)
                    if index:report['calls'][name].append(row)
            guard()
            cnn_after={offset:int(app.cnn.read(offset)) for offset in cnn_before}
            if cnn_before!=cnn_after:raise RuntimeError('Probe changed CNN state/counters')
            report['CNN_state_unchanged']=True
            medians={name:{key:statistics.median(row[key] for row in rows)
                     for key in ('invalidate_ms','copy_validate_ms','render_ms','copy_plus_render_ms')}
                     for name,rows in report['calls'].items()}
            best=min(names[:2],key=lambda name:medians[name]['copy_plus_render_ms'])
            report.update(median_ms=medians,recommended_heap_policy=best,request_unchanged=True)
            if select_heap_policy:app.set_camera_snapshot_policy(best)
            report.update(selected_policy=app.capture.snapshot_policy,policy_applied=bool(select_heap_policy),passed=True)
    except Exception as error:
        report['error']=repr(error);raise
    finally:
        (output/'probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('CAMERA_MEMORY_PROBE',str(output/'probe.json'),flush=True)
    return report
