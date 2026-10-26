"""Twenty-second preview diagnosis. Never starts/reloads hardware or allocates BOs.

Only wraps existing methods while their one preview owner holds app.lock.
Original capture/present/step code is called; every other native render is the
original uninstrumented export. All wrappers are removed before file I/O.
"""
import csv
import ctypes
import hashlib
import json
import math
import platform
import time
from pathlib import Path
import numpy as np

FIELDS=('step_start_ns','present_ack_ns','step_end_ns','frame_number','detailed',
        'capture_total_ms','freeze_wait_ms','invalidate_ms','snapshot_copy_validate_ms',
        'capture_other_ms','render_total_ms','background_camera_ms','model_update_ms',
        'ui_panels_ms','model_blit_ms','native_total_ms','display_present_ms',
        'step_total_ms','step_other_ms','model_renders','model_presents','display_slot',
        'source_slot','interval_ms','between_steps_ms','preview_policy_code','fresh_events_required','writer_target_slot')
IDX={k:i for i,k in enumerate(FIELDS)}
CAPACITY=4096
CAPTURE_POLICY='HEAP_MEMCPY_CHECK'
PREVIEW_HANDOFF='LEGACY_TWO_EVENTS_THEN_PARK'

def _summary(values):
    a=np.asarray(values,dtype=np.float64);a=a[np.isfinite(a)]
    if not len(a):return {'count':0}
    return {'count':int(len(a)),'mean':float(a.mean()),'median':float(np.median(a)),
            'p95':float(np.percentile(a,95)) if len(a)>=20 else None,
            'max':float(a.max())}

def _identity(request,model):
    return tuple(request.get(k) for k in ('mode','mode_epoch','request_epoch','request_id','selection_seq','class_id','valid'))+(model.get('active'),model.get('class_id'),model.get('paused'))

class _Probe:
    def __init__(self,app):
        self.app=app;self.rows=np.full((CAPACITY,len(FIELDS)),np.nan)
        self.count=0;self.issue=None;self.armed=False;self.deadline_ns=0
        self.buf=(ctypes.c_uint64*5)();self.native=None;self.saved=[]
        self.in_step=False;self.detailed=False;self.measure={}

    def _replace(self,obj,name,method):
        self.saved.append((obj,name,name in obj.__dict__,obj.__dict__.get(name)))
        setattr(obj,name,method)

    def attach(self):
        a=self.app
        with a.lock:
            a._check()
            if getattr(a,'_preview_diagnostic_owner',None) is not None:raise RuntimeError('Preview diagnostics already active')
            request=a.requests.status();model=a.page.model_info()
            if request['mode']!='CAMERA' or request['active'] or not model['active'] or model['paused']:
                raise RuntimeError('Need inactive CAMERA mode and a rotating selected model')
            self.expected=_identity(request,model)
            self.expected_policy=a.preview_handoff_policy
            self.native=a.page.lib.psv7_render_profiled
            self.native.argtypes=[ctypes.c_void_p]*3+[ctypes.c_uint32]*5+[ctypes.POINTER(ctypes.c_uint64)]
            self.native.restype=ctypes.c_int
            step=a._step;render=a.page.render;present=a.display.present;capture=a.capture.acquire
            def wrapped_capture(*args,**kwargs):
                if not self.in_step:return capture(*args,**kwargs)
                t=time.perf_counter_ns();value=capture(*args,**kwargs)
                self.measure['capture_total_ms']=(time.perf_counter_ns()-t)/1e6
                timings=a.capture.last_timing
                for key in ('freeze_wait_ms','invalidate_ms','snapshot_copy_validate_ms'):
                    self.measure[key]=float(timings[key])
                self.measure['source_slot']=int(value[1])
                actual=timings.get('handoff_policy')
                self.measure['preview_policy_code']=int(actual=='OVERLAP_SECOND_EVENT_WITH_PARK')
                self.measure['fresh_events_required']=timings.get('fresh_events_required',-1)
                self.measure['writer_target_slot']=timings.get('writer_target_slot',-1)
                if (actual!=self.expected_policy or timings.get('fresh_events_required')!=2
                    or timings.get('writer_target_slot')==int(value[1])):
                    self.issue='Actual capture policy/frame ownership evidence mismatch'

                return value
            def wrapped_render(source,destination,index,fps,frames,read_error,write_error):
                if not self.in_step:return render(source,destination,index,fps,frames,read_error,write_error)
                t=time.perf_counter_ns()
                if self.detailed:
                    code=self.native(a.page.handle,source.ctypes.data,destination.ctypes.data,index,fps,frames,read_error,write_error,self.buf)
                    if code<0:raise RuntimeError('Profiled native render failed: '+str(code))
                    for i,key in enumerate(('background_camera_ms','model_update_ms','ui_panels_ms','model_blit_ms','native_total_ms')):
                        self.measure[key]=self.buf[i]/1000.0
                else:render(source,destination,index,fps,frames,read_error,write_error)
                self.measure['render_total_ms']=(time.perf_counter_ns()-t)/1e6
            def wrapped_present(index):
                if not self.in_step:return present(index)
                t=time.perf_counter_ns();value=present(index);done=time.perf_counter_ns()
                self.measure.update(display_present_ms=(done-t)/1e6,present_ack_ns=done,display_slot=index)
                return value
            def wrapped_step():
                t=time.perf_counter_ns()
                if not self.armed or t>=self.deadline_ns or self.issue:return step()
                if self.count>=CAPACITY:
                    self.issue='Sample buffer full; no frames discarded from report';return step()
                # Diagnostic bookkeeping must not inject an exception into the worker.
                try:
                    req=a.requests.status();mod=a.page.model_info()
                    if req['active'] or _identity(req,mod)!=self.expected:
                        self.issue='Scene/request changed during sampling';return step()
                except Exception as e:
                    self.issue='Diagnostic state read failed: '+repr(e);return step()
                self.measure={};self.detailed=bool(self.count%2);self.in_step=True
                try:
                    value=step()
                finally:self.in_step=False
                done=time.perf_counter_ns()
                try:
                    m=self.measure;model=a.page.model_info();j=self.count
                    m.update(step_start_ns=t,step_end_ns=done,frame_number=a.frames_presented,
                             detailed=int(self.detailed),step_total_ms=(done-t)/1e6,
                             model_renders=model['renders'],model_presents=model['presents'])
                    m['capture_other_ms']=m['capture_total_ms']-sum(m[k] for k in ('freeze_wait_ms','invalidate_ms','snapshot_copy_validate_ms'))
                    m['step_other_ms']=m['step_total_ms']-sum(m[k] for k in ('capture_total_ms','render_total_ms','display_present_ms'))
                    if j:
                        m['interval_ms']=(m['present_ack_ns']-self.rows[j-1,IDX['present_ack_ns']])/1e6
                        m['between_steps_ms']=(t-self.rows[j-1,IDX['step_end_ns']])/1e6
                    for key,v in m.items():self.rows[j,IDX[key]]=v
                    self.count+=1
                except Exception as e:self.issue='Diagnostic bookkeeping failed: '+repr(e)
                return value
            a._preview_diagnostic_owner=self
            try:
                self._replace(a.capture,'acquire',wrapped_capture)
                self._replace(a.page,'render',wrapped_render)
                self._replace(a.display,'present',wrapped_present)
                self._replace(a,'_step',wrapped_step)
            except BaseException:
                self.detach();raise

    def detach(self):
        with self.app.lock:
            for obj,name,had,value in reversed(self.saved):
                if had:setattr(obj,name,value)
                else:delattr(obj,name)
            self.saved=[]
            if getattr(self.app,'_preview_diagnostic_owner',None) is self:delattr(self.app,'_preview_diagnostic_owner')

    def arm(self,seconds):
        with self.app.lock:
            self.start_ns=time.perf_counter_ns();self.deadline_ns=self.start_ns+int(seconds*1e9)
            self.start_frames=self.app.frames_presented;self.armed=True

