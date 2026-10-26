"""PSv7 720p display bring-up; register recipe follows the bundled BSP drivers.

The retained frame must not be freed until the MM2S channel is confirmed halted.
This module does not initialize the camera or start S2MM.
"""
import time

WIDTH, HEIGHT, STRIDE = 1280, 720, 3840
VTC_SOURCE = 0x03FDEF00
VDMA_ERROR_MASK = 0x00000FF0


def wait_until(predicate, label, timeout_s=2.0):
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() >= deadline:
            raise TimeoutError(label)
        time.sleep(0.001)


def configure_vtc_720p(vtc):
    # XVtc_ConvTiming2Signal subtracts one from progressive VSync start/end.
    # Horizontal offsets are aligned to 1280 (blank) / 1390 (sync), per C driver.
    control = int(vtc.read(0x00))
    control &= ~(0xC0000000 | 0x04000000 | 0x03FDEF00 | 0x00080000 | 0x2D)
    vtc.write(0x00, control | 0x03)  # core enable + register update; generator off
    registers = {
        0x60: (720 << 16) | 1280,
        0x68: int(vtc.read(0x68)) & ~0x140,  # progressive, even chroma start
        0x6C: (int(vtc.read(0x6C)) & ~0x7F) | 0x7F,
        0x70: 1650,
        0x74: (750 << 16) | 750,
        0x78: (1430 << 16) | 1390,
        0x7C: (1280 << 16) | 1280,
        0x80: (729 << 16) | 724,
        0x84: (1390 << 16) | 1390,
        0x88: (1280 << 16) | 1280,
        0x8C: (729 << 16) | 724,
        0x90: (1390 << 16) | 1390,
        0x94: 720 << 16,
    }
    for offset, value in registers.items():
        vtc.write(offset, value)
    vtc.write(0x00, control | VTC_SOURCE | 0x03)


def paint_bars(frame):
    """Eight conventional bars using the native B,G,R byte order."""
    assert frame.shape == (HEIGHT, WIDTH, 3) and frame.dtype.name == 'uint8'
    colors_bgr = [(255,255,255), (0,255,255), (255,255,0), (0,255,0),
                  (255,0,255), (0,0,255), (255,0,0), (0,0,0)]
    for i, color in enumerate(colors_bgr):
        frame[:, i*160:(i+1)*160, :] = color
    # White edge and a central gray horizontal stripe aid crop/geometry checks.
    frame[:6, :, :] = 255
    frame[-6:, :, :] = 255
    frame[:, :6, :] = 255
    frame[:, -6:, :] = 255
    frame[352:368, 32:1248, :] = 100
    frame.flush()


class Psv7Display:
    def __init__(self, vdma, vtc):
        self.vdma = vdma
        self.vtc = vtc
        self.frame = None
        self.running = False

    def snapshot(self):
        return {
            'mm2s_control': hex(int(self.vdma.read(0x00))),
            'mm2s_status': hex(int(self.vdma.read(0x04))),
            's2mm_control': hex(int(self.vdma.read(0x30))),
            's2mm_status': hex(int(self.vdma.read(0x34))),
            'park': hex(int(self.vdma.read(0x28))),
            'vdma_version': hex(int(self.vdma.read(0x2C))),
            'vtc_control': hex(int(self.vtc.read(0x00))),
            'vtc_status': hex(int(self.vtc.read(0x04))),
            'vtc_active': hex(int(self.vtc.read(0x60))),
            'vtc_horizontal_total': int(self.vtc.read(0x70)),
            'vtc_vertical_total': hex(int(self.vtc.read(0x74))),
            'frame_address': hex(int(self.frame.device_address)) if self.frame is not None else None,
        }

    def start(self, frame, timeout_s=2.0):
        if self.frame is not None:
            raise RuntimeError('Stop and clean up the previous display first')
        if int(self.vdma.read(0x00)) & 1 or int(self.vdma.read(0x30)) & 1:
            raise RuntimeError('A VDMA channel is already running; do not replace its buffers')
        if frame.shape != (HEIGHT, WIDTH, 3) or frame.dtype.name != 'uint8':
            raise ValueError('Expected a contiguous 1280x720 BGR888 frame')
        if not frame.flags.c_contiguous or int(frame.device_address) % 8:
            raise ValueError('Frame must be contiguous and 8-byte aligned')
        address = int(frame.device_address)
        if address < 0 or address + int(frame.nbytes) > 0x40000000:
            raise ValueError('Frame falls outside the PSv7 HP0 DDR address window')
        self.frame = frame
        try:
            self.vdma.write(0x00, 4)
            wait_until(lambda: not (int(self.vdma.read(0x00)) & 4),
                       'VDMA MM2S reset did not finish', timeout_s)
            self.vdma.write(0x04, 0x7FF0)  # clear W1C errors/IRQ status
            configure_vtc_720p(self.vtc)
            self.vdma.write(0x14, 0)  # low frame-address bank
            for offset in (0x5C, 0x60, 0x64):
                self.vdma.write(offset, address)
            self.vdma.write(0x54, STRIDE)
            self.vdma.write(0x58, STRIDE)
            self.vdma.write(0x28, int(self.vdma.read(0x28)) & ~0x1F)
            self.frame.flush()
            # Park frame 0; frame-count IRQ every frame; no CPU interrupt handler.
            self.vdma.write(0x00, 0x00011001)
            self.vdma.write(0x50, HEIGHT)  # VSIZE last commits the transfer
            self.vtc.write(0x00, int(self.vtc.read(0x00)) | 0x07)
            self.running = True

            def frame_complete():
                status = int(self.vdma.read(0x04))
                if status & VDMA_ERROR_MASK:
                    raise RuntimeError('VDMA MM2S error: ' + str(self.snapshot()))
                return bool(status & 0x1000)

            wait_until(frame_complete, 'No VDMA frame completion: ' + str(self.snapshot()), timeout_s)
            self.vdma.write(0x04, 0x1000)
            return self.snapshot()
        except Exception:
            # Stop/reset must be confirmed before a failed startup can release memory.
            try:
                self.stop(timeout_s)
            except Exception as cleanup_error:
                print('CLEANUP INCOMPLETE; frame retained:', repr(cleanup_error))
            raise

    def stop(self, timeout_s=2.0):
        if self.frame is None:
            return
        self.vdma.write(0x00, int(self.vdma.read(0x00)) & ~1)
        try:
            wait_until(lambda: bool(int(self.vdma.read(0x04)) & 1),
                       'VDMA MM2S did not halt', timeout_s)
        except TimeoutError:
            self.vdma.write(0x00, 4)
            wait_until(lambda: not (int(self.vdma.read(0x00)) & 4),
                       'VDMA reset stuck; buffer retained', timeout_s)
            wait_until(lambda: bool(int(self.vdma.read(0x04)) & 1),
                       'VDMA not halted after reset; buffer retained', timeout_s)
        # Keep generator running until the reader has drained, then disable it.
        self.vtc.write(0x00, int(self.vtc.read(0x00)) & ~4)
        frame = self.frame
        self.frame = None
        self.running = False
        frame.freebuffer()

