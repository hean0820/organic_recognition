"""PSv7 live preview and command-triggered recognition, using the original UI.
Loaded bridge Overlay is reused. All hardware work is serialized by one lock.
"""
import ctypes
import hashlib
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from .voice_service import VoiceApplicationMixin

WIDTH, HEIGHT, STRIDE = 1280, 720, 3840
ERROR_MASK = 0x8FF0


def wait_until(predicate, label, timeout=2.0):
    end = time.monotonic()+timeout
    while not predicate():
        if time.monotonic() >= end: raise TimeoutError(label)
        time.sleep(0.001)


class NativePage:
    def __init__(self,folder):
        sources = folder/'native'
        names = ['native_wrapper.c', 'preview_compose.c', 'ui_panel.c', 'ui_font.c', 'chem_db.c', 'preprocess.c', 'cnn_fc.c', 'app_control.c', 'ui_font_extra.c', 'mol_render.c', 'mol_selection.c', 'mol_board.c', 'molecule_models.c', 'chem22.c', 'voice_capture.c', 'voice_recognizer.c', 'voice_bridge.c', 'cnn_mmio.c', 'frame_copy.c', 'preprocess_reference.c']
        inputs=[p for p in sorted(sources.iterdir()) if p.is_file()]
        inputs.append(folder/'assets/camera_pipeline_reference/preprocess_0_7_0.c')
        digest = hashlib.sha256(b''.join(p.read_bytes() for p in inputs)).hexdigest()
        # dlopen may reuse a library already loaded at the same path. Give each
        # source version its own immutable path; never overwrite a mapped file.
        cache = folder/'reports/native';cache.mkdir(parents=True,exist_ok=True)
        output = cache/('libpsv7_ui_'+digest+'.so')
        if not output.exists():
            temporary=cache/(output.name+'.build_'+str(time.time_ns()))
            print('PSV7_NATIVE_BUILD',output.name,flush=True)
            command = ['gcc','-O2','-std=c99','-D_POSIX_C_SOURCE=200809L','-shared','-fPIC',
                       '-I',str(sources),'-o',str(temporary)]+[str(sources/n) for n in names]+['-lm']
            try:
                result = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
                if result.returncode:
                    raise RuntimeError('Native PSv7 UI build failed: '+result.stderr)
                temporary.replace(output)
            finally:
                if temporary.exists():temporary.unlink()
        self._bind_library(ctypes.CDLL(str(output)))
        print('PSV7_NATIVE_LIBRARY_READY',output.name,flush=True)

    def _bind_library(self,library):
        self.lib=library
        ptr, u = ctypes.c_void_p,ctypes.c_uint32
        signatures = {
            'psv7_create':([],ptr),'psv7_destroy':([ptr],None),'psv7_class_name':([u],ctypes.c_char_p),
            'psv7_missing_glyphs':([],u),'psv7_render':([ptr,ptr,ptr,u,u,u,u,u],ctypes.c_int),
            'psv7_validate_rgb565':([ptr,u],u),
            'psv7_copy_validate_rgb565':([ptr,ptr,u],u),
            'psv7_postprocess':([ptr,ptr,ptr,ptr,ptr,ptr],ctypes.c_int),
            'psv7_postprocess_reference':([ptr,ptr,ptr,ptr,ptr,ptr],ctypes.c_int),
            'psv7_begin':([ptr],None),'psv7_clear':([ptr],None),'psv7_select':([ptr,u],ctypes.c_int),
            'psv7_publish':([ptr,ptr,ptr,ptr],None),
            'psv7_fc':([ptr,ptr,ptr,ptr,ptr,ctypes.c_int32,ptr,ptr,ptr,ptr],ctypes.c_int)}
        signatures.update({
            'psv7_model_info':([ptr,ptr],ctypes.c_int),
            'psv7_model_pause':([ptr],ctypes.c_int),
            'psv7_model_reset':([ptr],ctypes.c_int),
            'psv7_presented':([ptr],None)})
        for name,(args,ret) in signatures.items():
            method=getattr(self.lib,name);method.argtypes=args;method.restype=ret
        self.handle=self.lib.psv7_create()
        if not self.handle: raise RuntimeError('PSv7 UI unavailable: allocation failed or another page still owns the model workspace')

    def postprocess(self,outputs,reference=False):
        image=np.zeros((64,64),np.uint8);raw=np.zeros(27,np.uint32)
        function=self.lib.psv7_postprocess_reference if reference else self.lib.psv7_postprocess
        code=function(self.handle,outputs[0].ctypes.data,outputs[1].ctypes.data,
                                     outputs[3].ctypes.data,image.ctypes.data,raw.ctypes.data)
        if code < 0: raise RuntimeError('Native postprocess failed')
        from ..drivers.reference_pipeline import REPORT_FIELDS,CODES
        report={key:int(raw[i]) for i,key in enumerate(REPORT_FIELDS)}
        report.update(stage_us=[int(v) for v in raw[20:26]],total_us=int(raw[26]),code_name=CODES[code])
        return image,raw,report

    def render(self,source,destination,index,fps,frames,read_error,write_error):
        result=self.lib.psv7_render(self.handle,source.ctypes.data,destination.ctypes.data,index,fps,frames,read_error,write_error)
        if result < 0: raise RuntimeError('Original PSv7 UI render failed')

    def model_info(self):
        if not self.handle:return {'active':False,'closed':True}
        values=np.zeros(10,np.uint32)
        if self.lib.psv7_model_info(self.handle,values.ctypes.data):raise RuntimeError('3D status unavailable')
        names=('active','class_id','paused','renders','presents','render_us_last','render_errors','angle_milli','result_valid','result_source')
        return {name:int(value) for name,value in zip(names,values)}

    def presented(self):self.lib.psv7_presented(self.handle)

    def validate_frame(self,frame):
        if frame.dtype!=np.uint8 or frame.shape!=(720,1280,3) or not frame.flags.c_contiguous:
            raise ValueError('Pixel check needs a contiguous 720x1280 BGR uint8 frame')
        return int(self.lib.psv7_validate_rgb565(frame.ctypes.data,720*1280))

    def copy_validate_frame(self,source,destination):
        for frame in (source,destination):
            if (not isinstance(frame,np.ndarray) or frame.dtype!=np.uint8 or
                    frame.shape!=(720,1280,3) or not frame.flags.c_contiguous):
                raise ValueError('Fused snapshot requires contiguous 720x1280 BGR uint8 arrays')
        if sys.byteorder!='little' or not destination.flags.writeable or np.shares_memory(source,destination):
            raise ValueError('Fused snapshot needs little-endian nonoverlapping writable output')
        result=int(self.lib.psv7_copy_validate_rgb565(source.ctypes.data,destination.ctypes.data,720*1280))
        if result==0xffffffff:raise RuntimeError('Native fused snapshot contract failed')
        return result

    def close(self):
        if self.handle: self.lib.psv7_destroy(self.handle);self.handle=None

    def fc(self,features,params):
        raise RuntimeError('Camera inference requires unified RTL CNN; legacy CPU FC is disabled')


