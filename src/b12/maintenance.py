"""Periodic housekeeping for the long-running server.

glibc keeps freed memory in per-thread arenas; a soak probe showed ~77 % of the RSS
growth over 2500 turns returned to the OS under malloc_trim while the Python object
count stayed flat, so the creep is allocator fragmentation, not a leak. The loop also
erases expired private approval digests even when nobody calls the control plane.
"""

import asyncio
import ctypes
import logging

log = logging.getLogger(__name__)


def trim_memory() -> int | None:
    """Ask glibc to return free heap to the OS; None when unsupported."""
    try:
        return int(ctypes.CDLL("libc.so.6").malloc_trim(0))
    except (OSError, AttributeError):
        return None


async def maintenance_loop(
    runtime, stop: asyncio.Event, *, interval_s: float = 300.0, trim=trim_memory
):
    while not stop.is_set():
        try:
            runtime.control.expire_approvals()
        except Exception:
            log.exception("approval expiry failed")
        try:
            trim()
        except Exception:
            log.exception("memory trim failed")
        try:
            await asyncio.wait_for(stop.wait(), interval_s)
        except TimeoutError:
            pass
