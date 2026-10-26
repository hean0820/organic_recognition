"""PSv7 OV5640 configuration and one-frame S2MM capture.

Sensor writes follow the frozen bare-metal table. Linux owns GPIO outputs;
GPIO input MMIO is only used while both GPIO requests keep the device active.
The capture buffer stays owned until S2MM HALTED is confirmed.
"""
import time
from .psv7_sccb import SccbReader

WIDTH, HEIGHT, STRIDE = 1280, 720, 3840
VDMA_ERROR_MASK = 0x00008FF0


class KernelOwnedInputView:
    def __init__(self, lines, gpio_mmio):
        self.lines, self.gpio_mmio = lines, gpio_mmio

    def set_scl(self, level):
        self.lines.set_scl(level)

    def set_sda(self, level):
        self.lines.set_sda(level)

    def read_sda(self):
        self.lines._require_ready()
        if self.lines.runtime_status() != 'active':
            raise RuntimeError('GPIO must stay requested and active during input reads')
        return (int(self.gpio_mmio.read(0x68)) >> 1) & 1


class CameraSccb(SccbReader):
    def write_register(self, address, value):
        if not 0 <= address <= 0xFFFF or not 0 <= value <= 255:
            raise ValueError('Invalid sensor register/value')
        try:
            self.start()
            for byte in (0x78, address >> 8, address & 255, value):
                self.send_byte(byte)
        finally:
            self.stop()


def configure_sensor(reader, table, progress=None, sleep=time.sleep):
    if (table['width'], table['height'], table['total_h'], table['total_v']) != (1280, 720, 2570, 980):
        raise ValueError('Expected the frozen PSv7 720p configuration')
    if reader.read_sensor_id() != 0x5640:
        raise RuntimeError('OV5640 ID mismatch before configuration')
    writes = 0
    for event in table['events']:
        if event['op'] == 'delay':
            sleep(event['us'] / 1000000.0)
        elif event['op'] == 'write':
            reader.write_register(event['address'], event['value'])
            writes += 1
            if progress and (writes % 25 == 0 or writes == table['write_count']):
                progress(writes, table['write_count'])
        else:
            raise ValueError('Unknown sensor initialization operation')
    if writes != table['write_count']:
        raise RuntimeError('Incomplete sensor table')
    readbacks = {}
    for address_text, expected in table['readback_expected'].items():
        address = int(address_text, 16)
        actual = reader.read_register(address)
        readbacks[address_text] = actual
        if actual != expected:
            raise RuntimeError('Sensor readback mismatch at %s: got 0x%02x, expected 0x%02x'
                               % (address_text, actual, expected))
    id_after = reader.read_sensor_id()
    if id_after != 0x5640:
        raise RuntimeError('OV5640 ID mismatch after configuration')
    return {'write_count': writes, 'readbacks': readbacks, 'id_after': hex(id_after)}


def wait_until(predicate, label, timeout_s):
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() >= deadline:
            raise TimeoutError(label)
        time.sleep(0.001)


class Psv7Capture:
    def __init__(self, vdma):
        self.vdma = vdma
        self.frame = None
        self.running = False

    def snapshot(self):
        return {'s2mm_control': hex(int(self.vdma.read(0x30))),
                's2mm_status': hex(int(self.vdma.read(0x34))),
                'mm2s_control': hex(int(self.vdma.read(0x00))),
                'mm2s_status': hex(int(self.vdma.read(0x04))),
                'park': hex(int(self.vdma.read(0x28))),
                'frame_address': hex(int(self.frame.device_address)) if self.frame is not None else None}

    def arm(self, frame, timeout_s=2.0):
        if self.frame is not None:
            raise RuntimeError('Close the previous capture before arming again')
        if int(self.vdma.read(0x00)) & 1 or int(self.vdma.read(0x30)) & 1:
            raise RuntimeError('Stop both video channels before this single-frame test')
        if frame.shape != (HEIGHT, WIDTH, 3) or frame.dtype.name != 'uint8':
            raise ValueError('Expected 720x1280x3 uint8 frame')
        if not frame.flags.c_contiguous:
            raise ValueError('Capture frame must be contiguous')
        address = int(frame.device_address)
        if address % 8 or address < 0 or address + int(frame.nbytes) > 0x40000000:
            raise ValueError('Capture buffer alignment/HP0 DDR range is invalid')
        self.frame = frame
        self.vdma.write(0x30, 4)
        wait_until(lambda: not (int(self.vdma.read(0x30)) & 4), 'S2MM reset did not complete', timeout_s)
        self.vdma.write(0x34, 0xFFFF)  # W1C error/IRQ flags; reserved writes ignored
        self.vdma.write(0x3C, 0)       # unmask line/frame error diagnostics
        self.vdma.write(0x44, 0)       # frame address bank 0
        for offset in (0xAC, 0xB0, 0xB4):
            self.vdma.write(offset, address)
        self.vdma.write(0xA4, STRIDE)
        self.vdma.write(0xA8, STRIDE)
        self.vdma.write(0x28, int(self.vdma.read(0x28)) & ~0x1F00)
        frame.flush()
        # One complete frame then halt: RS=1, FrameCntEn=1, IRQFrameCount=1.
        self.vdma.write(0x30, 0x00011011)
        self.running = True
        self.vdma.write(0xA0, HEIGHT)   # VSIZE last commits the transfer

    def wait_frame(self, timeout_s=10.0):
        if self.frame is None:
            raise RuntimeError('No capture frame is armed')
        deadline = time.monotonic() + timeout_s
        while True:
            status = int(self.vdma.read(0x34))
            if status & VDMA_ERROR_MASK:
                raise RuntimeError('S2MM error: ' + str(self.snapshot()))
            if (status & 0x1000) and (status & 1) and not (int(self.vdma.read(0x30)) & 1):
                self.running = False
                self.frame.invalidate()
                return self.snapshot()
            if time.monotonic() >= deadline:
                raise TimeoutError('No completed and halted S2MM frame: ' + str(self.snapshot()))
            time.sleep(0.001)

    def stop(self, timeout_s=2.0):
        if self.frame is None:
            return
        self.vdma.write(0x30, int(self.vdma.read(0x30)) & ~1)
        try:
            wait_until(lambda: bool(int(self.vdma.read(0x34)) & 1), 'S2MM did not halt', timeout_s)
        except TimeoutError:
            self.vdma.write(0x30, 4)
            wait_until(lambda: not (int(self.vdma.read(0x30)) & 4),
                       'S2MM reset stuck; frame retained', timeout_s)
            wait_until(lambda: bool(int(self.vdma.read(0x34)) & 1),
                       'S2MM not halted after reset; frame retained', timeout_s)
        self.running = False

    def close(self, timeout_s=2.0):
        if self.frame is None:
            return
        self.stop(timeout_s)
        frame = self.frame
        frame.freebuffer()
        self.frame = None