class ParkedCapture:
    def __init__(self,vdma,allocator):
        self.video,self.allocator=vdma,allocator
        self.frames=[];self.dma_owned=False
        self.validate_frame=None
        self.copy_validate_frame=None
        self.snapshot_policy='HEAP_MEMCPY_CHECK'

    def prepare(self):
        if self.frames or self.dma_owned: raise RuntimeError('Capture still owns buffers')
        if any(int(self.video.read(c))&1 or not int(self.video.read(s))&1 for c,s in ((0,4),(0x30,0x34))):
            raise RuntimeError('Prepare only while both video channels are halted')
        self.dma_owned=True
        self.video.write(0x30,4)
        wait_until(lambda:not int(self.video.read(0x30))&4,'S2MM reset stuck')
        for _ in range(3):
            frame=self.allocator(shape=(720,1280,3),dtype=np.uint8);self.frames.append(frame)
            address=int(frame.device_address)
            if address&7 or address<0 or address+frame.nbytes>0x40000000: raise ValueError('Capture DDR address invalid')
            frame.fill(0xA5);frame.flush()

    def start(self):
        v=self.video
        v.write(0x34,0xFFF0);v.write(0x3C,0);v.write(0x44,0)
        for index,frame in enumerate(self.frames):v.write(0xAC+4*index,int(frame.device_address))
        v.write(0xA4,STRIDE);v.write(0xA8,STRIDE)
        v.write(0x28,int(v.read(0x28))&~0x1F00)
        control=(int(v.read(0x30))&~(2|8|16|0xF00|0xFFFF0000|0x7000))|0x15001
        v.write(0x30,control);v.write(0xA0,HEIGHT)

    def acquire(self,timeout=3.0,destination=None,handoff_policy=None):
        """Freeze a fresh complete source; startup/preview keep legacy ordering."""
        if destination is not None:
            if (not isinstance(destination,np.ndarray) or destination.dtype!=np.uint8 or
                    destination.shape!=(720,1280,3) or not destination.flags.c_contiguous or
                    not destination.flags.writeable):
                raise ValueError('Capture destination must be a writable contiguous BGR frame')
            if any(np.shares_memory(destination,frame) for frame in self.frames):
                raise ValueError('Capture destination must not alias any VDMA source buffer')
        from ..drivers.camera_handoff import LEGACY,freeze_source,check_frozen_source
        policy=handoff_policy or LEGACY
        old,timing=freeze_source(self.video,policy,timeout)
        target=timing['writer_target_slot']
        started=time.perf_counter()
        self.frames[old].invalidate()
        timing['invalidate_ms']=(time.perf_counter()-started)*1000
        started=time.perf_counter()
        if destination is None and self.snapshot_policy=='HEAP_MEMCPY_CHECK':
            result=np.array(self.frames[old],copy=True,subok=False)
            timing['snapshot_copy_ms']=(time.perf_counter()-started)*1000
            checked=time.perf_counter()
            violations=(self.validate_frame(result) if self.validate_frame is not None else
                        np.count_nonzero((result[:,:,0]&7)|(result[:,:,1]&3)|(result[:,:,2]&7)))
            timing['snapshot_check_ms']=(time.perf_counter()-checked)*1000
        elif self.copy_validate_frame is not None:
            result=destination if destination is not None else np.empty((720,1280,3),np.uint8)
            violations=self.copy_validate_frame(np.asarray(self.frames[old]),result)
        else:
            result=destination if destination is not None else np.empty((720,1280,3),np.uint8)
            np.copyto(result,np.asarray(self.frames[old]))
            violations=(self.validate_frame(result) if self.validate_frame is not None else
                        np.count_nonzero((result[:,:,0]&7)|(result[:,:,1]&3)|(result[:,:,2]&7)))
        timing['snapshot_copy_validate_ms']=(time.perf_counter()-started)*1000
        timing['snapshot_destination']='PRIVATE_PREP_INPUT' if destination is not None else 'INDEPENDENT_HEAP'
        timing['snapshot_policy']='EXPERIMENTAL_DIRECT_PREP' if destination is not None else self.snapshot_policy
        if violations:
            raise RuntimeError('Frozen capture has invalid RGB565-expanded low bits')
        check_frozen_source(self.video,old,target)
        self.last_timing=timing
        return result,old

    def close(self):
        if self.dma_owned:
            v=self.video;v.write(0x30,int(v.read(0x30))&~1)
            try:wait_until(lambda:int(v.read(0x34))&1,'S2MM did not halt')
            except TimeoutError:
                v.write(0x30,4)
                wait_until(lambda:not int(v.read(0x30))&4,'S2MM reset stuck; retain buffers')
                wait_until(lambda:int(v.read(0x34))&1,'S2MM not halted; retain buffers')
            self.dma_owned=False
        while self.frames:self.frames[-1].freebuffer();self.frames.pop()