def _window(app,seconds=20.0,warmup=5.0):
    probe=_Probe(app);error=None
    # Preallocated raw storage ~0.75MiB, no PYNQ allocation or new DMA owner.
    try:
        probe.attach()
        if app.stop_event.wait(warmup):raise RuntimeError('Application stopped during warmup')
        probe.arm(seconds)
        while time.perf_counter_ns()<probe.deadline_ns and not probe.issue:
            if app.stop_event.wait(min(.1,max(0,(probe.deadline_ns-time.perf_counter_ns())/1e9))):
                raise RuntimeError('Application stopped during sampling: '+repr(app.worker_error))
    except BaseException as e:error=repr(e)
    finally:probe.detach()
    if probe.issue:error=probe.issue if error is None else error+'; '+probe.issue
    data=probe.rows[:probe.count].copy()
    good=probe.count>=21 and error is None
    groups={key:_summary(data[:,IDX[key]]) for key in FIELDS if key.endswith('_ms')}
    if len(data)>1 and not np.all(np.diff(data[:,IDX['frame_number']])==1):
        good=False;error='Preview frame counter is not continuous'
    intervals=data[:,IDX['interval_ms']];intervals=intervals[np.isfinite(intervals)]
    elapsed_ms=(data[-1,IDX['present_ack_ns']]-data[0,IDX['present_ack_ns']])/1e6 if len(data)>1 else 0
    fps=(len(data)-1)*1000/elapsed_ms if elapsed_ms>0 else None
    control=_summary(data[data[:,IDX['detailed']]==0,IDX['step_total_ms']])
    detailed=_summary(data[data[:,IDX['detailed']]==1,IDX['step_total_ms']])
    ratio=(detailed['median']/control['median']-1)*100 if control.get('median',0)>0 and detailed.get('median') else None
    return {'passed':good,'error':error,'hardware_accessed':False,
            'sample_count':len(data),'requested_seconds':seconds,'warmup_seconds':warmup,
            'observed_ack_span_ms':elapsed_ms,'preview_submit_fps':fps,
            'statistics_ms':groups,'alternating_original_native':control,
            'alternating_profiled_native':detailed,'detail_median_step_change_percent':ratio,
            'diagnostic_overhead_review_required':ratio is None or abs(ratio)>5,
            'overhead_scope':'Alternating native path comparison is a drift/confounding screen, not a calibrated overhead measurement; common Python bookkeeping is not isolated.',
            'raw_storage_bytes':probe.rows.nbytes,
            'scope':'Successful preview display park ACKs; excludes startup, warmup and JSON/CSV saves. Not sensor FPS, zero-drop proof or physical scanout latency.',
            'rows':[[float(v) if math.isfinite(v) else None for v in row] for row in data],
            'fields':list(FIELDS),'wrappers_restored':not probe.saved and not hasattr(app,'_preview_diagnostic_owner')}

