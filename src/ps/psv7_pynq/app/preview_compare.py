"""One A/B/A preview test; no Overlay reload, new DMA owner or model changes."""
import csv,json,platform,time
from pathlib import Path
from .preview_profile import _window,_identity,_clocks,_process_memory
from ..drivers.camera_handoff import LEGACY,OVERLAP

def _json_scalar(value):
    from numpy import generic
    if isinstance(value,generic):return value.item()
    raise TypeError('Unsupported report value: '+type(value).__name__)

def evaluate(windows):
    result={'speedup_accepted':False,'reason':'incomplete_or_failed_windows'}
    if len(windows)!=3 or not all(w.get('passed') for w in windows):return result
    if [w.get('preview_policy') for w in windows]!=[LEGACY,OVERLAP,LEGACY]:return result
    a,b,c=windows;fa,fb,fc=[w['preview_submit_fps'] for w in windows]
    if not all(isinstance(f,(float,int)) and f>0 for f in (fa,fb,fc)):return result
    p=[w['statistics_ms']['interval_ms']['p95'] for w in windows]
    if any(v is None for v in p):return result
    drift=(max(fa,fc)/min(fa,fc)-1)*100
    gain=(fb/max(fa,fc)-1)*100
    review=any(w.get('diagnostic_overhead_review_required',True) for w in windows)
    model_rates=[w.get('model_present_fps',0) for w in windows]
    model_preserved=bool(min(model_rates)>0 and model_rates[1]>=.95*min(model_rates[0],model_rates[2]))
    accepted=bool(drift<=5 and gain>=5 and p[1]<=min(p[0],p[2]) and not review and model_preserved)
    return {'speedup_accepted':accepted,'baseline_fps':[fa,fc],'optimized_fps':fb,
            'gain_percent_vs_faster_baseline':gain,'baseline_drift_percent':drift,
            'p95_interval_ms':p,'model_present_fps':model_rates,'model_update_preserved':model_preserved,'instrumentation_review_required':review,
            'reason':'use_overlap' if accepted else 'keep_legacy_review_raw_data',
            'scope':'One fixed-scene A/B/A, descriptive results only; no zero-drop or long-term reliability claim.'}

def _validate_scene(before,after,clock0,clock1):
    errors=[]
    if not after['running'] or after['worker_error']:errors.append('preview_stopped_or_failed')
    if after['request']['active'] or _identity(before['request'],before['model3d'])!=_identity(after['request'],after['model3d']):errors.append('scene_or_request_changed')
    if before['memory']!=after['memory']:errors.append('BO_ownership_changed')
    if after['model3d'].get('render_errors')!=before['model3d'].get('render_errors'):errors.append('model_render_error')
    if any(int(after[k],0)&0x8FF1 for k in ('mm2s_status','s2mm_status')):errors.append('DMA_error_or_halt')
    if any(abs(clock0[k]-clock1[k])>.1 for k in clock0):errors.append('clock_changed')
    if any(abs(clock1[k]-100)>.1 for k in ('fclk0_mhz','fclk1_mhz')):errors.append('unexpected_PL_clock')
    return errors

