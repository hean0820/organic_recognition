"""Replay a previously accepted camera frame through the current app.
This is saved-frame regression, not a new live-camera recognition or FPS test.
Call verify_saved_frame(session.app) from the formal application Notebook.
"""
import hashlib
import json
import time
from contextlib import contextmanager
from pathlib import Path
import numpy as np


@contextmanager
def saved_capture_source(application, frame):
    """Caller holds the app lock, excluding the preview thread throughout."""
    capture = application.capture
    original = capture.acquire
    local_method = 'acquire' in vars(capture)
    local_timing = 'last_timing' in vars(capture)
    previous_timing = getattr(capture, 'last_timing', None)
    def acquire(*args, **kwargs):
        started = time.perf_counter()
        copied=kwargs.get('destination')
        if copied is None:copied=frame.copy()
        elif application.page.copy_validate_frame(frame,copied):
            raise RuntimeError('Saved baseline fails fused pixel validation')
        capture.last_timing = {'saved_source_copy_validate_ms': (time.perf_counter() - started) * 1000,
                              'snapshot_destination':'PRIVATE_PREP_INPUT' if kwargs.get('destination') is not None else 'INDEPENDENT_HEAP'}
        return copied, -1  # Explicitly not a live VDMA slot.
    capture.acquire = acquire
    try:
        yield
    finally:
        if local_method:
            capture.acquire = original
        else:
            del capture.acquire
        if local_timing:
            capture.last_timing = previous_timing
        elif 'last_timing' in vars(capture):
            del capture.last_timing


def verify_saved_frame(application, baseline_folder=None, stop_after=True):
    folder = Path(baseline_folder) if baseline_folder else (
        application.folder / 'assets/reference')
    report = {'validation_kind': 'saved_camera_frame_regression',
              'source_directory': str(folder), 'passed': False,
              'not_exposed_by_public_ABI': ['fc1_acc'],
              'scope': 'Current app PREP/CNN/FC/result publication using saved input; excludes live acquisition performance'}
    report_path = application.report_folder / ('saved_frame_acceptance_%s.json' % time.time_ns())
    failure = None
    try:
        names = ('frame_bgr.npy', 'input64.npy', 'cnn_actual.npz', 'app_capture_report.json')
        for name in names:
            if not (folder / name).is_file():
                raise FileNotFoundError('Saved baseline missing: ' + str(folder / name))
        old_report = json.loads((folder / 'app_capture_report.json').read_text())
        if not old_report.get('passed') or old_report.get('outcome') != 'RESULT':
            raise RuntimeError('Selected baseline is not a successful recognition')
        frame = np.load(folder / 'frame_bgr.npy', allow_pickle=False)
        expected_input = np.load(folder / 'input64.npy', allow_pickle=False)
        with np.load(folder / 'cnn_actual.npz', allow_pickle=False) as archive:
            expected = {name: archive[name].copy() for name in ('features', 'pool3', 'acc', 'relu', 'logits')}
        if frame.shape != (720, 1280, 3) or frame.dtype != np.uint8 or not frame.flags.c_contiguous:
            raise ValueError('Saved baseline frame format differs from the app')
        report['source_sha256'] = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in names}
        print('SAVED_REGRESSION_SOURCE', str(folder), flush=True)
        with application.lock:
            if not application.running or application.worker_error:
                raise RuntimeError('Start the current app and preview before regression')
            report['native_pixel_violations'] = application.page.validate_frame(frame)
            if report['native_pixel_violations']:
                raise RuntimeError('Saved baseline fails native pixel-format validation')
            with saved_capture_source(application, frame):
                result = application.recognize(diagnostics=True)
            result['input_source'] = 'saved_camera_frame_regression'
            result['saved_source_directory'] = str(folder)
            output = application.report_folder / ('capture_%04d' % result['capture_sequence'])
            (output / 'app_capture_report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
            report['current_capture_directory'] = str(output)
            report['current_result'] = result
            if not result.get('passed') or result.get('outcome') != 'RESULT' or not result['cnn']['transaction_passed']:
                raise RuntimeError('Saved-frame regression did not complete CNN recognition')
            actual_input = np.load(output / 'input64.npy', allow_pickle=False)
            if actual_input.shape != expected_input.shape:
                raise RuntimeError('Preprocessing input shape differs')
            differences = {'input64': int(np.count_nonzero(actual_input != expected_input))}
            with np.load(output / 'cnn_actual.npz', allow_pickle=False) as archive:
                for name, reference in expected.items():
                    if name == 'acc':continue  # FC1 pre-quant accumulator is not a public S1 debug window.
                    actual = archive[name]
                    if actual.shape != reference.shape:
                        raise RuntimeError(name + ' shape differs')
                    differences[name] = int(np.count_nonzero(actual != reference))
            report['differences'] = differences
            report['class_matches_baseline'] = result['cnn']['predicted'] == old_report['cnn']['predicted']
            if any(differences.values()) or not report['class_matches_baseline']:
                raise RuntimeError('Saved-frame results differ from the accepted baseline')
            model=application.page.model_info()
            if not model['active'] or model['class_id']!=result['cnn']['predicted'] or not model['result_valid'] or model['result_source']!=1 or model['render_errors']:
                raise RuntimeError('3D model does not correspond to this camera result: '+repr(model))
            report['model3d']=model
            report['passed'] = True
        print('PSV7_FORMAL_SAVED_DATA_AND_MODEL_PASS', differences, result['cnn']['class_zh'], flush=True)
        # Allow the user to see the saved-input result page before stopping.
        time.sleep(3)
    except Exception as exc:
        report['error'] = repr(exc)
        failure = exc
    finally:
        try:
            if not stop_after:
                report['cleanup'] = {'deferred': True, 'reason': 'Caller retains the running session for live tests; session.stop() required afterwards'}
            else:
                report['cleanup'] = application.stop()
            if not stop_after:
                stats = application.memory.status()
                report['memory_after_regression'] = stats
            else:
                stats = report['cleanup']['memory']
            cleanup=report['cleanup']
            if stop_after and (stats['active_bos'] or stats['allocated_bos']!=stats['released_bos']):
                raise RuntimeError('Managed BO release incomplete')
            before,after=cleanup.get('driver_before',{}),cleanup.get('driver_after',{})
            report['driver_usage_checked']=stop_after and 'unavailable' not in before and 'unavailable' not in after
            if stop_after and 'unavailable' not in before and 'unavailable' not in after and before!=after:
                raise RuntimeError('Driver BO usage did not return to startup baseline: '+repr((before,after)))
        except Exception as exc:
            report['passed'] = False
            report['cleanup_error'] = repr(exc)
            if failure is None:
                failure = exc
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('SAVED_APP_ACCEPTANCE_REPORT', str(report_path), flush=True)
    if failure is not None:
        raise failure
    print('PSV7_FORMAL_SAVED_REGRESSION_PASS', report['model3d'], report['cleanup'].get('memory',report.get('memory_after_regression')), flush=True)
    return report

