"""SPEED C frontend/CNN, frozen VAD and one authoritative request controller."""
import ctypes
import json
import threading
import time
import wave
from pathlib import Path
import numpy as np

PTR, U32, SIZE, INT = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_size_t, ctypes.c_int


class ChemResult(ctypes.Structure):
    _fields_ = [('class_id', INT), ('raw_class', INT), ('confidence', ctypes.c_float),
                ('margin', ctypes.c_float), ('reason', INT)]


class ChemProfile(ctypes.Structure):
    _fields_ = [(name, U32) for name in ('frontend_us', 'cnn_us', 'postprocess_us', 'total_us')]


def bind(lib):
    signatures = {
        'voice_recognizer_init': ([], INT), 'voice_recognizer_predict': ([PTR, SIZE, PTR], INT),
        'voice_recognizer_reason': ([PTR], ctypes.c_char_p),
        'chem22_frontend': ([PTR, SIZE, PTR], INT), 'chem22_logits': ([PTR, PTR], None),
        'chem22_model_version': ([], ctypes.c_char_p),
        'chem22_last_profile': ([], ctypes.POINTER(ChemProfile)),
        'psv7_request_create': ([], PTR), 'psv7_request_destroy': ([PTR], None),
        'psv7_request_mode': ([PTR, U32], INT), 'psv7_request_cancel': ([PTR], None),
        'psv7_request_ready': ([PTR, U32, U32, U32], None), 'psv7_request_begin': ([PTR, U32], INT),
        'psv7_request_current': ([PTR, U32, U32, U32], INT),
        'psv7_request_progress': ([PTR, U32, U32, U32, U32, ctypes.c_char_p], INT),
        'psv7_request_reject': ([PTR, U32, U32, U32, U32, ctypes.c_char_p], INT),
        'psv7_request_publish': ([PTR, U32, U32, U32, U32], INT),
        'psv7_request_voice_result': ([PTR, PTR, U32, U32], INT),
        'psv7_request_reference': ([PTR, U32], INT),
        'psv7_request_info': ([PTR, PTR], INT), 'psv7_request_reason': ([PTR], ctypes.c_char_p),
        'psv7_sync_control': ([PTR, PTR], INT),
        'psv7_audio_stats': ([PTR, U32, U32, U32, U32], INT),
        'psv7_voice_timing': ([PTR, U32, U32, U32, U32, U32, U32], INT),
        'psv7_voice_timing_info': ([PTR, PTR], INT),
        'psv7_vad_create': ([], PTR), 'psv7_vad_destroy': ([PTR], None),
        'psv7_vad_feed': ([PTR, PTR, SIZE], INT), 'psv7_vad_info': ([PTR, PTR], INT),
        'psv7_vad_reason': ([PTR], ctypes.c_char_p), 'psv7_vad_copy': ([PTR, PTR, SIZE], INT)}
    for name, (args, ret) in signatures.items():
        fn = getattr(lib, name); fn.argtypes = args; fn.restype = ret