def run(app):
    if platform.machine()!='armv7l':raise RuntimeError('A/B/A requires the actual Zynq board')
    from .config import verify_project,load_config
    identity=verify_project(app.folder);_,cfg=load_config(app.folder)
    if cfg['project_version']!='1.1.2-preview-overlap-candidate':raise RuntimeError('Use the paired 1.1.2 candidate')
    with app.lock:
        app._check()
        if not app.worker or not app.worker.is_alive():raise RuntimeError('Start preview first')
        if app.requests.status()['active'] or (app.voice_worker and app.voice_worker.is_alive()):raise RuntimeError('Wait for active request')
        if app.capture.snapshot_policy!='HEAP_MEMCPY_CHECK':raise RuntimeError('Keep baseline copy/check policy')
        if app.requests.status()['mode']!='CAMERA':app.set_mode('camera')
        app.select(4)
        if app.page.model_info()['paused']:app.pause_3d()
        before=app.status();clock0=_clocks();memory0=_process_memory()
    report={'passed':False,'speedup_accepted':False,'hardware_accessed':True,'board_tested':True,
        'identity':identity,'before':before,'clocks_before':clock0,'ps_memory_before':memory0,
        'hardware_sha256':{k:v for k,v in cfg['sha256'].items() if k.endswith(('.bit','.hwh'))},
        'scene':'CAMERA and manual class04 rotating 3D; manual display test, not recognition',
        'board_calendar_unverified':True,'windows':[],'selected_preview_policy':LEGACY,
        'functional_acceptance':'pending_user_short_check_and_normal_stop',
        'scope':'Only preview handoff policy varies; 720p, hardware, model, copy/check, renderer, clocks and per-window instrumentation held fixed.'}
    try:
        for index,policy in enumerate((LEGACY,OVERLAP,LEGACY)):
            app.set_preview_handoff_policy(policy)
            print('PREVIEW_COMPARE_WINDOW',index+1,'A' if policy==LEGACY else 'B',policy,'5s warmup + 20s sample',flush=True)
            window=_window(app,seconds=20,warmup=5)
            window.update(preview_policy=policy,window_index=index,hardware_accessed=True)
            report['windows'].append(window)
            errors=[]
            try:
                with app.lock:
                    window['status_after']=app.status();window['clocks_after']=_clocks()
                errors=_validate_scene(before,window['status_after'],clock0,window['clocks_after'])
            except Exception as e:errors.append('post_window_snapshot_failed: '+repr(e))
            expected_code=int(policy==OVERLAP);columns={k:i for i,k in enumerate(window['fields'])}
            for row in window['rows']:
                if (row[columns['preview_policy_code']]!=expected_code
                    or row[columns['fresh_events_required']]!=2
                    or row[columns['writer_target_slot']]==row[columns['source_slot']]):
                    errors.append('actual_policy_or_frame_ownership_mismatch');break
            if len(window['rows'])>1 and window['observed_ack_span_ms']>0:
                window['model_present_fps']=(window['rows'][-1][columns['model_presents']]-window['rows'][0][columns['model_presents']])*1000/window['observed_ack_span_ms']
            else:window['model_present_fps']=0
            if errors:window.update(passed=False,validation_errors=errors)
            if not window['passed']:raise RuntimeError('Window invalid; keep raw evidence, do not auto-retry')
        report['summary']=evaluate(report['windows'])
        report['passed']=True
        report['speedup_accepted']=report['summary']['speedup_accepted']
    except BaseException as e:report['error']=repr(e)
    finally:
        # Pure software selector only; no hardware reset/free, even on failure.
        with app.lock:
            app.preview_handoff_policy=OVERLAP if report['passed'] and report['speedup_accepted'] else LEGACY
            report['selected_preview_policy']=app.preview_handoff_policy
    try:
        with app.lock:
            report['after']=app.status();report['clocks_after']=_clocks();report['ps_memory_after']=_process_memory()
    except Exception as e:
        report.update(passed=False,speedup_accepted=False,final_snapshot_error=repr(e))
        with app.lock:app.preview_handoff_policy=LEGACY;report['selected_preview_policy']=LEGACY
    folder=Path(app.folder)/'reports/preview_overlap'/('compare_'+str(time.time_ns()))
    folder.mkdir(parents=True,exist_ok=False);report['report_directory']=str(folder)
    (folder/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False,default=_json_scalar)+'\n',encoding='utf-8')
    for window in report['windows']:
        with (folder/('window_'+str(window['window_index'])+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.writer(f);writer.writerow(window['fields']);writer.writerows(window['rows'])
    print('PREVIEW_COMPARE_DONE',json.dumps({k:report.get(k) for k in ('passed','speedup_accepted','selected_preview_policy','summary','report_directory')},ensure_ascii=False,default=_json_scalar),flush=True)
    return report
