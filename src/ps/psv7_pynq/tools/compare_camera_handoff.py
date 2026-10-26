"""Alternate complete live recognitions with only the handoff order changed."""
import json
import statistics
import time

from ..drivers.camera_handoff import LEGACY, OVERLAP


def choose_policy(calls, minimum_gain_ms=5.0):
    """Require useful preparation/present-ACK gains and no worse observed tail.

    Three measurements are not a percentile estimate. Report their maximum,
    never label it p95, and do not promote a path solely on inference latency.
    """
    metrics = ('result_preparation_ms', 'result_present_ack_wall_ms', 'request_wall_ms')
    summary = {policy: {key: {'median': statistics.median(row[key] for row in rows),
                              'max': max(row[key] for row in rows)} for key in metrics}
               for policy, rows in calls.items()}
    accepted = all(summary[LEGACY][key]['median'] - summary[OVERLAP][key]['median'] >= minimum_gain_ms
                   and summary[OVERLAP][key]['max'] <= summary[LEGACY][key]['max']
                   for key in metrics)
    return (OVERLAP if accepted else LEGACY), summary, accepted


def compare_camera_handoff(app, expected_class_id, repeats=3):
    """User must keep one known paper stationary and issue no concurrent commands.

    One warm pair, then three alternating-order pairs. Each call performs the
    normal full live recognition, publication, display ACK and diagnostic save.
    Startup/preview keep legacy capture. This is not physical click-to-photon
    timing: host queue, browser polling and scanout are outside these endpoints.
    """
    if repeats != 3:
        raise ValueError('This comparison uses exactly three measured pairs')
    if not isinstance(expected_class_id, int) or not 0 <= expected_class_id < 22:
        raise ValueError('Declare the actual known paper class before testing')
    with app.lock:
        app._check()
        status = app.requests.status()
        if status['mode'] != 'CAMERA' or status['active']:
            raise RuntimeError('Comparison requires inactive CAMERA mode')
        if app.capture.snapshot_policy != 'HEAP_MEMCPY_CHECK':
            raise RuntimeError('Keep the accepted HEAP_MEMCPY_CHECK for both paths')
        epoch = status['mode_epoch']
        report = {'passed': False, 'board_acceleration_accepted': False,
                  'input_source': 'LIVE_CAMERA_STATIONARY_KNOWN_PAPER',
                  'expected_class_id': expected_class_id, 'same_PCM_or_image_bytes_claimed': False,
                  'scope': 'Same running app, model, clocks, heap copy/check, initial UI, PREP/CNN/FC, result display ACK and diagnostic saves. Only handoff order differs. Different live frames; no exact pixel equality or physical click-to-photon claim.',
                  'warmup_calls': [], 'calls': {LEGACY: [], OVERLAP: []},
                  'selected_policy': LEGACY, 'report_directory': str(app.report_folder)}
        folder = app.folder / 'reports/camera_handoff_compare'
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / ('comparison_%d.json' % time.time_ns())
        try:
            for round_index in range(repeats + 1):
                order = (LEGACY, OVERLAP) if round_index % 2 == 0 else (OVERLAP, LEGACY)
                for policy in order:
                    app.set_camera_handoff_policy(policy)
                    actual = app.recognize(expected_epoch=epoch)
                    if (not actual.get('passed') or not actual.get('published') or
                            actual.get('outcome') != 'RESULT' or actual.get('display_error') or
                            not actual.get('diagnostics_passed') or
                            actual['cnn']['predicted'] != expected_class_id):
                        raise RuntimeError('Live comparison input/result failed; keep all capture reports and use legacy')
                    if actual['capture_timings_ms']['handoff_policy'] != policy:
                        raise RuntimeError('Wrong camera handoff policy in actual capture')
                    current = app.requests.status()
                    if current['mode_epoch'] != epoch or current['mode'] != 'CAMERA' or not current['valid']:
                        raise RuntimeError('Mode changed during comparison')
                    row = {'policy': policy, 'round': round_index, 'warmup': round_index == 0,
                           'capture_sequence': actual['capture_sequence'],
                           'request_id': current['request_id'],
                           'capture_report': str(app.report_folder / ('capture_%04d' % actual['capture_sequence']) / 'app_capture_report.json'),
                           'freeze_wait_ms': actual['capture_timings_ms']['freeze_wait_ms'],
                           'initial_UI_wall_ms': actual['initial_UI_wall_ms'],
                           'snapshot_copy_validate_ms': actual['capture_timings_ms']['snapshot_copy_validate_ms'],
                           'algorithm_wall_ms': actual['algorithm_wall_ms'],
                           'inference_wall_ms': actual['cnn']['inference_wall_ms'],
                           'result_preparation_ms': actual['result_preparation_us'] / 1000,
                           'result_present_ack_wall_ms': actual['result_present_ack_wall_ms'],
                           'request_wall_ms': actual['request_wall_ms'],
                           'class_id': actual['cnn']['predicted'],
                           'hardware': actual['cnn']['hardware'], 'final_state': actual['cnn']['final_state']}
                    if round_index == 0:
                        report['warmup_calls'].append(row)
                    else:
                        report['calls'][policy].append(row)
                    print('CAMERA_HANDOFF_SAMPLE', row, flush=True)
            selected, summary, accepted = choose_policy(report['calls'])
            report.update(passed=True, selected_policy=selected,
                          board_acceleration_accepted=accepted, summary_ms=summary,
                          selection_rule='All three endpoints: median improves by >=5ms and measured maximum does not worsen; all eight live recognitions must match declared label. Three samples do not measure p95 or overall accuracy.')
        except Exception as error:
            report['error'] = repr(error)
            raise
        finally:
            # Any failed or slower run leaves formal recognition on legacy.
            with app.requests.lock:
                app.camera_handoff_policy = report['selected_policy'] if report['passed'] else LEGACY
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print('CAMERA_HANDOFF_COMPARISON', str(output), flush=True)
        return report