class VoiceModel:
    _registry_lock = threading.Lock()
    _workspace_locks = {}
    def __init__(self, lib):
        self.lib = lib
        bind(lib)
        with self._registry_lock:
            self.lock = self._workspace_locks.setdefault(lib._handle, threading.RLock())
        with self.lock:
            if lib.chem22_model_version().decode() != 'chem22_real4_v1_candidate' or lib.voice_recognizer_init():
                raise RuntimeError('Frozen voice CNN numerical self-test failed')
        self.ready = True

    def predict(self, pcm, directory=None):
        if not isinstance(pcm, np.ndarray) or pcm.dtype != np.int16 or pcm.ndim != 1 or not 400 <= pcm.size <= 48000:
            raise ValueError('Voice input must be 400..48000 mono int16 samples at 16 kHz')
        pcm = np.ascontiguousarray(pcm)
        with self.lock:
            result = ChemResult()
            start = time.perf_counter()
            code = self.lib.voice_recognizer_predict(pcm.ctypes.data, pcm.size, ctypes.byref(result))
            infer_ms = (time.perf_counter() - start) * 1000
            # Copy while this library's static workspace is still locked.
            native_profile = self.lib.chem22_last_profile().contents
            profile = {key: int(getattr(native_profile, key)) for key, _ in ChemProfile._fields_}
            profile.update(clock='PROCESS_CPU_CLOCK', unit='microseconds',
                           scope='single native prediction; excludes audio, display and diagnostic recomputation')
            if code:
                raise RuntimeError('Original voice recognizer rejected invalid/model input')
            reason = self.lib.voice_recognizer_reason(ctypes.byref(result)).decode()
            report = {key: getattr(result, key) for key, _ in ChemResult._fields_}
            report.update(reason_name=reason, inference_ms=infer_ms, model_version='chem22_real4_v1_candidate',
                          samples=int(pcm.size), backend='PS_NATIVE_C_SPEED', accuracy='Not measured by this transaction',
                          compute_profile=profile, native_call_wall_ms=infer_ms)
            diagnostic_start = time.perf_counter()
            features = np.zeros(3840, np.float32); logits = np.zeros(24, np.float32)
            if self.lib.chem22_frontend(pcm.ctypes.data, pcm.size, features.ctypes.data):
                raise RuntimeError('Original voice frontend failed')
            self.lib.chem22_logits(features.ctypes.data, logits.ctypes.data)
            if not np.isfinite(features).all() or not np.isfinite(logits).all():
                raise RuntimeError('Voice frontend/CNN produced nonfinite arrays')
            report['diagnostic_recompute_wall_ms'] = (time.perf_counter()-diagnostic_start)*1000
            report['diagnostic_recompute_scope'] = 'second frontend/logits pass for numerical evidence; excluded from compute profile'
            if directory is not None:
                directory = Path(directory)
                np.savez(directory / 'voice_arrays.npz', features=features, logits=logits)
                save_pcm(directory / 'utterance.wav', pcm)
            return report, result, features, logits


def read_pcm(file):
    with wave.open(str(file), 'rb') as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()) != (16000, 1, 2, 'NONE'):
            raise ValueError('Expected uncompressed 16 kHz mono PCM16 WAV')
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(np.int16, copy=True)
    return pcm


