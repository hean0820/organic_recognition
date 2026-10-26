"""Independent startup for the known PSv7 bridge hardware, PYNQ 2.7.
Rebind existing hardware without relying on a prior Notebook variable.
"""
import hashlib
import time
from pathlib import Path

LEGACY_PSV7_BIT_SHA256='a9c1bc55cd13c10746ba42ac218dc9a48e5049e0b3d4acfa6a94c34044daebce'
IP_ADDRESSES={'axi_vdma_0':0x43000000,'cnn_ps_if_0':0x43C00000,
              'prep_accel_0':0x43C20000,'v_tc_0':0x43C10000,'camera_bridge_ctrl':0x41200000,'audio_axi_0':0x43C30000}


def require_released_owners(runtime):
    for name in ('app','camera_capture','display','native_capture','live_capture','bridge_capture','prep_capture'):
        owner=runtime.get(name)
        if owner is None:continue
        worker=getattr(owner,'worker',None)
        if (getattr(owner,'frame',None) is not None or getattr(owner,'frames',[]) or
            getattr(owner,'dma_owned',False) or getattr(owner,'running',False) or
            bool(getattr(getattr(owner,'memory',None),'active',{})) or
            (worker is not None and worker.is_alive())):
            raise RuntimeError(name+' still owns resources; stop it before startup')
    for name in ('camera_lines','probe_lines','standby_lines','snapshot_lines',
                 'boundary_lines','native_lines','bridge_lines'):
        owner=runtime.get(name)
        if owner is not None and getattr(owner,'owned',[]):raise RuntimeError(name+' still owns GPIOs')


def check_idle_hardware(ip_dict,mmio):
    for name in IP_ADDRESSES:
        if name not in ip_dict or ip_dict[name]['phys_addr']!=IP_ADDRESSES[name]:
            raise RuntimeError('Current hardware metadata is not the known PSv7 layout: '+name)
    video=mmio(0x43000000,ip_dict['axi_vdma_0']['addr_range'])
    for control,status in ((0,4),(0x30,0x34)):
        print('PSV7_BOOT_STAGE READ_VDMA',hex(control),hex(status),flush=True)
        control_value=int(video.read(control));status_value=int(video.read(status))
        print('PSV7_BOOT_VDMA_VALUE',hex(control_value),hex(status_value),flush=True)
        if control_value&1 or not status_value&1:
            raise RuntimeError('VDMA is active or not HALTED; keep the kernel open and stop its owner')
    prep=mmio(0x43C20000,ip_dict['prep_accel_0']['addr_range'])
    print('PSV7_BOOT_STAGE READ_PREP',flush=True)
    control=int(prep.read(0))
    print('PSV7_BOOT_PREP_VALUE',hex(control),flush=True)
    if not control&4 or control&0x81:
        raise RuntimeError('PREP AXI master is active; keep its buffers and stop before Overlay/clock changes')
    audio=mmio(0x43C30000,ip_dict['audio_axi_0']['addr_range'])
    if int(audio.read(0))!=0x41554432 or int(audio.read(28))!=0x10000:
        raise RuntimeError('Audio ID/version does not match the paired camera/audio design')
    if int(audio.read(4))&1:
        raise RuntimeError('Audio producer enabled; stop its owner before clock/Overlay changes')
    print('PSV7_BOOT_AUDIO_IDLE',flush=True)
    cnn=mmio(0x43C00000,ip_dict['cnn_ps_if_0']['addr_range'])
    print('PSV7_BOOT_STAGE READ_CNN',flush=True)
    cnn_id=int(cnn.read(0));cnn_status=int(cnn.read(8))
    print('PSV7_BOOT_CNN_VALUE',hex(cnn_id),cnn_status,flush=True)
    from ..drivers.cnn_control import CnnControl
    owner=CnnControl(cnn).owner
    owner.verify_identity()
    if not owner.release_guard() or cnn_status & (4|8|16):
        raise RuntimeError('CNN is not the expected IDLE core')


