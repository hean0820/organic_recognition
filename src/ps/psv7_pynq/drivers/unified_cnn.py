"""S1 ABI: independent model ownership and one START for the complete CNN."""
import hashlib
import json
import threading
import time
from pathlib import Path
import numpy as np

ID=0x4352544C
ABI=0x00010000
QUIET=1
BUSY=2
DONE=4
ERROR=8
RESULT=16
DRAINING=32
RECOVERY=64
CONFIG=128
INPUT=256


class UnifiedCnn:
    def __init__(self, mmio, allocator, contract_path):
        self.mmio,self.allocator=mmio,allocator
        self.contract=json.loads(Path(contract_path).read_text(encoding='utf-8'))
        self.lock=threading.RLock()
        self.frames=[]
        self.dma_owned=False
        self.model_ready=False

    def _read(self, offset):return int(self.mmio.read(offset))

    def verify_identity(self):
        for offset,value in self.contract['register_constants'].items():
            if self._read(int(offset,0))!=int(value,0):
                raise RuntimeError('Unified CNN identity/ABI/model mismatch at '+offset)

    def snapshot(self):
        out={name:self._read(offset) for name,offset in (
            ('id',0),('status',8),('error',12),('sequence',16),('stage',20),
            ('input_count',24),('output_count',28),('pool3_count',32),('logit_count',36),
            ('outstanding',48),('ar_pending',52),('error_detail',100),
            ('fault_flags',204),('result_sequence',208))}
        low=self._read(40);high=self._read(44)
        out['cycles']=low|(high<<32)
        return out

    def _safe(self):
        status=self._read(8)
        return bool(status&QUIET) and not status&(BUSY|DRAINING|RECOVERY) and not self._read(48) and not self._read(52)

    def release_guard(self):
        if not self.lock.acquire(blocking=False):return False
        try:return not self.dma_owned and self._safe()
        finally:self.lock.release()

    def _wait_safe(self, timeout_s):
        deadline=time.monotonic()+timeout_s
        while True:
            if self._safe():
                self.dma_owned=False
                return
            if time.monotonic()>=deadline:
                raise TimeoutError('CNN has pending DDR/recovery; retain model BOs and owner: '+repr(self.snapshot()))
            time.sleep(0.0001)

    def recover(self, timeout_s=2.0):
        with self.lock:
            self.verify_identity()
            # The hardware keeps any asserted AR and drains accepted R traffic.
            self.dma_owned=True
            status=self._read(8)
            if status&(BUSY|DRAINING):self.mmio.write(4,4)
            self._wait_safe(timeout_s)
            if self._read(8)&DONE:self.mmio.write(4,2)
            self.mmio.write(4,8)
            if not self._safe() or self._read(8)&(ERROR|DONE|RESULT):
                raise RuntimeError('CNN CLEAR did not confirm clean quiescence')

    def load_model(self, asset_folder):
        with self.lock:
            self.verify_identity()
            if self.dma_owned or not self._safe() or self._read(8)&(DONE|ERROR|RESULT):
                raise RuntimeError('CNN model replacement requires clean idle ownership')
            if self.frames:raise RuntimeError('CNN model already allocated; close before replacement')
            blobs=[]
            for name,valid,allocated in (('cnn_model_weights.bin',169248,169280),('cnn_model_bias.bin',472,512)):
                blob=(Path(asset_folder)/name).read_bytes()
                if len(blob)!=valid or hashlib.sha256(blob).hexdigest()!=self.contract['assets_sha256'][name]:
                    raise ValueError('Frozen CNN model asset mismatch: '+name)
                blobs.append((blob,allocated))
            try:
                ranges=[]
                for blob,allocated in blobs:
                    frame=self.allocator(shape=(allocated,),dtype=np.uint8)
                    self.frames.append(frame)
                    address=int(frame.physical_address)
                    if address<=0 or address&63 or address+allocated>0x40000000 or frame.nbytes!=allocated or not frame.flags.c_contiguous:
                        raise RuntimeError('CNN model requires contiguous aligned BO in reachable DDR')
                    if any(address<end and begin<address+allocated for begin,end in ranges):
                        raise RuntimeError('CNN model BOs overlap')
                    ranges.append((address,address+allocated))
                    frame.fill(0);frame[:len(blob)]=np.frombuffer(blob,np.uint8)
                    frame.flush()
                self._configure()
                self.model_ready=True
            except Exception:
                self.close();raise

    def _configure(self):
        if not self._safe() or self.dma_owned:raise RuntimeError('CNN configuration while owned')
        for offset,value in ((0x40,int(self.frames[0].physical_address)),(0x44,169248),(0x48,169280),
            (0x4c,int(self.frames[1].physical_address)),(0x50,472),(0x54,512),(0x58,0xb91cb580),
            (0x5c,100000000),(0x60,10000000)):
            self.mmio.write(offset,value)
            if self._read(offset)!=value:raise RuntimeError('CNN config readback mismatch')
        if not self._read(8)&CONFIG:raise RuntimeError('CNN rejected model configuration')

    def _debug(self, selector, count):
        if not self._safe() or self._read(8)&(DONE|RESULT)!=(DONE|RESULT):
            raise RuntimeError('CNN debug requires safe valid DONE')
        self.mmio.write(0xa0,selector)
        data=np.empty(count,np.uint8)
        for i in range(count):
            self.mmio.write(0xa4,i);data[i]=self._read(0xa8)
        return data

    def infer(self, image, transfer, timeout_s=2.0, diagnostics=False):
        if not 0<timeout_s<=30:raise ValueError('Invalid CNN software timeout')
        with self.lock:
            if not self.model_ready:raise RuntimeError('CNN model not loaded')
            self.verify_identity()
            if self.dma_owned or not self._safe() or self._read(8)&(DONE|ERROR|RESULT):
                raise RuntimeError('CNN transaction unresolved; recover before another START')
            previous=self._read(16);started=time.perf_counter();timings={}
            transfer.write_input(image)
            transfer.verify_input(image)
            if self._read(24)!=4096 or not self._read(8)&INPUT:raise RuntimeError('CNN input incomplete')
            timings['input_write_ms']=(time.perf_counter()-started)*1000
            wait_start=time.monotonic()
            # Mark ownership before writing START: even a bus exception is uncertain.
            self.dma_owned=True
            try:
                self.mmio.write(4,1)
                expected=(previous+1)&0xffffffff
                while True:
                    status=self._read(8)
                    if status&ERROR:raise RuntimeError('CNN hardware error: '+repr(self.snapshot()))
                    if status&(DONE|RESULT)==DONE|RESULT and self._safe():break
                    if time.monotonic()-wait_start>=timeout_s:raise TimeoutError('CNN inference timed out')
                    time.sleep(0.0001)
                timings['cnn_done_wait_ms']=(time.monotonic()-wait_start)*1000
                hw=self.snapshot()
                if (hw['sequence']!=expected or hw['result_sequence']!=expected or hw['error'] or
                    [hw[k] for k in ('input_count','output_count','pool3_count','logit_count')]!=[4096,12288,3072,22]):
                    raise RuntimeError('CNN completion/sequence/count mismatch: '+repr(hw))
                logits=transfer.read_logits()
                if logits.dtype!=np.int32 or logits.shape!=(22,):raise RuntimeError('CNN logits ABI mismatch')
                arrays={'logits':logits}
                wall=(time.perf_counter()-started)*1000
                if diagnostics:
                    arrays.update(features=self._debug(1,12288),pool3=self._debug(2,3072),relu=self._debug(3,48))
                self.dma_owned=False
                self.mmio.write(4,2)
                if not self._safe() or self._read(8)&(DONE|RESULT|ERROR):raise RuntimeError('CNN ACK failed')
                return {'transaction_passed':True,'predicted':int(logits.argmax()),'hardware':hw,
                    'final_state':self.snapshot(),'inference_wall_ms':wall,'phase_wall_ms':timings,
                    'transfer_backend':transfer.backend,'_diagnostic_arrays':arrays,
                    'network':'CNN3_QAT_24_48_48','network_conv_layers':3,'cnn_implementation':'UNIFIED_HANDWRITTEN_RTL',
                    'frontend_scope':'Conv1/Conv2/Conv3/Pool1/Pool2/Pool3/FC1/FC2',
                    'frontend_feature_bytes':12288,'pool3_feature_bytes':3072,
                    'fc_us':0,'fc':{'backend':'UNIFIED_HANDWRITTEN_RTL','hardware_wait_ms':0},
                    'inference_wall_scope':'Input MMIO, one START, complete CNN DONE, 22 signed logits; excludes diagnostic reads, ACK, PREP and display'}
            except Exception as original:
                try:self.recover()
                except Exception as recovery:
                    raise RuntimeError('CNN recovery unresolved; owner and model retained: '+repr(recovery)) from original
                raise

    def close(self):
        with self.lock:
            if self.frames or self.dma_owned:
                self.recover()
                # Invalidate configuration before returning physical BOs.
                self.mmio.write(0x58,0);self.mmio.write(0x40,0);self.mmio.write(0x4c,0)
            self.model_ready=False
            while self.frames:
                self.frames[-1].freebuffer();self.frames.pop()
