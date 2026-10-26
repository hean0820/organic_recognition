"""One asynchronous voice request at a time; identity survives cancel/mode changes."""
import json
import threading
import time
from pathlib import Path
import numpy as np
from ..drivers.voice_runtime import VoiceModel, RequestControl, VoiceSegment, read_pcm
from ..drivers.audio_capture import AudioCaptureError


class VoiceApplicationMixin:
    def init_voice(self):
        self.voice_timing = None
        self.voice_model = VoiceModel(self.page.lib)
        self.requests = RequestControl(self.page.lib)
        self.requests.ready(False, True)

    def current_voice_timing(self, request=None):
        with self.requests.lock:
            request = request or self.requests.status()
            timing = self.voice_timing
            if (timing is None or request.get('mode') != 'VOICE' or request.get('active') or
                    request.get('state') not in ('RESULT', 'REJECTED', 'ERROR') or
                    request.get('source') not in ('VOICE', 'NONE') or
                    any(timing[key] != request.get(key) for key in
                        ('mode_epoch', 'request_epoch', 'request_id', 'selection_seq'))):
                return None
            return dict(timing)

    def _publish_voice_timing(self, token, prediction, input_source):
        # Cancellation bypasses app.lock. Match and publish while requests.lock
        # holds the completed result's identity, including selection sequence.
        with self.requests.lock:
            state = self.requests.status()
            if (state.get('mode_epoch') != token[1] or state.get('request_epoch') != token[1] or
                    state.get('request_id') != token[2] or state.get('active')):
                return False
            self.requests.sync(self.page)
            profile = prediction['compute_profile']
            if self.page.lib.psv7_voice_timing(self.page.handle, token[1], token[2],
                    profile['total_us'], profile['frontend_us'], profile['cnn_us'],
                    input_source == 'EXISTING_TRAINING_PCM_REGRESSION'):
                return False
            self.voice_timing = dict(profile, mode_epoch=state['mode_epoch'], request_epoch=state['request_epoch'],
                                     request_id=state['request_id'], selection_seq=state['selection_seq'],
                                     input_source=input_source, native_call_wall_ms=prediction['native_call_wall_ms'])
            return True

    def _sync_request(self):
        if self.requests is not None: self.requests.sync(self.page)

    def _refresh_control(self):
        # Cancellation must not wait for the expensive inference/capture lock.
        if self.running and self.lock.acquire(blocking=False):
            try:
                index = self.display.back(); self._render(index)
                self.display.present(index); self.page.presented()
            finally:
                self.lock.release()

    def set_mode(self, mode):
        if self.requests is None: raise RuntimeError('Application not initialized')
        status = self.requests.mode(mode)
        self._refresh_control()
        return status

    def cancel(self):
        if self.requests is None: return {'initialized': False}
        status = self.requests.cancel()
        self._refresh_control()
        return status

    def join_voice(self, timeout=15):
        worker = self.voice_worker
        if worker and worker is not threading.current_thread():
            worker.join(timeout)
            if worker.is_alive(): raise RuntimeError('Voice worker still owns native/audio state; keep session and kernel')

    def voice_status(self):
        return {'request': self.requests.status() if self.requests else {'closed': True},
                'worker_alive': bool(self.voice_worker and self.voice_worker.is_alive()),
                'last_voice_result': self.voice_result}

    def voice_once(self, line_input=False, gain=1, expected_label=None, scene=None, expected_epoch=None):
        request_started = time.monotonic()
        if expected_label is not None and not isinstance(expected_label,str): raise ValueError('expected_label must be text or None')
        if scene is not None and not isinstance(scene,str): raise ValueError('scene must be text or None')
        if gain not in (0,1,2,3): raise ValueError('gain must be 0..3')
        if self.voice_worker and self.voice_worker.is_alive(): raise RuntimeError('Previous voice worker is still finishing')
        # Active requests are refused; ordinary preview rendering gets a short wait.
        if self.audio.owns_capture or self.requests.status()['active']:
            raise RuntimeError('Application has an active request; wait or cancel it')
        if not self.lock.acquire(timeout=2): raise RuntimeError('Preview did not release its lock; inspect status')
        try:
            self._check()
            status = self.audio.status()
            with self.requests.lock:
                if expected_epoch is not None and self.requests.status()['mode_epoch'] != expected_epoch:
                    raise RuntimeError('Voice command is stale')
                self.requests.ready(status['status'] & 31 == 3 and not status['control'] & 1, self.voice_model.ready, line_input)
                token = self.requests.begin('VOICE',expected_epoch=expected_epoch)
            self.requests.progress(token, 2, 'KEEP_QUIET_500MS')
            self.voice_sequence += 1
            folder = self.report_folder / ('voice_%04d' % self.voice_sequence)
            self.voice_result = None
            self.page.lib.psv7_audio_stats(self.page.handle,0,0,0,0)
            index = self.display.back(); self._render(index)
            self.display.present(index); self.page.presented()
            self.voice_worker = threading.Thread(target=self._voice_run, args=(token,folder,line_input,gain,expected_label,scene,request_started),
                                                 name='psv7-voice', daemon=True)
            self.voice_worker.start()
        finally:
            self.lock.release()
        print('PSV7_VOICE_STARTED; keep quiet 500 ms, speak when SPEAK_NOW appears', flush=True)
        return {'started': True, 'token': token, 'report_directory': str(folder)}

    def _voice_run(self, token, folder, line_input, gain, expected_label, scene, request_started=None):
        report = {'passed': False, 'token': list(token), 'input_source': 'LIVE_MIC' if not line_input else 'LIVE_LINE_INPUT',
                  'declared_label': expected_label, 'scene': scene,
                  'recognition_accuracy': 'Independent sample label and observation required; no overall accuracy claim'}
        segment = None
        started = time.monotonic() if request_started is None else request_started
        try:
            with self.lock:
                self._check()
                if not self.requests.current(token):
                    report['outcome'] = 'CANCELLED_OR_STALE'; return
                def progress(status):
                    self.requests.progress(token, 2, status['reason'])
                    print('PSV7_VOICE_STAGE', status['reason'], flush=True)
                segment = VoiceSegment(self.page.lib, progress)
                try:
                    capture = self.audio.record(folder, seconds=9.5, line_input=line_input, gain=gain,
                                                cancelled=lambda: not self.requests.current(token), segment=segment)
                    report['capture'] = capture
                except AudioCaptureError as error:
                    report['capture'] = error.report
                    raise
                if not self.requests.current(token): report['outcome'] = 'CANCELLED_OR_STALE'; return
                vad = segment.status(); report['vad'] = vad
                if vad['state_id'] != 4:
                    self.requests.reject(token, vad['reason'])
                    report.update(passed=True, outcome='REJECTED', reason=vad['reason']); return
                pcm = segment.pcm()
                self.requests.progress(token, 3, 'PROCESSING')
                prediction, result, _, _ = self.voice_model.predict(pcm, folder)
                report['prediction'] = prediction
                applied = self.requests.voice_result(token, result)
                if applied >= 0:
                    report['timing_published'] = self._publish_voice_timing(token, prediction, report['input_source'])
                report.update(passed=applied >= 0, outcome='RESULT' if applied == 0 else 'REJECTED' if applied == 1 else 'CANCELLED_OR_STALE')
                if applied == 0:
                    report['class_zh'] = str(self.labels[result.class_id])
                    if expected_label is not None:report['matches_declared_label'] = report['class_zh']==expected_label
        except Exception as error:
            report['error'] = repr(error)
            report['outcome'] = 'ERROR' if self.requests.current(token) else 'CANCELLED_OR_STALE'
            self.requests.reject(token, 'AUDIO_OR_MODEL_ERROR', error=True)
            if self.audio.owns_capture: self.stop_event.set()
        finally:
            if segment is not None:
                report.setdefault('vad',segment.status())
                segment.close()
            with self.lock:
                if self.running and not self.audio.owns_capture:
                    try:
                        vad=report.get('vad',{})
                        dropped=report.get('capture',{}).get('after_stop',{}).get('dropped',0)
                        self.page.lib.psv7_audio_stats(self.page.handle,vad.get('peak',0),vad.get('noise_abs',0),vad.get('length',0),dropped)
                        index = self.display.back(); self._render(index)
                        self.display.present(index); self.page.presented()
                        report['model3d'] = self.page.model_info()
                    except Exception as error: report['display_error'] = repr(error); report['passed'] = False
                report.update(elapsed_s=time.monotonic()-started, final_request_state=self.requests.status())
                report['request_wall_scope'] = 'voice_once entry through result/display finalization; includes diagnostic recomputation'
                with self.requests.lock:
                    timing = self.current_voice_timing()
                    if timing and timing['request_id'] == token[2] and timing['mode_epoch'] == token[1]:
                        self.voice_timing = dict(timing, request_wall_ms=report['elapsed_s']*1000)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'voice_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                self.voice_result = report
            print('PSV7_VOICE_RESULT', report, flush=True)
            print('VOICE_REPORT_DIRECTORY', str(folder), flush=True)

    def verify_voice_saved(self):
        if self.voice_worker and self.voice_worker.is_alive(): raise RuntimeError('Wait for the live voice request before saved PCM regression')
        with self.lock:
            started = time.monotonic()
            self._check()
            status=self.audio.status()
            self.requests.ready(status['status'] & 31 == 3 and not status['control'] & 1, self.voice_model.ready)
            token = self.requests.begin('VOICE')
            self.voice_sequence += 1
            folder = self.report_folder / ('voice_saved_%04d' % self.voice_sequence)
            folder.mkdir()
            try:
                pcm = read_pcm(self.folder / 'assets/voice/selftest_ethene_training.wav')
                prediction, result, features, logits = self.voice_model.predict(pcm, folder)
                reference = np.load(self.folder / 'assets/voice/golden_arrays.npz', allow_pickle=False)
                with reference:
                    differences = {'features_max_abs': float(np.max(np.abs(features-reference['example_features']))),
                                   'logits_max_abs': float(np.max(np.abs(logits-reference['example_logits'])))}
                if differences['features_max_abs'] > 0.001 or differences['logits_max_abs'] > 0.02 or result.class_id != 0 or result.reason != 0:
                    raise RuntimeError('Fixed PCM differs from frozen stage2 numerical contract: '+str(differences))
                if self.requests.voice_result(token, result) != 0: raise RuntimeError('Saved voice result was stale')
                self.reference_voice_token=token
                if not self._publish_voice_timing(token, prediction, 'EXISTING_TRAINING_PCM_REGRESSION'):
                    raise RuntimeError('Saved voice timing was stale')
                self.page.lib.psv7_audio_stats(self.page.handle,int(np.max(np.abs(pcm.astype(np.int32)))),0,int(pcm.size),0)
                index = self.display.back(); self._render(index)
                self.display.present(index); self.page.presented()
                report = {'passed': True, 'differences': differences, 'prediction': prediction,
                          'input_source': 'EXISTING_TRAINING_PCM_REGRESSION', 'independent_accuracy': False,
                          'model3d': self.page.model_info(), 'request': self.requests.status()}
                report['elapsed_s'] = time.monotonic()-started
                with self.requests.lock:
                    timing = self.current_voice_timing()
                    if timing and timing['request_id'] == token[2] and timing['mode_epoch'] == token[1]:
                        self.voice_timing = dict(timing, request_wall_ms=report['elapsed_s']*1000)
                (folder / 'saved_voice_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                print('PSV7_SAVED_VOICE_REGRESSION_PASS', report, flush=True)
                return report
            except Exception:
                self.requests.reject(token, 'SAVED_VOICE_REGRESSION_ERROR', error=True)
                raise
