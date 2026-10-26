"""Focused readback after original web work; never start or change hardware."""
import hashlib
import json
from datetime import datetime, timezone

from ..app.config import ACCEPTED_CAMERA_HANDOFF


def collect_entry_state(session, mode, expected_name=None, expect_empty=False):
    if mode not in ('CAMERA','VOICE'):
        raise ValueError('Expected mode must be CAMERA or VOICE')
    if not expect_empty and (not isinstance(expected_name,str) or not expected_name):
        raise ValueError('Declare the actual input label before comparing a result')
    app, service = session.app, session.host_service
    if app is None or service is None:
        raise RuntimeError('Use this running session and host; do not create a second owner')
    web = service.controller.snapshot()
    if web['busy']:
        raise RuntimeError('Wait for current work to finish before collecting entry evidence')
    if not app.lock.acquire(timeout=2):
        raise RuntimeError('Application busy; preserve current session and collect after work finishes')
    try:
        board = app.status()
        if board['request'] != web['request']:
            raise RuntimeError('Request changed during snapshot; collect after it settles')
        request, selection, model = web['request'], web['selection'], board['model3d']
        checks = {'same_mode':request['mode']==mode,
                  'automatic_policy':board['camera_handoff_policy']==session.config['camera_handoff_default']==ACCEPTED_CAMERA_HANDOFF,
                  'application_running':board['running'] and board['preview_thread_alive'] and not board['worker_error'],
                  'managed_buffers':board['memory']['roles']=={'camera':3,'display':3,'prep':5,'cnn_model':2} and board['memory']['active_bos']==board['memory']['allocated_bos']-board['memory']['released_bos'],
                  'model_matches_selection':bool(model['result_valid'])==bool(selection['valid']) and (not selection['valid'] or model['class_id']==selection['class_id'])}
        if expect_empty:
            checks.update(selection_empty=not selection['valid'], native_model_empty=not model['active'] and model['class_id']==22,
                          timings_empty=web['camera_timing'] is None and web['voice_timing'] is None)
        else:
            timing = web['camera_timing'] if mode=='CAMERA' else web['voice_timing']
            checks.update(actual_label_matches=selection['valid'] and selection['name']==expected_name,
                          source_matches=selection['source']==mode.lower(), current_timing_present=timing is not None)
            if timing:
                checks['timing_identity_matches']=all(timing.get(k)==request.get(k) for k in ('mode_epoch','request_epoch','request_id','selection_seq'))
        report = {'version':session.config['project_version'], 'expected_mode':mode,'expected_name':expected_name,
                  'expect_empty':expect_empty,'passed':all(checks.values()),'checks':checks,'web':web,'board':board,
                  'release_manifest_sha256':hashlib.sha256((session.root/'release_manifest.json').read_bytes()).hexdigest(),
                  'physical_observation':'Operator confirmation required; snapshots do not establish physical HDMI content',
                  'overall_accuracy_measured':False}
        if not expect_empty:
            report['transaction_report']=app.last_result if mode=='CAMERA' else app.voice_result
    finally:
        app.lock.release()
    folder=app.report_folder/'entry_validation';folder.mkdir(exist_ok=True)
    file=folder/(datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary={k:report[k] for k in ('version','expected_mode','expected_name','expect_empty','passed','checks')}
    summary.update(report=str(file),camera_handoff_policy=board['camera_handoff_policy'],request=request,selection=selection,
                   camera_timing=web['camera_timing'],voice_timing=web['voice_timing'],native_model=model)
    print('ENTRY_DELTA_SNAPSHOT',summary,flush=True)
    if not report['passed']:
        raise RuntimeError('Entry snapshot did not pass; preserve evidence: '+str(file))
    return summary