def ensure_overlay(runtime,folder,expected_hashes,mode=None,ref_clk_mhz=33.333333,fclk_mhz=100.0,
                   verified_previous_bit_sha256=()):
    from pynq import Overlay,MMIO
    from pynq.ps import _ClocksZynq
    folder=Path(folder).resolve()
    # Verify files before constructing or mutating any hardware object.
    for name,expected in expected_hashes.items():
        file=folder/name
        if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:raise RuntimeError(name+' hash mismatch')
    require_released_owners(runtime)
    print('PSV7_BOOT_STAGE CREATE_METADATA_ONLY',flush=True)
    overlay=Overlay(str(folder/'psv7.bit'),download=False)
    for name,address in IP_ADDRESSES.items():
        if name not in overlay.ip_dict or overlay.ip_dict[name]['phys_addr']!=address:
            raise RuntimeError('Paired bridge HWH address mismatch: '+name)
    reused=overlay.is_loaded()
    previous_name=getattr(overlay.device,'bitfile_name',None)
    if mode=='cold_start':
        # Only after a confirmed clean board boot: establish a verified PL
        # before touching any AXI IP. Kernel restart is not a clean board boot.
        print('PSV7_BOOT_STAGE DOWNLOAD_VERIFIED_COLD_START',flush=True)
        overlay.download();reused=False
        if not overlay.is_loaded():raise RuntimeError('Bridge Overlay download not confirmed')
        print('PSV7_BOOT_STAGE DOWNLOAD_COMPLETE',flush=True)
    elif reused:
        check_idle_hardware(overlay.ip_dict,MMIO)
    else:
        previous_ips=getattr(overlay.device,'ip_dict',{})
        if previous_name:
            previous=Path(previous_name)
            if not previous.is_file():raise RuntimeError('Cannot identify the currently registered bitstream: '+str(previous))
            digest=hashlib.sha256(previous.read_bytes()).hexdigest()
            if digest not in (expected_hashes['psv7.bit'],)+tuple(verified_previous_bit_sha256):
                raise RuntimeError('Another Overlay is registered; inspect and stop its hardware before replacement')
            check_idle_hardware(previous_ips,MMIO)
        elif previous_ips:
            raise RuntimeError('PYNQ has IP metadata without a bitstream identity; inspect the current hardware before loading')
        else:
            raise RuntimeError('PL identity was lost after the kernel restart. Do not probe AXI using guessed metadata. Stop other hardware sessions and perform a clean board reboot; only then start with mode="cold_start", clean_boot=True')
        print('PSV7_BOOT_STAGE DOWNLOAD_VERIFIED_AFTER_IDLE_CHECK',flush=True)
        overlay.download()
        if not overlay.is_loaded():raise RuntimeError('Bridge Overlay download not confirmed')
        print('PSV7_BOOT_STAGE DOWNLOAD_COMPLETE',flush=True)
    print('PSV7_BOOT_STAGE SET_CLOCK_100MHZ',flush=True)
    clock=_ClocksZynq(ref_clk_mhz=ref_clk_mhz)
    clock.set_pl_clk(0,clk_mhz=fclk_mhz);clock.set_pl_clk(1,clk_mhz=fclk_mhz)
    print('PSV7_BOOT_STAGE HOLD_BRIDGE',flush=True)
    bridge=MMIO(0x41200000,overlay.ip_dict['camera_bridge_ctrl']['addr_range'])
    bridge.write(4,0);bridge.write(0,0)
    deadline=time.monotonic()+2.0
    while (int(bridge.read(8))&63)!=1:
        if time.monotonic()>=deadline:raise TimeoutError('Bridge did not confirm locked/reset-held state')
        time.sleep(0.001)
    print('PSV7_BOOT_STAGE BRIDGE_HELD_AND_LOCKED',flush=True)
    check_idle_hardware(overlay.ip_dict,MMIO)
    clocks={str(i):clock.get_pl_clk(i) for i in (0,1)}
    if any(abs(value-fclk_mhz)>0.2 for value in clocks.values()):raise RuntimeError('FCLK setup failed: '+repr(clocks))
    print('PSV7_APP_OVERLAY_READY',{'reused':bool(reused),'bitfile':overlay.bitfile_name,'fclk_mhz':clocks},flush=True)
    return overlay
