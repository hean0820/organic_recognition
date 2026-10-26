"""OV5640 ID diagnostics using Linux sysfs GPIO on the PSv7 EMIO pins.

Pinned diagnostic adapter for the existing Linux 5.4/PYNQ 2.7 image.
No /dev/mem or direct GPIO register accesses. Sysfs is a legacy kernel ABI;
this adapter deliberately uses the interface present on the validated image.
"""

from pathlib import Path
import time


class SysfsFiles:
    root = Path('/sys/class/gpio')

    def chips(self):
        return sorted(self.root.glob('gpiochip*'))

    def read(self, path):
        return Path(path).read_text().strip()

    def write(self, path, value):
        Path(path).write_text(str(value))

    def exists(self, path):
        return Path(path).exists()

    def device(self, chip):
        return str((Path(chip) / 'device').resolve())


def discover_gpio(files=None):
    files = files or SysfsFiles()
    matches = []
    for chip in files.chips():
        if files.read(chip / 'label') != 'zynq_gpio':
            continue
        if not files.device(chip).endswith('/e000a000.gpio'):
            continue
        base, count = int(files.read(chip / 'base')), int(files.read(chip / 'ngpio'))
        if count != 118:
            raise RuntimeError('Expected Zynq-7000 GPIO with 118 lines')
        matches.append({'chip': str(chip), 'base': base, 'ngpio': count,
                        'scl_gpio': base + 54, 'sda_gpio': base + 55})
    if len(matches) != 1:
        raise RuntimeError('Expected one PS GPIO controller at e000a000.gpio')
    return matches[0]


class LinuxSccbLines:
    def __init__(self, profile, files=None, sleep=time.sleep):
        self.profile = profile
        self.files = files or SysfsFiles()
        self.sleep = sleep
        self.scl = int(profile['scl_gpio'])
        self.sda = int(profile['sda_gpio'])
        if self.scl != int(profile['base']) + 54 or self.sda != int(profile['base']) + 55:
            raise ValueError('Only PSv7 EMIO 0/1 (PS GPIO 54/55) are supported')
        self.owned = []
        self.ready = False

    def path(self, pin, attribute=None):
        path = self.files.root / ('gpio' + str(pin))
        return path / attribute if attribute else path

    def runtime_status(self):
        return self.files.read(Path(self.profile['chip']) / 'device/power/runtime_status')

    def open(self, timeout_s=1.0):
        if self.owned:
            raise RuntimeError('This bus already owns GPIOs; close it before reopening')
        # Preflight both lines: do not adopt or unexport another user's GPIO.
        for pin in (self.scl, self.sda):
            if self.files.exists(self.path(pin)):
                raise RuntimeError('GPIO %d is already exported; report its owner' % pin)
        for pin in (self.scl, self.sda):
            self.files.write(self.files.root / 'export', pin)
            self.owned.append(pin)  # ownership exists even if node creation is delayed
            deadline = time.monotonic() + timeout_s
            while not self.files.exists(self.path(pin, 'direction')):
                if time.monotonic() >= deadline:
                    raise TimeoutError('GPIO %d export node did not appear' % pin)
                self.sleep(0.005)
        deadline = time.monotonic() + timeout_s
        while self.runtime_status() != 'active':
            if time.monotonic() >= deadline:
                raise RuntimeError('GPIO controller did not become active after requests')
            self.sleep(0.005)
        # Output-high initialization avoids the low glitch of direction="out".
        self.files.write(self.path(self.sda, 'active_low'), 0)
        self.files.write(self.path(self.scl, 'active_low'), 0)
        self.files.write(self.path(self.sda, 'direction'), 'in')
        self.files.write(self.path(self.scl, 'direction'), 'high')
        self.ready = True

    def _require_ready(self):
        if not self.ready or len(self.owned) != 2:
            raise RuntimeError('SCCB GPIOs have not been requested and initialized')

    def set_scl(self, level):
        self._require_ready()
        self.files.write(self.path(self.scl, 'value'), 1 if level else 0)

    def set_sda(self, level):
        self._require_ready()
        # Open drain SDA: high means release, low means drive low.
        self.files.write(self.path(self.sda, 'direction'), 'in' if level else 'low')

    def read_sda(self):
        self._require_ready()
        return int(self.files.read(self.path(self.sda, 'value')))

    def idle_levels(self):
        self._require_ready()
        return {'scl': int(self.files.read(self.path(self.scl, 'value'))),
                'sda': self.read_sda()}

    def close(self):
        errors = []
        # Keep SCL high and release SDA before relinquishing our requests.
        # Do not touch GPIO direction/value if the controller was not awakened.
        active = False
        if self.owned:
            try:
                active = self.runtime_status() == 'active'
            except OSError as error:
                errors.append('runtime_status: %r' % error)
        if active:
            for pin, direction in ((self.scl, 'high'), (self.sda, 'in')):
                if pin in self.owned and self.files.exists(self.path(pin, 'direction')):
                    try:
                        self.files.write(self.path(pin, 'direction'), direction)
                    except OSError as error:
                        errors.append('GPIO %d idle: %r' % (pin, error))
        self.ready = False
        for pin in list(reversed(self.owned)):
            try:
                self.files.write(self.files.root / 'unexport', pin)
            except OSError as error:
                errors.append('GPIO %d unexport: %r' % (pin, error))
            else:
                self.owned.remove(pin)
        return errors


