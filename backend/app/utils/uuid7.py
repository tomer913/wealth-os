"""
UUID v7 — time-ordered UUID (RFC 9562).

Structure:
  bits 0–47:   48-bit millisecond timestamp
  bits 48–51:  version = 0b0111 (7)
  bits 52–63:  12-bit sequence counter (monotonic within same ms)
  bits 64–65:  variant = 0b10
  bits 66–127: 62 random bits

Thread-safe: uses a lock to guard the (last_ms, seq) state.
No external dependencies — pure Python 3.12.
"""
import os
import struct
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms: int = 0
_seq: int = 0


def uuid7() -> uuid.UUID:
    """Return a new UUID v7 (time-ordered, monotonic within same millisecond)."""
    global _last_ms, _seq

    now_ms = int(time.time() * 1000)

    with _lock:
        if now_ms > _last_ms:
            _last_ms = now_ms
            _seq = 0
        else:
            # Same or backward clock — keep last_ms, increment sequence
            _seq += 1
            if _seq > 0xFFF:
                # Sequence overflow — advance artificial millisecond
                _last_ms += 1
                _seq = 0

        ms = _last_ms
        seq = _seq

    rand_bytes = os.urandom(8)
    rand_a, rand_b = struct.unpack(">HQ", b"\x00\x00" + rand_bytes)[0], \
                     int.from_bytes(rand_bytes, "big")

    # Build 128-bit integer
    #  [48-bit ms][4-bit ver=7][12-bit seq][2-bit var=0b10][62-bit random]
    rand62 = int.from_bytes(rand_bytes, "big") & ((1 << 62) - 1)

    value = (
        (ms & 0xFFFFFFFFFFFF) << 80          # bits 127–80: timestamp
        | 0x7 << 76                           # bits 79–76: version
        | (seq & 0xFFF) << 64                 # bits 75–64: sequence
        | 0b10 << 62                          # bits 63–62: variant
        | rand62                              # bits 61–0:  random
    )

    return uuid.UUID(int=value)


def uuid7_from_datetime(dt) -> uuid.UUID:
    """
    Create a UUID v7 with a specific timestamp (useful for testing/replay).
    dt: datetime object or milliseconds int.
    """
    import datetime as dt_module

    if isinstance(dt, dt_module.datetime):
        ms = int(dt.timestamp() * 1000)
    else:
        ms = int(dt)

    rand_bytes = os.urandom(10)
    rand62 = int.from_bytes(rand_bytes[:8], "big") & ((1 << 62) - 1)
    seq = int.from_bytes(rand_bytes[8:10], "big") & 0xFFF

    value = (
        (ms & 0xFFFFFFFFFFFF) << 80
        | 0x7 << 76
        | seq << 64
        | 0b10 << 62
        | rand62
    )
    return uuid.UUID(int=value)


def ms_from_uuid7(u: uuid.UUID) -> int:
    """Extract millisecond timestamp from a UUID v7."""
    return u.int >> 80
