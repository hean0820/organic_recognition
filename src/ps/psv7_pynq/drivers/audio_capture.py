"""Bounded PCM capture on the verified camera/audio Overlay; no implicit MMIO."""
import json
import math
import struct
import time
import wave
from pathlib import Path

ID, CONTROL, STATUS, COUNT, SAMPLE, DROPPED, TOTAL, VERSION = range(0, 32, 4)
EXPECTED_ID = 0x41554432
EXPECTED_VERSION = 0x00010000
RATE, DEPTH = 16000, 4096


class AudioCaptureError(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__(report.get('error', 'Audio capture did not pass'))


class AudioCancelled(RuntimeError):
    pass


class AudioCapture:
    def __init__(self, mmio, clock=time.monotonic, sleep=time.sleep):
        self.mmio, self.clock, self.sleep = mmio, clock, sleep
        self.owns_capture = False
        if self.read(ID) != EXPECTED_ID or self.read(VERSION) != EXPECTED_VERSION:
            raise RuntimeError('Audio ID/version mismatch; no control writes performed')
        if self.read(CONTROL) & 1:
            raise RuntimeError('Audio producer already enabled; stop its owner first')

    def read(self, offset):
        return int(self.mmio.read(offset)) & 0xFFFFFFFF

    def status(self):
        return {name: self.read(offset) for name, offset in
                (('control', CONTROL), ('status', STATUS), ('count', COUNT),
                 ('dropped', DROPPED), ('total', TOTAL))}

    def stop(self):
        if not self.owns_capture:
            return {'owned': False}
        control = self.read(CONTROL) & ~5
        self.mmio.write(CONTROL, control)
        if self.read(CONTROL) & 1:
            raise RuntimeError('Audio disable readback failed; owner retained')
        self.sleep(0.002)
        first = self.read(TOTAL)
        self.sleep(0.002)
        second = self.read(TOTAL)
        if second != first:
            raise RuntimeError('Audio producer still changes TOTAL after disable; owner retained')
        result = self.status()
        self.owns_capture = False
        return result

    def record(self, directory, seconds=3.0, line_input=False, gain=1, cancelled=None, segment=None):
        if not math.isfinite(seconds) or not 0.25 <= seconds <= 10:
            raise ValueError('seconds must be finite and between 0.25 and 10')
        if gain not in (0, 1, 2, 3):
            raise ValueError('gain must be 0..3')
        if self.owns_capture or self.read(CONTROL) & 1:
            raise RuntimeError('Audio producer already owned/enabled')
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        target = round(seconds * RATE)
        pcm = []
        report = {'passed': False, 'sample_rate_hz': RATE, 'channels': 1, 'sample_width_bytes': 2,
                  'requested_samples': target, 'line_input': bool(line_input), 'gain': gain,
                  'fifo_depth_samples': DEPTH, 'fifo_capacity_ms': 256,
                  'board_acceptance': 'pending', 'recognition_performed': False}
        started = None
        max_gap = 0.0
        max_count = 0
        read_seconds = 0.0
        failure = None
        control = (gain << 3) | (2 if line_input else 0)
        try:
            # Claim before first control write so a partial failure remains stoppable.
            self.owns_capture = True
            self.mmio.write(CONTROL, control | 4)
            self.sleep(0.020)  # input/gain changes restart codec; do not trust stale ready
            deadline = self.clock() + 3.0
            while True:
                if cancelled and cancelled(): raise AudioCancelled('Request cancelled during codec setup')
                status = self.read(STATUS)
                if status & 12:
                    raise RuntimeError('Codec NACK/FIR overrun: 0x%x' % status)
                if status & 3 == 3:
                    break
                if self.clock() >= deadline:
                    raise TimeoutError('Audio clock/codec configuration not ready')
                self.sleep(0.005)
            self.mmio.write(CONTROL, control | 4)
            self.sleep(0.001)
            if any(self.read(reg) for reg in (COUNT, DROPPED, TOTAL)):
                raise RuntimeError('Audio flush did not clear FIFO and counters')
            started = self.clock()
            previous = started
            self.mmio.write(CONTROL, control | 1)
            deadline = started + seconds + 2.0
            while len(pcm) < target:
                if cancelled and cancelled(): raise AudioCancelled('Request cancelled during capture')
                now = self.clock()
                max_gap = max(max_gap, now - previous)
                previous = now
                if now >= deadline:
                    raise TimeoutError('PCM capture deadline exceeded')
                status = self.read(STATUS)
                if status & 3 != 3 or status & 28:
                    raise RuntimeError('Audio clock/codec/FIFO fault: 0x%x' % status)
                count = self.read(COUNT)
                if count > DEPTH:
                    raise RuntimeError('FIFO count exceeds hardware contract')
                max_count = max(max_count, count)
                if not count:
                    self.sleep(0.001)
                    continue
                # SAMPLE is a pop register. Repeated reads of this address are required.
                count = min(count, target - len(pcm), 512)
                t0 = self.clock()
                for _ in range(count):
                    word = self.read(SAMPLE) & 0xFFFF
                    pcm.append(word - 65536 if word & 0x8000 else word)
                read_seconds += self.clock() - t0
                if segment is not None and segment.feed(pcm[-count:]):
                    break
            report['before_stop'] = self.status()
        except BaseException as error:
            failure = error
            report['error'] = type(error).__name__ + ': ' + str(error)
            report['cancelled'] = isinstance(error, AudioCancelled)
        finally:
            stop_started = self.clock()
            try:
                report['after_stop'] = self.stop()
            except Exception as error:
                report['stop_error'] = repr(error)
                if failure is None:
                    failure = error
                    report['error'] = str(error)
            report['samples'] = len(pcm)
            if segment is not None: report['segmentation'] = segment.status()
            report['max_service_gap_ms'] = max_gap * 1000
            report['max_fifo_count'] = max_count
            report['sample_read_seconds'] = read_seconds
            report['sample_reads_per_second'] = len(pcm) / read_seconds if read_seconds else None
            report['capture_elapsed_s'] = stop_started - started if started is not None else None
            if pcm:
                mean = sum(pcm) / len(pcm)
                rms = math.sqrt(sum((value - mean) ** 2 for value in pcm) / len(pcm))
                report.update(mean=mean, ac_rms=rms, peak=max(abs(v) for v in pcm),
                              clipped_samples=sum(abs(v) >= 32760 for v in pcm))
            after = report.get('after_stop', {})
            if started is not None and after.get('total') is not None and stop_started > started:
                report['observed_sample_rate_hz'] = after['total'] / (stop_started - started)
            observed_rate = report.get('observed_sample_rate_hz', 0)
            report['sample_rate_within_5_percent'] = abs(observed_rate - RATE) <= RATE * 0.05
            report['counter_accounting_passed'] = (after.get('total') == len(pcm) + after.get('count', -1) + after.get('dropped', -1))
            complete = len(pcm) == target if segment is None else report['segmentation']['state_id'] in (4, 5)
            report['transport_passed'] = (failure is None and complete and
                                          after.get('dropped') == 0 and not after.get('control', 1) & 1 and
                                          after.get('status', 0) & 31 == 3 and
                                          report['sample_rate_within_5_percent'] and report['counter_accounting_passed'])
            # Nonzero AC is only a signal check, not proof that the microphone captured speech.
            report['nonconstant_signal'] = report.get('ac_rms', 0) > 0
            report['passed'] = report['transport_passed'] and (report['nonconstant_signal'] or segment is not None)
            if not report['passed'] and 'error' not in report:
                report['error'] = 'PCM transport failed or signal is constant'
            with wave.open(str(directory / 'capture.wav'), 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(RATE)
                wav.writeframes(struct.pack('<%dh' % len(pcm), *pcm))
            (directory / 'capture_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if isinstance(failure, (KeyboardInterrupt, SystemExit)):
            raise failure
        if not report['passed']:
            raise AudioCaptureError(report)
        return report
