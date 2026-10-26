"""One explicit application owner per process and cooperating Linux session."""
import threading
import json
from pathlib import Path
from .config import load_config, verify_project, check_environment
from .bootstrap import ensure_overlay

_owner = None
_owner_lock = threading.RLock()


class PynqSession:
    def __init__(self, root=None):
        self.root, self.config = load_config(root)
        self.app = None
        self.overlay = None
        self.audio = None
        self.audio_sequence = 0
        self.environment = None
        self._process_lock = None
        self.host_service = None

    def check(self):
        return verify_project(self.root)

    def _claim(self):
        global _owner
        with _owner_lock:
            if _owner is not None:
                raise RuntimeError('An application session still owns hardware; stop it first')
            # Kernel exit releases this lock, but hardware may still run:
            # ensure_overlay independently checks hardware identity and idle.
            import fcntl
            handle = open('/tmp/psv7_pynq_hardware.lock', 'a+')
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except Exception:
                handle.close()
                raise RuntimeError('Another PYNQ session holds the hardware lock')
            self._process_lock = handle
            _owner = self

    def _release(self):
        global _owner
        with _owner_lock:
            if self._process_lock is not None:
                self._process_lock.close()
                self._process_lock = None
            if _owner is self:
                _owner = None

    def start(self, mode='reuse', clean_boot=False):
        if mode not in ('reuse', 'cold_start'):
            raise ValueError('mode must be reuse or cold_start')
        if mode == 'cold_start' and not clean_boot:
            raise ValueError('cold_start requires confirmation of a clean board power-up, clean_boot=True')
        self.check()
        self.environment = check_environment(self.config)
        self._claim()
        try:
            self.overlay = ensure_overlay({}, self.root / 'overlay',
                {name: value for name, value in self.config['sha256'].items() if name.endswith(('.bit', '.hwh'))},
                mode=mode, ref_clk_mhz=self.config['ps_reference_mhz'], fclk_mhz=self.config['fclk_mhz'],
                verified_previous_bit_sha256=self.config.get('verified_previous_bit_sha256', ()))
            from pynq import MMIO
            from ..drivers.audio_capture import AudioCapture
            self.audio = AudioCapture(MMIO(0x43C30000,self.overlay.ip_dict['audio_axi_0']['addr_range']))
            from .application import Psv7App
            self.app = Psv7App(self.overlay, self.root)
            self.app.audio = self.audio
            self.app.start()
            # Startup frame acquisition retains its original safety sequence.
            # Recognition uses the reviewed published policy on every new session.
            policy = self.config['camera_handoff_default']
            selected = self.app.set_camera_handoff_policy(policy)
            observed = self.app.status()['camera_handoff_policy']
            if selected != policy or observed != policy:
                raise RuntimeError('Automatic camera handoff policy readback mismatch')
            print('PSV7_CAMERA_HANDOFF_READY', {'requested': policy, 'observed': observed}, flush=True)
            self.app.start_preview()
            print('PSV7_FORMAL_APP_RUNNING', str(self.root), flush=True)
            return self.app
        except Exception:
            # Keep the owner, native workspace, and lock if cleanup fails.
            if self.app is not None:
                try:
                    self.stop()
                except Exception as cleanup:
                    print('PSV7_FORMAL_START_CLEANUP_INCOMPLETE', repr(cleanup), flush=True)
            else:
                self._release()
            raise

    def status(self):
        return self.app.status() if self.app is not None else {'running': False, 'application_created': False}

    def stop(self):
        # Reject network work and join its camera/clear/manual worker before
        # the existing hardware cleanup. A failed join retains ownership.
        host_stop_report = {'host_running': False}
        if self.host_service is not None:
            host_stop_report = self.host_service.stop()
            self.host_service = None
        if self.app is not None:
            self.app.cancel()
            self.app.join_voice()
        if self.audio is not None:
            self.audio.stop()
            audio_status = self.audio.status()
            if audio_status['control'] & 1:
                raise RuntimeError('Audio still enabled; keep session owner')
        else:
            audio_status = None
        if self.app is None:
            self._release()
            return {'running': False, 'application_created': False}
        report = self.app.stop()
        report['host'] = host_stop_report
        report['audio'] = audio_status
        (self.app.report_folder / 'session_stop_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        self.audio = None
        self.app = None
        self._release()
        return report

    def start_host(self, host='0.0.0.0', port=8765, allowed_hosts=None):
        if self.app is None or not self.app.running:
            raise RuntimeError('Start this session application before its host service')
        if self.host_service is not None:
            raise RuntimeError('Host service already exists; call session.stop_host() first')
        from .host_service import HostService
        service = HostService(self.app, self.root, host, port, allowed_hosts)
        service.start()
        self.host_service = service
        return service.info()

    def stop_host(self):
        if self.host_service is not None:
            self.host_service.stop()
            self.host_service = None
        return {'host_running': False}

    def verify_saved_frame(self):
        if self.app is None:
            raise RuntimeError('Start the formal application before saved-frame regression')
        if self.host_service is not None:
            self.stop_host()
        from .acceptance import verify_saved_frame
        try:
            return verify_saved_frame(self.app)
        finally:
            # The verifier calls app.stop(); release session ownership only
            # after checking the actual remaining owners on every error path.
            app = self.app
            if (not app.running and not app.frames and not app.dma_owned and
                    not app.lines.owned and not app.memory.active and
                    not (app.worker and app.worker.is_alive()) and
                    (app.page is None or not app.page.handle)):
                self.app = None
                self._release()

    def verify_unified_cnn(self):
        if self.app is None:
            raise RuntimeError('Start the formal application before PL FC verification')
        from .unified_acceptance import verify_unified_cnn
        return verify_unified_cnn(self.app)

    def verify_pl_fc(self):
        """Compatibility entry: now replays full CNN inputs, never PREP mode3."""
        return self.verify_unified_cnn()

    def verify_speed_saved_frame(self):
        if self.app is None:
            raise RuntimeError('Start the formal application before SPEED saved-frame verification')
        from .acceptance import verify_saved_frame
        with self.app.lock:
            if self.app.requests.status()['active'] or (self.app.voice_worker and self.app.voice_worker.is_alive()):
                raise RuntimeError('Wait or cancel the active request before saved-frame verification')
            self.app.set_mode('camera')
            return verify_saved_frame(self.app, stop_after=False)

    def record_audio(self, seconds=3.0, line_input=False, gain=1):
        if self.app is None or self.audio is None:
            raise RuntimeError('Start the camera/audio application first')
        if self.app.voice_worker and self.app.voice_worker.is_alive():
            raise RuntimeError('Voice request is active; wait or cancel before diagnostic recording')
        # The preview worker and image commands use this same lock. HDMI scanout
        # and camera DMA stay running, while expensive PS redraws wait.
        with self.app.lock:
            self.app._check()
            self.audio_sequence += 1
            folder = self.app.report_folder / ('audio_%04d' % self.audio_sequence)
            print('PSV7_AUDIO_RECORDING', seconds, 'seconds; preview redraw waits', flush=True)
            try:
                report = self.audio.record(folder, seconds, line_input, gain)
                print('PSV7_AUDIO_CAPTURE_RESULT', report, flush=True)
                return report
            finally:
                print('AUDIO_REPORT_DIRECTORY', str(folder), flush=True)
                if self.audio.owns_capture:
                    self.app.stop_event.set()
                    print('PSV7_AUDIO_STOP_INCOMPLETE; keep kernel/session and call session.stop()', flush=True)