def _clocks():
    from pynq.ps import _ClocksZynq
    c=_ClocksZynq(ref_clk_mhz=33.333333)
    return {'cpu_mhz':float(c.get_cpu_mhz()),'fclk0_mhz':float(c.get_pl_clk(0)),'fclk1_mhz':float(c.get_pl_clk(1))}

def _process_memory():
    file=Path('/proc/self/status')
    if not file.is_file():return {'available':False}
    return {line.split(':',1)[0]+'_kib':int(line.split()[1]) for line in file.read_text().splitlines()
            if line.startswith(('VmRSS:','VmHWM:','VmData:'))}

def run(app):
    if platform.machine()!='armv7l':raise RuntimeError('Diagnostic run requires the actual Zynq board')
    from .config import verify_project,load_config
    identity=verify_project(app.folder);_,cfg=load_config(app.folder)
    if cfg['project_version']!='1.1.1-preview-profile-candidate':raise RuntimeError('Use the paired diagnostic runtime')
    with app.lock:
        app._check()
        if not app.worker or not app.worker.is_alive():raise RuntimeError('Start preview first')
        if app.requests.status()['active'] or (app.voice_worker and app.voice_worker.is_alive()):raise RuntimeError('A request is active; wait for it to finish')
        if app.capture.snapshot_policy!=CAPTURE_POLICY:raise RuntimeError('Baseline snapshot policy changed')
        if app.requests.status()['mode']!='CAMERA':app.set_mode('camera')
        app.select(4) # fixed ethanol model, MANUAL display test, not recognition.
        if app.page.model_info()['paused']:app.pause_3d()
        before=app.status();clock_before=_clocks();ps_memory_before=_process_memory()
    print('PREVIEW_PROFILE: manual class04, rotating 3D; wait 5s warmup + 20s sample. Do not operate the page.',flush=True)
    result=_window(app)
    with app.lock:
        after=app.status();clock_after=_clocks();ps_memory_after=_process_memory()
    result.update(hardware_accessed=True,board_tested=True,identity=identity,
        hardware_sha256={k:v for k,v in cfg['sha256'].items() if k.endswith(('.bit','.hwh'))},
        before=before,after=after,clocks_before=clock_before,clocks_after=clock_after,
        ps_memory_before=ps_memory_before,ps_memory_after=ps_memory_after,
        scene='CAMERA; manually selected class04 ethanol; rotating 3D; NOT a recognition result',
        board_calendar_unverified=True,experiment_date_source='Use PC receipt date; board calendar may be wrong')
    problems=[]
    if after['worker_error'] or not after['running']:problems.append('Preview worker stopped or failed')
    if after['request']['active'] or after['request']['mode']!='CAMERA':problems.append('Scene changed')
    if _identity(before['request'],before['model3d'])!=_identity(after['request'],after['model3d']):problems.append('Model/request identity changed')
    for key in ('cpu_mhz','fclk0_mhz','fclk1_mhz'):
        if abs(clock_before[key]-clock_after[key])>.1:problems.append('Clock changed: '+key)
    for key in ('fclk0_mhz','fclk1_mhz'):
        if abs(clock_before[key]-100)>.1:problems.append('Unexpected clock: '+key)
    if before['memory']!=after['memory']:problems.append('Memory ownership changed')
    for status in ('mm2s_status','s2mm_status'):
        if int(after[status],0)&0x8FF1:problems.append('Video DMA error/halt: '+status)
    if problems:result.update(passed=False,validation_errors=problems)
    folder=Path(app.folder)/'reports/preview_profile'/('profile_'+str(time.time_ns()))
    folder.mkdir(parents=True,exist_ok=False);result['report_directory']=str(folder)
    (folder/'preview_profile.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    with (folder/'frames.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(FIELDS);w.writerows(result['rows'])
    print('PREVIEW_PROFILE_DONE',json.dumps({k:result[k] for k in ('passed','sample_count','preview_submit_fps','diagnostic_overhead_review_required','report_directory')},ensure_ascii=False),flush=True)
    return result
