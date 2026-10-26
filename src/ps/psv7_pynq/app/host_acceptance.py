"""Collect board snapshots and user observations; never manufacture board PASS."""
import hashlib
import json
from datetime import datetime, timezone


def record_host_observation(session, label, expected_name=None, observed_web_name=None,
                            observed_hdmi_name=None, note=None):
    if session.app is None or session.host_service is None:
        raise RuntimeError('Start the session and host service before recording observations')
    app = session.app
    web = session.host_service.controller.snapshot()
    if web['busy']:
        raise RuntimeError('Wait for the request and worker to finish before collecting evidence')
    # Take only a small snapshot. Holding app.lock here is bounded to a normal
    # preview step and used only after the request has finished.
    with app.lock:
        board = app.status()
        if app.requests.status() != web['request']:
            raise RuntimeError('State changed during observation; collect again')
        model = board['model3d']
        valid = web['selection']['valid']
        same = (bool(model['result_valid']) == valid and
                (not valid or model['class_id'] == web['selection']['class_id']))
        report = {'schema': 1, 'label': label, 'time_utc': datetime.now(timezone.utc).isoformat(),
                  'version': session.config['project_version'],
                  'release_manifest_sha256': hashlib.sha256((session.root / 'release_manifest.json').read_bytes()).hexdigest(),
                  'overlay_sha256': {name: value for name, value in session.config['sha256'].items()
                                     if name.endswith(('.bit', '.hwh'))},
                  'web_state': web, 'board_state': board, 'native_selection_matches_web': same,
                  'expected_name': expected_name, 'observed_web_name': observed_web_name,
                  'observed_hdmi_name': observed_hdmi_name, 'note': note,
                  'last_camera_report': app.last_result, 'last_voice_report': app.voice_result,
                  'board_environment': session.environment,
                  'visual_observation_complete': observed_web_name is not None and observed_hdmi_name is not None,
                  'overall_accuracy_measured': False}
    if expected_name is not None:
        report['names_match_declared'] = (expected_name == web['selection']['name'] ==
                                          observed_web_name == observed_hdmi_name)
    folder = app.report_folder / 'host_observations'
    folder.mkdir(exist_ok=True)
    path = folder / (datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f') + '.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('HOST_OBSERVATION_SAVED', str(path), 'native_selection_matches_web', same, flush=True)
    return report