def save_pcm(file, pcm):
    with wave.open(str(file), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(np.asarray(pcm, dtype='<i2').tobytes())


class RequestControl:
    """One C AppControl owns identities; UiPanel receives a locked display snapshot."""
    def __init__(self, lib):
        self.lib = lib; self.lock = threading.RLock()
        self.handle = lib.psv7_request_create()
        if not self.handle: raise MemoryError('Request controller allocation failed')

    def status(self):
        with self.lock:
            if not self.handle: return {'closed': True}
            out = np.zeros(14, np.uint32)
            if self.lib.psv7_request_info(self.handle, out.ctypes.data): raise RuntimeError('Request status unavailable')
            names = ('mode_id', 'state_id', 'source_id', 'mode_epoch', 'request_id', 'request_epoch',
                     'selection_seq', 'class_id', 'valid', 'active', 'audio_ready', 'recognizer_ready', 'line_input', 'revision')
            status = dict(zip(names, map(int, out)))
            status.update(mode=('CAMERA', 'VOICE')[status['mode_id']],
                          state=('IDLE','ARMED','LISTENING','PROCESSING','RESULT','REJECTED','ERROR')[status['state_id']],
                          source=('NONE','CAMERA','VOICE','TEST','GOLDEN','DEMO','EXTERNAL')[status['source_id']],
                          reason=self.lib.psv7_request_reason(self.handle).decode())
            return status

    def ready(self, audio, model=True, line_input=False):
        with self.lock: self.lib.psv7_request_ready(self.handle, audio, model, line_input)

    def mode(self, mode):
        if mode not in ('camera', 'voice'): raise ValueError('mode must be camera or voice')
        with self.lock:
            if self.lib.psv7_request_mode(self.handle, mode == 'voice') < 0: raise RuntimeError('Mode switch failed')
            return self.status()

    def cancel(self):
        with self.lock:
            self.lib.psv7_request_cancel(self.handle)
            return self.status()

    def begin(self, source, expected_epoch=None):
        source_id = {'CAMERA': 1, 'VOICE': 2}[source]
        with self.lock:
            if expected_epoch is not None and self.status()['mode_epoch'] != expected_epoch:
                raise RuntimeError('Command is stale; mode or cancellation changed before it started')
            code = self.lib.psv7_request_begin(self.handle, source_id)
            if code: raise RuntimeError('Request refused (%s): %s' % (code, self.status()))
            status = self.status()
            return (source_id, status['mode_epoch'], status['request_id'])

    def current(self, token):
        with self.lock: return bool(self.handle and self.lib.psv7_request_current(self.handle, *token))

    def progress(self, token, state, reason):
        with self.lock: return self.lib.psv7_request_progress(self.handle, *token, state, reason.encode()) == 0

    def reject(self, token, reason, error=False):
        with self.lock: return self.lib.psv7_request_reject(self.handle, *token, error, reason.encode()) == 0

    def publish(self, token, class_id):
        with self.lock:
            source, epoch, request = token
            return self.lib.psv7_request_publish(self.handle, source, class_id, epoch, request) == 0

    def voice_result(self, token, result):
        with self.lock:
            source, epoch, request = token
            if source != 2: raise ValueError('Voice result requires a voice token')
            return int(self.lib.psv7_request_voice_result(self.handle, ctypes.byref(result), epoch, request))

    def reference(self, class_id, expected_epoch=None):
        with self.lock:
            if expected_epoch is not None and self.status()['mode_epoch'] != expected_epoch:
                raise RuntimeError('Manual command is stale')
            if self.lib.psv7_request_reference(self.handle, class_id): raise ValueError('Class must be 0..21')

    def sync(self, page):
        with self.lock:
            if self.lib.psv7_sync_control(page.handle, self.handle): raise RuntimeError('Display control sync failed')

    def close(self):
        with self.lock:
            if self.handle: self.lib.psv7_request_destroy(self.handle); self.handle = None


class VoiceSegment:
    def __init__(self, lib, progress=None):
        self.lib = lib; self.progress = progress; self.previous = -1
        self.handle = lib.psv7_vad_create()
        if not self.handle: raise MemoryError('Voice segment allocation failed')
        self.feed([])

    def feed(self, samples):
        pcm = np.asarray(samples, dtype=np.int16)
        if self.lib.psv7_vad_feed(self.handle, pcm.ctypes.data, pcm.size) < 0: raise RuntimeError('Voice VAD failed')
        status = self.status()
        if status['state_id'] != self.previous:
            self.previous = status['state_id']
            if self.progress: self.progress(status)
        return status['state_id'] in (4, 5)

    def status(self):
        raw = np.zeros(7, np.uint32)
        if self.lib.psv7_vad_info(self.handle, raw.ctypes.data): raise RuntimeError('Voice VAD status unavailable')
        status = dict(zip(('state_id', 'length', 'threshold', 'noise_abs', 'peak', 'clips', 'voiced'), map(int, raw)))
        status.update(reason=self.lib.psv7_vad_reason(self.handle).decode(),
                      state=('IDLE','CALIBRATE','WAIT','SPEECH','DONE','REJECT')[status['state_id']])
        return status

    def pcm(self):
        out = np.zeros(48000, np.int16)
        count = self.lib.psv7_vad_copy(self.handle, out.ctypes.data, out.size)
        if count < 0: raise RuntimeError('Voice segment is not complete')
        return out[:count].copy()

    def close(self):
        if self.handle: self.lib.psv7_vad_destroy(self.handle); self.handle = None