class ParkedDisplay:
    def __init__(self,vdma,vtc,allocator):
        self.vdma,self.vtc,self.allocator=vdma,vtc,allocator
        self.frames=[];self.dma_owned=False;self.front=0

    @property
    def frame(self):return self.frames[0] if self.frames else None

    def prepare(self):
        if self.frames:raise RuntimeError('Display buffers retained')
        for _ in range(3):
            frame=self.allocator(shape=(720,1280,3),dtype=np.uint8);self.frames.append(frame)
            address=int(frame.device_address)
            if address&7 or address<0 or address+frame.nbytes>0x40000000:raise ValueError('Display DDR address invalid')
            frame.fill(0x12)

    def start(self):
        from ..drivers.video_recipe import configure_vtc_720p
        v=self.vdma
        if int(v.read(0))&1:raise RuntimeError('MM2S already running')
        self.dma_owned=True
        v.write(0,4);wait_until(lambda:not int(v.read(0))&4,'MM2S reset stuck')
        v.write(4,0x7FF0);configure_vtc_720p(self.vtc);v.write(0x14,0)
        for index,frame in enumerate(self.frames):frame.flush();v.write(0x5C+4*index,int(frame.device_address))
        v.write(0x54,STRIDE);v.write(0x58,STRIDE);v.write(0x28,int(v.read(0x28))&~31)
        v.write(0,0x11001);v.write(0x50,HEIGHT)
        self.vtc.write(0,int(self.vtc.read(0))|7)
        def event():
            status=int(v.read(4))
            if status&ERROR_MASK:raise RuntimeError('MM2S error '+hex(status))
            return bool(status&0x1000)
        wait_until(event,'MM2S did not complete first frame');self.front=0

    def back(self):return (self.front+1)%3

    def present(self,index):
        v=self.vdma
        if index==self.front:raise RuntimeError('Do not modify the currently displayed buffer')
        self.frames[index].flush();v.write(4,0x1000)
        v.write(0x28,(int(v.read(0x28))&~31)|index)
        def moved():
            status=int(v.read(4))
            if status&ERROR_MASK:raise RuntimeError('MM2S error during presentation '+hex(status))
            return ((int(v.read(0x28))>>16)&31)==index
        wait_until(moved,'MM2S parking not acknowledged');self.front=index

    def close(self):
        if self.dma_owned:
            v=self.vdma;v.write(0,int(v.read(0))&~1)
            try:wait_until(lambda:int(v.read(4))&1,'MM2S did not halt')
            except TimeoutError:
                v.write(0,4);wait_until(lambda:not int(v.read(0))&4,'MM2S reset stuck; retain buffers')
                wait_until(lambda:int(v.read(4))&1,'MM2S not halted; retain buffers')
            self.dma_owned=False
        if self.frames:self.vtc.write(0,int(self.vtc.read(0))&~4)
        while self.frames:self.frames[-1].freebuffer();self.frames.pop()


