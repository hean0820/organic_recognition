"""Independent PREP-only owner; CNN model BOs belong to UnifiedCnn."""
import threading
from contextlib import contextmanager
import time
import numpy as np
from .prep_runtime import ReusablePrepCapture


class ManagedSpeedEngine(ReusablePrepCapture):
    def __init__(self,mmio,allocator):
        super().__init__(mmio,allocator)
        self.lock=threading.RLock()
        self.identity_verified=False

    @property
    def all_frames(self):return self.frames

    def prepare(self):
        with self.lock:
            if not self.identity_verified:self.verify_identity()
            super().prepare()

    def run(self,frame,timeout_s=5.0):
        with self.lock:return super().run(frame,timeout_s)

    @contextmanager
    def input_target(self):
        """Borrow only this engine's private input while idle under its RLock.
        The caller also holds the app lock through rendering/diagnostic saving.
        No camera DMA buffer is exposed to the PREP master.
        """
        with self.lock:
            self._idle()
            if self.dma_owned or getattr(self,'input_lease_active',False):
                raise RuntimeError('PREP input lease unavailable; retain ownership')
            self.prepare();self.input_lease_active=True
            try:yield np.asarray(self.frames[0]).view(np.uint8).reshape(720,1280,3)
            finally:self.input_lease_active=False

    def recover_idle(self):
        with self.lock:
            try:self._idle()
            except RuntimeError:return False
            self.dma_owned=False;self.done_seen=False
            return True

    def verify_identity(self):
        with self.lock:
            self._idle()
            if self.dma_owned:raise RuntimeError('PREP transaction unresolved')
            self.mmio.write(4,0);self.mmio.write(8,0);self.mmio.write(0x5c,4)
            self.dma_owned=True;self.done_seen=False
            self.mmio.write(0,1);deadline=time.monotonic()+1.0
            while True:
                control=int(self.mmio.read(0));self.done_seen |= bool(control&2)
                if self.done_seen and control&4 and not control&0x81:break
                if time.monotonic()>=deadline:raise TimeoutError('PREP identity query unresolved; retain owner')
                time.sleep(0.0001)
            self.dma_owned=False
            if int(self.mmio.read(0x10))!=0x50525001:raise RuntimeError('Wrong PREP-only identity; old tail hardware rejected')
            self.identity_verified=True

    def close(self):
        with self.lock:super().close()
