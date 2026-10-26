"""Freeze the previous parked S2MM slot; never treat an IRQ as frame completion.

PG020: IRQFrameCount counts when a transfer starts; WrFrmStore is the current
writer. First observe a fresh event while the old slot is still selected. Then
request the next slot, and require BOTH another fresh event and the new writer.
That moves the park request earlier without removing either event observation.
Caller must serialize all video writes and keep buffers owned on failure.
"""
import time

LEGACY = 'LEGACY_TWO_EVENTS_THEN_PARK'
OVERLAP = 'OVERLAP_SECOND_EVENT_WITH_PARK'
POLICIES = (LEGACY, OVERLAP)
ERROR_MASK = 0x8FF0


def check_frozen_source(video, source, target):
    control = int(video.read(0x30))
    status = int(video.read(0x34))
    park = int(video.read(0x28))
    if not control & 1 or control & (2 | 4 | 8 | 16) or status & (ERROR_MASK | 1):
        raise RuntimeError('S2MM is not running in stable parked mode')
    if ((park >> 24) & 31) != target or ((park >> 8) & 31) != target or source == target:
        raise RuntimeError('S2MM frozen source ownership changed')


def freeze_source(video, policy=LEGACY, timeout=3.0):
    if policy not in POLICIES:
        raise ValueError('Unknown camera handoff policy: ' + str(policy))
    if timeout <= 0:
        raise ValueError('Camera timeout must be positive')
    control = int(video.read(0x30))
    status = int(video.read(0x34))
    park = int(video.read(0x28))
    old = (park >> 24) & 31
    # No circular/genlock/reset/frame-count-stop, exactly one IRQ per frame.
    if (not control & 1 or control & (2 | 4 | 8 | 16) or
            ((control >> 16) & 255) != 1 or status & (ERROR_MASK | 1)):
        raise RuntimeError('Unsupported S2MM configuration for parked capture')
    if old >= 3 or ((park >> 8) & 31) != old:
        raise RuntimeError('Invalid or pending S2MM writer selection')
    target = (old + 1) % 3
    timing = {'handoff_policy': policy, 'source_slot': old, 'writer_target_slot': target,
              'fresh_events_required': 2}
    start = time.perf_counter()
    deadline = time.monotonic() + timeout

    def state(allowed, reference):
        cr = int(video.read(0x30))
        sr = int(video.read(0x34))
        ptr = int(video.read(0x28))
        writer = (ptr >> 24) & 31
        if cr != control or sr & (ERROR_MASK | 1):
            raise RuntimeError('S2MM stopped, changed configuration or reported an error')
        if writer not in allowed or ((ptr >> 8) & 31) != reference:
            raise RuntimeError('Unexpected S2MM writer/reference change')
        return sr, writer

    def poll(predicate, label):
        while not predicate():
            if time.monotonic() >= deadline:
                raise TimeoutError(label)
            time.sleep(0.001)

    def fresh_event():
        video.write(0x34, 0x1000)  # W1C stale event before observing a new one.
        poll(lambda: bool(state((old,), old)[0] & 0x1000), 'No fresh S2MM frame event')

    fresh_event()
    timing['first_fresh_event_ms'] = (time.perf_counter() - start) * 1000
    if policy == LEGACY:
        fresh_event()
        timing['two_frame_events_ms'] = (time.perf_counter() - start) * 1000
    else:
        # Clear event 1 BEFORE requesting the move, so event 2 can overlap it.
        video.write(0x34, 0x1000)
    switched = time.perf_counter()
    ptr = int(video.read(0x28))
    if ((ptr >> 24) & 31) != old or ((ptr >> 8) & 31) != old:
        raise RuntimeError('S2MM writer changed before park request')
    video.write(0x28, (ptr & ~0x1F00) | (target << 8))
    if policy == LEGACY:
        poll(lambda: state((old, target), target)[1] == target, 'S2MM parking not acknowledged')
        timing['writer_switch_ms'] = (time.perf_counter() - switched) * 1000
    else:
        def both():
            sr, writer = state((old, target), target)
            return bool(sr & 0x1000) and writer == target
        poll(both, 'No second fresh S2MM event with acknowledged park')
        timing['second_event_and_writer_switch_ms'] = (time.perf_counter() - switched) * 1000
    check_frozen_source(video, old, target)
    timing['freeze_wait_ms'] = (time.perf_counter() - start) * 1000
    return old, timing