class Psv7App(VoiceApplicationMixin):
    def __init__(self,overlay,folder):
        from pynq import MMIO,allocate
        from ..drivers.speed_engine import ManagedSpeedEngine
        from ..drivers.managed_memory import ManagedAllocator,cma_snapshot,driver_memory_snapshot
        from ..drivers import psv7_sccb as sccb
        self.overlay,self.folder=overlay,Path(folder)
        self.vdma=MMIO(0x43000000,0x10000);self.vtc=MMIO(0x43C10000,0x10000)
        self.bridge=MMIO(0x41200000,0x10000);self.cnn=MMIO(0x43C00000,0x10000)
        self.capture=ParkedCapture(self.vdma,allocate);self.display=ParkedDisplay(self.vdma,self.vtc,allocate)
        self.prep=ManagedSpeedEngine(MMIO(0x43C20000,0x10000),allocate)
        from ..drivers.unified_cnn import UnifiedCnn
        self.unified=UnifiedCnn(self.cnn,allocate,self.folder/'assets/cnn_rtl_contract.json')
        self.memory=ManagedAllocator(overlay.device,allocate)
        self.capture.allocator=self.memory.for_owner('camera',lambda:self._video_released(self.capture,0x30,0x34))
        self.display.allocator=self.memory.for_owner('display',lambda:self._video_released(self.display,0,4))
        self.prep.allocator=self.memory.for_owner('prep',self._prep_released)
        self.unified.allocator=self.memory.for_owner('cnn_model',self.unified.release_guard)
        self.cma_before=cma_snapshot();self.driver_before=driver_memory_snapshot(overlay.device)
        self.lines=sccb.LinuxSccbLines(sccb.discover_gpio())
        self.page=None;self.cnn_io=None;self.running=False;self.last_frame=None;self.last_result=None
        self.camera_timing=None
        self.camera_handoff_policy='LEGACY_TWO_EVENTS_THEN_PARK'
        self.preview_handoff_policy='OVERLAP_SECOND_EVENT_WITH_PARK'
        self.requests=None;self.voice_model=None;self.audio=None
        self.voice_worker=None;self.voice_result=None;self.voice_sequence=0
        self.reference_voice_token=None
        self.frames_presented=0;self.capture_sequence=0;self.fps10=0
        self.lock=threading.RLock();self.stop_event=threading.Event();self.worker=None;self.worker_error=None
        self.report_folder=self.folder/'reports/board'/('psv7_app_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
        self.report_folder.mkdir(parents=True);self.started=time.monotonic();self.fps_start=self.started;self.fps_frames=0

    @property
    def frames(self):return self.capture.frames+self.display.frames+self.prep.all_frames+self.unified.frames
    @property
    def dma_owned(self):return self.capture.dma_owned or self.display.dma_owned or self.prep.dma_owned or self.unified.dma_owned

    def _video_released(self,owner,control,status):
        return not owner.dma_owned and not int(self.vdma.read(control))&1 and bool(int(self.vdma.read(status))&1)

    def _prep_released(self):
        if not self.prep.lock.acquire(blocking=False):return False
        try:
            if self.prep.dma_owned:return False
            control=int(self.prep.mmio.read(0))
            return bool(control&4) and not control&0x81
        finally:self.prep.lock.release()

    def _render(self,index):
        self._sync_request()
        self.page.render(self.last_frame,self.display.frames[index],index,self.fps10,self.frames_presented,
                         int(self.vdma.read(4))&ERROR_MASK,int(self.vdma.read(0x34))&ERROR_MASK)

    def start(self):
        from ..drivers import psv7_camera as camera
        with self.lock:
            print('PSV7_APP_STAGE BUILD_NATIVE_PAGE',flush=True)
            self.page=NativePage(self.folder)
            self.init_voice()
            from ..drivers.cnn_native_io import NativeCnnTransfer
            self.cnn_io=NativeCnnTransfer(self.cnn,self.page.lib)
            print('PSV7_CNN_TRANSFER_READY',self.cnn_io.backend,flush=True)
            print('PSV7_VOICE_MODEL_SELFTEST_PASS',flush=True)
            self.capture.validate_frame=self.page.validate_frame
            self.capture.copy_validate_frame=self.page.copy_validate_frame
            print('PSV7_CAMERA_SNAPSHOT_READY',self.capture.snapshot_policy,'CRC32_TABLE256',flush=True)
            with np.load(self.folder/'assets/fc_parameters.npz',allow_pickle=False) as data:
                self.params={k:data[k].copy() for k in data.files}
            with np.load(self.folder/'assets/golden_data.npz',allow_pickle=False) as data:self.labels=data['class_zh'].copy()
            for i,label in enumerate(self.labels):
                if self.page.lib.psv7_class_name(i).decode('utf-8')!=str(label):raise RuntimeError('Original UI class order mismatch')
            self.bridge.write(4,0);self.bridge.write(0,0)
            print('PSV7_APP_STAGE PREPARE_VIDEO_BUFFERS',flush=True)
            self.capture.prepare();self.display.prepare()
            print('PSV7_APP_STAGE PREPARE_PRIVATE_PREP_BUFFERS',flush=True)
            self.prep.prepare()
            print('PSV7_APP_STAGE LOAD_UNIFIED_CNN_MODEL',flush=True)
            self.unified.load_model(self.folder/'assets')
            print('PSV7_APP_STAGE SENSOR_CONFIG_BEGIN',flush=True)
            self.lines.open()
            try:
                reader=camera.CameraSccb(camera.KernelOwnedInputView(self.lines,MMIO_for_gpio()))
                table=json.loads((self.folder/'assets/ov5640_720p_config.json').read_text())
                self.sensor_config=camera.configure_sensor(reader,table)
                if reader.read_register(0x3008)!=2:raise RuntimeError('Sensor not in original active mode')
            finally:
                errors=self.lines.close()
                if errors or self.lines.owned:raise RuntimeError('GPIO cleanup incomplete')
            print('PSV7_APP_STAGE SENSOR_CONFIG_COMPLETE',flush=True)
            time.sleep(0.4);self.capture.start();self.bridge.write(0,3)
            print('PSV7_APP_STAGE RELEASE_BRIDGE',flush=True)
            wait_until(lambda:(int(self.bridge.read(8))&63)==15,'Bridge not released/locked or error present')
            print('PSV7_APP_STAGE ACQUIRE_FIRST_FRAME',flush=True)
            self.last_frame,_=self.capture.acquire()
            for i in range(3):self._render(i)
            print('PSV7_APP_STAGE START_HDMI',flush=True)
            self.display.start();self.page.presented();self.running=True
            print('PSV7_APP_HDMI_STARTED',self.status(),flush=True)
            print('REPORT_DIRECTORY',str(self.report_folder),flush=True)
            return self

    def _check(self):
        if not self.running:raise RuntimeError('Application is not running: '+repr(self.worker_error))
        if (int(self.bridge.read(8))&63)!=15:raise RuntimeError('Bridge error or reset not released')
        for offset in (4,0x34):
            status=int(self.vdma.read(offset))
            if status&ERROR_MASK or status&1:raise RuntimeError('Video channel halted/error '+hex(status))

    def set_preview_handoff_policy(self,policy):
        from ..drivers.camera_handoff import POLICIES
        if policy not in POLICIES:raise ValueError('Unknown preview handoff policy')
        with self.lock:
            self._check()
            if self.requests.status()['active'] or (self.voice_worker and self.voice_worker.is_alive()):
                raise RuntimeError('Wait for the active request before changing preview policy')
            if getattr(self,'_preview_diagnostic_owner',None) is not None:
                raise RuntimeError('Do not switch preview policy during a sampling window')
            self.preview_handoff_policy=policy
            return policy

    def _step(self):
        self._check();self.last_frame,_=self.capture.acquire(handoff_policy=self.preview_handoff_policy)
        index=self.display.back();self._render(index);self.display.present(index);self.page.presented()
        self.frames_presented+=1
        elapsed=time.monotonic()-self.fps_start
        if elapsed>=1:
            self.fps10=int((self.frames_presented-self.fps_frames)*10/elapsed)
            self.fps_start=time.monotonic();self.fps_frames=self.frames_presented

    def start_preview(self):
        if self.worker and self.worker.is_alive():raise RuntimeError('Preview already running')
        self.stop_event.clear()
        def run():
            try:
                while not self.stop_event.is_set():
                    with self.lock:
                        if not self.stop_event.is_set():self._step()
                    self.stop_event.wait(0.01)
            except Exception as error:
                self.worker_error=repr(error);self.stop_event.set()
                print('PSV7_APP_PREVIEW_FAILED',repr(error),flush=True)
                try:self.stop()
                except Exception as cleanup:print('PSV7_APP_CLEANUP_INCOMPLETE',repr(cleanup),flush=True)
        self.worker=threading.Thread(target=run,name='psv7-preview',daemon=True);self.worker.start()
        print('PSV7_APP_LIVE_PREVIEW_RUNNING; keep this kernel open',flush=True)

    def current_camera_timing(self,request=None):
        with self.requests.lock:
            request=request or self.requests.status()
            timing=self.camera_timing
            if (timing is None or request.get('mode')!='CAMERA' or request.get('state')!='RESULT' or
                    request.get('source')!='CAMERA' or not request.get('valid') or request.get('active') or
                    any(timing[key]!=request.get(key) for key in
                        ('mode_epoch','request_epoch','request_id','selection_seq','class_id'))):
                return None
            return dict(timing)

    def _publish_camera_timing(self,report,total_us):
        # Caller holds requests.lock across result publication and timing.
        request=self.requests.status()
        if not report.get('published') or request['source']!='CAMERA' or not request['valid']:
            return
        cnn=report['cnn']
        self.camera_timing=dict(
            inference_wall_ms=cnn['inference_wall_ms'],fc_wait_ms=cnn['fc']['hardware_wait_ms'],
            total_us=int(total_us),clock='PERF_COUNTER_WALL_CLOCK',
            input_source='SAVED_CAMERA_FRAME_REGRESSION' if report.get('source_slot')==-1 else 'LIVE_CAMERA',
            algorithm_wall_ms=report['algorithm_wall_ms'],
            scope='Inference includes input MMIO, one complete RTL CNN START and 22 logits; excludes acquisition, PREP, files, ACK and display. Total matches HDMI Time through result preparation; diagnostic files are saved after result display.',
            **{key:request[key] for key in ('mode_epoch','request_epoch','request_id','selection_seq','class_id')})
        report['camera_timing']=dict(self.camera_timing)

    def recognize(self,classify=True,expected_epoch=None,diagnostics=False):
        with self.lock:
            self._check()
            token=self.requests.begin('CAMERA',expected_epoch=expected_epoch)
            with self.requests.lock:self.camera_timing=None
            self._sync_request()
            self.capture_sequence+=1
            output=self.report_folder/('capture_%04d'%self.capture_sequence);output.mkdir()
            report={'capture_sequence':self.capture_sequence,'classify':bool(classify),'passed':False}
            tx=np.zeros(13,np.uint32);tx[0]=5;tx[1]=int(classify);tx[12]=self.capture_sequence
            raw=np.zeros(27,np.uint32);image=np.zeros((64,64),np.uint8)
            captured_frame=None;diagnostic_arrays=None;algorithm_started=None
            started=time.perf_counter()
            try:
                self.page.lib.psv7_begin(self.page.handle)
                index=self.display.back();self._render(index);self.display.present(index);self.page.presented()
                report['initial_UI_wall_ms']=(time.perf_counter()-started)*1000
                self.last_frame,source_slot=self.capture.acquire(handoff_policy=self.camera_handoff_policy);report['source_slot']=source_slot
                captured_frame=self.last_frame
                report['capture_timings_ms']=dict(self.capture.last_timing)
                algorithm_started=time.perf_counter()
                filtered,report['pl']=self.prep.run(self.last_frame)
                image,raw,report['prep']=self.page.postprocess(filtered)
                tx[2]=1;tx[0]=1 if report['prep']['code']==0 else 2
                if report['prep']['code']==0 and classify:
                    result=self._infer(image,output,diagnostics=True) if diagnostics else self._infer(image,output)
                    diagnostic_arrays=result.pop('_diagnostic_arrays')
                    report['cnn']=result;hw=result['hardware']
                    tx[0]=4;tx[3]=result['predicted'];tx[4]=hw['sequence'];tx[5]=hw['cycles']
                    tx[6]=hw['input_count'];tx[7]=hw['output_count'];tx[8]=hw['error'];tx[10]=result['fc_us']
                report['passed']=True
                report['outcome']='RESULT' if tx[0]==4 else 'INPUT_READY' if tx[0]==1 else 'PREPROCESS_REJECTED'
            except Exception as error:
                report['error']=repr(error);tx[0]=3 if tx[2] else 5;tx[11]=0xFFFFFFFF
                raise
            finally:
                if algorithm_started is not None:
                    report['algorithm_wall_ms']=(time.perf_counter()-algorithm_started)*1000
                    report['algorithm_wall_scope']='PREP call, native postprocess, CNN transfers/compute, PL FC and CNN ACK; excludes camera acquisition, UI, files and request setup'
                tx[9]=min(0xFFFFFFFF,int((time.perf_counter()-started)*1e6))
                report['result_preparation_us']=int(tx[9])
                display_started=time.perf_counter()
                with self.requests.lock:
                    current=self.requests.current(token)
                    if current:
                        self.page.lib.psv7_publish(self.page.handle,image.ctypes.data,raw.ctypes.data,tx.ctypes.data)
                        if report.get('outcome')=='RESULT':
                            report['published']=self.requests.publish(token,report['cnn']['predicted'])
                            if not report['published']:report['outcome']='CANCELLED_OR_STALE'
                            else:self._publish_camera_timing(report,tx[9])
                        else:
                            self.requests.reject(token,report.get('prep',{}).get('code_name','CAMERA_NO_RESULT'),error='error' in report)
                    else:
                        report['published']=False;report['outcome']='CANCELLED_OR_STALE'
                if self.running:
                    try:
                        index=self.display.back();self._render(index);self.display.present(index);self.page.presented()
                    except Exception as error:
                        report['passed']=False;report['display_error']=repr(error)
                report['result_display_wall_ms']=(time.perf_counter()-display_started)*1000
                report['result_present_ack_wall_ms']=(time.perf_counter()-started)*1000
                report['result_present_ack_scope']='Request processing start through result MM2S park acknowledgement; includes initial UI, acquisition and algorithm; excludes diagnostic files, application-lock/host queue wait, browser polling and physical display scanout'
                diagnostics_started=time.perf_counter()
                try:
                    if captured_frame is not None:
                        np.save(output/'frame_bgr.npy',captured_frame)
                    if tx[2]:np.save(output/'input64.npy',image)
                    if diagnostic_arrays is not None:
                        np.savez_compressed(output/'cnn_actual.npz',**diagnostic_arrays)
                    report['diagnostics_passed']=True
                except Exception as error:
                    report['diagnostics_passed']=False;report['diagnostics_error']=repr(error)
                    report['passed']=False
                report['diagnostic_save_wall_ms']=(time.perf_counter()-diagnostics_started)*1000
                report['request_wall_ms']=(time.perf_counter()-started)*1000
                report['request_wall_scope']='Includes initial UI, acquisition, algorithm, result display and post-display diagnostic files; excludes final JSON serialization/logging'
                self.last_result=report
                (output/'app_capture_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
                print('PSV7_APP_CAPTURE_RESULT',report,flush=True)
                print('REPORT_DIRECTORY',str(output),flush=True)
                if 'display_error' in report:raise RuntimeError('Result display failed: '+report['display_error'])
            return report

    def _infer(self,image,output,transfer=None,diagnostics=False):
        result=self.unified.infer(image,transfer or self.cnn_io,diagnostics=diagnostics)
        result['class_zh']=str(self.labels[result['predicted']])
        return result

    def preprocess(self):return self.recognize(classify=False)

    def set_camera_handoff_policy(self,policy):
        from ..drivers.camera_handoff import POLICIES
        if policy not in POLICIES:raise ValueError('Unknown camera handoff policy')
        with self.lock,self.requests.lock:
            self._check()
            request=self.requests.status()
            if request['mode']!='CAMERA' or request['active']:
                raise RuntimeError('Change handoff only while CAMERA is inactive')
            self.camera_handoff_policy=policy
        return policy

    def set_camera_snapshot_policy(self,policy):
        if policy not in ('HEAP_MEMCPY_CHECK','HEAP_FUSED_CHECK'):
            raise ValueError('Formal snapshots must remain independent ordinary arrays')
        with self.lock,self.requests.lock:
            self._check();state=self.requests.status()
            if state['mode']!='CAMERA' or state['active']:
                raise RuntimeError('Change snapshot policy only in inactive CAMERA mode')
            self.capture.snapshot_policy=policy
            print('PSV7_CAMERA_SNAPSHOT_POLICY_SELECTED',policy,flush=True)
            return policy

    def clear(self,expected_epoch=None):
        if expected_epoch is None:
            expected_epoch=self.cancel()['mode_epoch']
        with self.lock:
            if self.requests.status()['mode_epoch'] != expected_epoch:
                return {'applied':False,'reason':'CANCELLED_OR_STALE'}
            self._check();self.unified.recover()
            self.page.lib.psv7_clear(self.page.handle);self.last_result=None
            index=self.display.back();self._render(index);self.display.present(index);self.page.presented()

    def pause_3d(self):
        with self.lock:
            self._check()
            if self.page.lib.psv7_model_pause(self.page.handle):raise RuntimeError('3D pause failed')
            back=self.display.back();self._render(back);self.display.present(back);self.page.presented()
            return self.page.model_info()

    def reset_3d(self):
        with self.lock:
            self._check()
            if self.page.lib.psv7_model_reset(self.page.handle):raise RuntimeError('3D reset failed')
            back=self.display.back();self._render(back);self.display.present(back);self.page.presented()
            return self.page.model_info()

    def select(self,index,expected_epoch=None):
        with self.lock:
            self._check()
            # Validate identity and publish the manual source atomically before
            # touching the page; a queued selection must not replace new work.
            self.requests.reference(index,expected_epoch=expected_epoch)
            if self.page.lib.psv7_select(self.page.handle,index):raise ValueError('Class must be 0..21')
            back=self.display.back();self._render(back);self.display.present(back);self.page.presented()
            print('PSV7_MANUAL_TEST_SELECTION; this is not recognition',index,flush=True)

    def status(self):
        with self.lock:
            return {'running':self.running,'preview_thread_alive':bool(self.worker and self.worker.is_alive()),
                    'preview_frames':self.frames_presented,'preview_fps':self.fps10/10.0,
                    'mm2s_status':hex(int(self.vdma.read(4))),'s2mm_status':hex(int(self.vdma.read(0x34))),
                    'park':hex(int(self.vdma.read(0x28))),'bridge_status':hex(int(self.bridge.read(8))),
                    'retained_buffers':len(self.frames),'dma_owned':self.dma_owned,'worker_error':self.worker_error,
                    'memory':self.memory.status(),
                    'request':self.requests.status() if self.requests else None,
                    'voice_timing':self.current_voice_timing() if self.requests else None,
                    'camera_timing':self.current_camera_timing() if self.requests else None,
                    'camera_snapshot_policy':self.capture.snapshot_policy,
                    'preview_handoff_policy':self.preview_handoff_policy,
                    'camera_handoff_policy':self.camera_handoff_policy,
                    'voice_worker_alive':bool(self.voice_worker and self.voice_worker.is_alive()),
                    'model3d':self.page.model_info() if self.page else None,
                    'missing_glyphs':int(self.page.lib.psv7_missing_glyphs()) if self.page else None}

    def stop(self):
        if self.requests is not None:self.requests.cancel()
        self.join_voice()
        if self.audio is not None:self.audio.stop()
        self.stop_event.set()
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(15)
            if self.worker.is_alive():raise RuntimeError('Preview thread still owns hardware; keep kernel open')
        with self.lock:
            self.bridge.write(0,0);errors=[]
            for name,action in (('cnn',self.unified.close),('camera',self.capture.close),('display',self.display.close),
                                ('prep',self.prep.close),('gpio',self.lines.close)):
                try:
                    result=action()
                    if result:errors.append(name+': '+repr(result))
                except Exception as error:errors.append(name+': '+repr(error))
            self.running=False
            if not self.frames and not self.dma_owned and not errors:
                try:self.memory.release_idle_remaining()
                except Exception as error:errors.append('memory: '+repr(error))
            if not self.frames and not errors:
                self.last_frame=None
                if self.requests is not None:self.requests.close()
                if self.page:self.page.close()
            from ..drivers.managed_memory import cma_snapshot,driver_memory_snapshot
            report={'errors':errors,'retained_buffers':len(self.frames),'dma_owned':self.dma_owned,'owned_gpio':list(self.lines.owned),
                    'preview_thread_alive':bool(self.worker and self.worker.is_alive()),
                    'voice_worker_alive':bool(self.voice_worker and self.voice_worker.is_alive()),
                    'request_controller_closed':self.requests is None or not self.requests.handle,
                    'memory':self.memory.status(),
                    'model3d':self.page.model_info() if self.page else None,'cma_before':self.cma_before,'cma_after':cma_snapshot(),
                    'driver_before':self.driver_before,'driver_after':driver_memory_snapshot(self.overlay.device)}
            (self.report_folder/'stop_report.json').write_text(json.dumps(report,indent=2))
            print('PSV7_APP_STOP',report,flush=True)
            if errors or self.frames or self.dma_owned or self.lines.owned or self.memory.active:raise RuntimeError('Cleanup incomplete; keep kernel open')
            return report


def MMIO_for_gpio():
    from pynq import MMIO
    return MMIO(0xE000A000,0x1000)