class SccbReader:
    def __init__(self, lines, half_period_s=0.000020, sleep=time.sleep):
        if half_period_s < 0.000004:
            raise ValueError('Diagnostic half-period must be at least 4 us')
        self.lines = lines
        self.half_period_s = half_period_s
        self.sleep = sleep
        self.ack_samples = []

    def delay(self):
        self.sleep(self.half_period_s)

    def start(self):
        self.lines.set_sda(1)
        self.lines.set_scl(1)
        self.delay()
        self.lines.set_sda(0)
        self.delay()
        self.lines.set_scl(0)
        self.delay()

    def stop(self):
        self.lines.set_scl(0)
        self.lines.set_sda(0)
        self.delay()
        self.lines.set_scl(1)
        self.delay()
        self.lines.set_sda(1)
        self.delay()

    def send_byte(self, value):
        if not 0 <= value <= 255:
            raise ValueError('SCCB byte out of range')
        for bit in range(7, -1, -1):
            self.lines.set_sda((value >> bit) & 1)
            self.delay()
            self.lines.set_scl(1)
            self.delay()
            self.lines.set_scl(0)
            self.delay()
        self.lines.set_sda(1)
        self.delay()
        self.lines.set_scl(1)
        self.delay()
        # Record the ninth bit. SCCB's don't-care phase is not a strict I2C ACK gate.
        sampled = self.lines.read_sda()
        self.ack_samples.append({'sent_byte': hex(value), 'ninth_bit': sampled})
        self.lines.set_scl(0)
        self.delay()

    def receive_byte(self):
        self.lines.set_sda(1)
        value = 0
        for _ in range(8):
            self.lines.set_scl(1)
            self.delay()
            value = (value << 1) | self.lines.read_sda()
            self.lines.set_scl(0)
            self.delay()
        # One-byte read: release SDA for the final master NACK/NA phase.
        self.lines.set_sda(1)
        self.delay()
        self.lines.set_scl(1)
        self.delay()
        self.lines.set_scl(0)
        self.delay()
        return value

    def read_register(self, address):
        if not 0 <= address <= 0xFFFF:
            raise ValueError('OV5640 register must fit uint16')
        try:
            self.start()
            self.send_byte(0x78)
            self.send_byte(address >> 8)
            self.send_byte(address & 255)
            self.stop()
            self.start()
            self.send_byte(0x79)
            return self.receive_byte()
        finally:
            self.stop()

    def read_sensor_id(self):
        high = self.read_register(0x300A)
        low = self.read_register(0x300B)
        return (high << 8) | low
