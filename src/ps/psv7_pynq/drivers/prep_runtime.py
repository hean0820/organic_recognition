"""Reuse private PREP buffers while preserving original HLS transactions."""
import time
import numpy as np


class ReusablePrepCapture:
    def __init__(self, mmio, allocator):
        self.mmio, self.allocator = mmio, allocator
        self.frames = []
        self.dma_owned = False
        self.done_seen = False
        self.allocation_ms = None

    def _idle(self):
        control = int(self.mmio.read(0))
        if not control & 4 or control & 0x81:
            raise RuntimeError('PREP is active; retain buffers and keep this kernel open')
        return control

    def prepare(self):
        self._idle()
        if self.dma_owned:
            raise RuntimeError('PREP still owns an active transaction')
        if self.frames:
            if len(self.frames) != 5:
                raise RuntimeError('Incomplete PREP allocation; close before preparing')
            return
        started = time.perf_counter()
        try:
            for count in (691200, 42720, 30240, 60256, 30240):
                buf = self.allocator(shape=(count,), dtype=np.uint32)
                self.frames.append(buf)
                address = int(buf.physical_address)
                if address & 63 or address <= 0 or address + buf.nbytes > 0x40000000:
                    raise RuntimeError('PREP requires aligned buffers within board DDR')
                buf.fill(0xA5A5A5A5)
        except Exception:
            self.close()
            raise
        self.allocation_ms = (time.perf_counter() - started) * 1000

    def run(self, frame, timeout_s=5.0):
        self._idle()
        if self.dma_owned:
            raise RuntimeError('PREP still owns an active transaction')
        if frame.shape != (720, 1280, 3) or frame.dtype != np.uint8 or not frame.flags.c_contiguous:
            raise ValueError('PREP needs a contiguous 720x1280 BGR uint8 frame')
        self.prepare()
        timing = {}
        started = time.perf_counter()
        # Copy directly into the private input, without a full-frame bytes object.
        direct_input=(getattr(self,'input_lease_active',False) and
                      frame.ctypes.data==self.frames[0].ctypes.data and frame.nbytes==self.frames[0].nbytes)
        if not direct_input:
            np.copyto(np.asarray(self.frames[0]), np.asarray(frame).reshape(-1).view('<u4'))
        for buf in self.frames[1:]:
            buf.fill(0xA5A5A5A5)
        timing['input_copy_output_reset_ms'] = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        for buf in self.frames:
            buf.flush()
        timing['flush_ms'] = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        self.mmio.write(4, 0)
        self.mmio.write(8, 0)
        for offset, buf in zip((0x18, 0x24, 0x30, 0x3C, 0x48), self.frames):
            self.mmio.write(offset, int(buf.physical_address))
            self.mmio.write(offset + 4, 0)
            if int(self.mmio.read(offset)) != int(buf.physical_address):
                raise RuntimeError('PREP pointer readback mismatch')
        self.mmio.write(0x54, 960)
        self.mmio.write(0x5C, 0)
        timing['register_setup_ms'] = (time.perf_counter() - started) * 1000
        self.dma_owned = True
        self.done_seen = False
        started = time.monotonic()
        try:
            self.mmio.write(0, 1)
            while True:
                control = int(self.mmio.read(0))
                self.done_seen = self.done_seen or bool(control & 2)
                if self.done_seen and control & 4 and not control & 0x81:
                    break
                if time.monotonic() - started >= timeout_s:
                    raise TimeoutError('PREP did not confirm DONE and IDLE: ' + hex(control))
                time.sleep(0.001)
            self.dma_owned = False
            timing['done_idle_wait_ms'] = (time.monotonic() - started) * 1000
            return_value = int(self.mmio.read(0x10))
            if return_value:
                raise RuntimeError('PREP returned ' + str(return_value))
            output_started = time.perf_counter()
            for buf in self.frames[1:]:
                buf.invalidate()
            # Plain independent NumPy arrays survive reuse of the private buffers.
            outputs = (
                np.array(self.frames[1].view(np.uint8).reshape(267, 640), copy=True, subok=False),
                np.array(self.frames[2].view(np.uint8).reshape(224, 540)[:, :537], copy=True, subok=False),
                np.array(self.frames[3].view(np.uint16).reshape(224, 538)[:, :537], copy=True, subok=False),
                np.array(self.frames[4].view(np.uint8).reshape(224, 540)[:, :537], copy=True, subok=False))
            padding = [int(np.count_nonzero(self.frames[i].view(np.uint8).reshape(224, 540)[:, 537:])) for i in (2, 4)]
            padding.append(int(np.count_nonzero(self.frames[3].view(np.uint16).reshape(224, 538)[:, 537:])))
            if any(padding):
                raise AssertionError('PREP output padding differs from original HLS')
            timing['invalidate_copy_check_ms'] = (time.perf_counter() - output_started) * 1000
            return outputs, {'control': hex(control), 'return_value': return_value,
                            'hardware_wait_ms': (time.monotonic() - started) * 1000,
                            'padding_nonzero': padding, 'timings_ms': timing,
                            'input_copy_skipped':bool(direct_input),
                            'retained_idle_buffers': len(self.frames),
                            'startup_allocation_ms': self.allocation_ms}
        except Exception:
            # Never free while START/auto-restart is set or IDLE is absent.
            control = int(self.mmio.read(0))
            if control & 4 and not control & 0x81:
                self.dma_owned = False
            raise

    def close(self):
        if self.frames or self.dma_owned:
            self._idle()
        self.dma_owned = False
        while self.frames:
            self.frames[-1].freebuffer()
            self.frames.pop()
