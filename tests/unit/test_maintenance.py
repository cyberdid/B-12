import asyncio
from types import SimpleNamespace


def test_trim_memory_never_raises_and_reports_an_int_or_none():
    from b12.maintenance import trim_memory

    result = trim_memory()
    assert result is None or (isinstance(result, int) and result >= 0)


def test_trim_memory_degrades_when_libc_is_unavailable(monkeypatch):
    import ctypes

    from b12 import maintenance

    def broken(*args, **kwargs):
        raise OSError("no libc")

    monkeypatch.setattr(ctypes, "CDLL", broken)
    assert maintenance.trim_memory() is None


async def test_loop_expires_approvals_and_trims_until_stopped():
    from b12.maintenance import maintenance_loop

    calls = {"expire": 0, "trim": 0}
    control = SimpleNamespace(
        expire_approvals=lambda: calls.__setitem__("expire", calls["expire"] + 1)
    )
    runtime = SimpleNamespace(control=control)
    stop = asyncio.Event()

    def trim():
        calls["trim"] += 1
        if calls["trim"] == 3:
            stop.set()

    await asyncio.wait_for(maintenance_loop(runtime, stop, interval_s=0.01, trim=trim), 5)
    assert calls["expire"] >= 3 and calls["trim"] == 3


async def test_a_failing_step_does_not_stop_the_loop():
    from b12.maintenance import maintenance_loop

    state = {"expire": 0}

    def expire():
        state["expire"] += 1
        raise RuntimeError("synthetic failure")

    stop = asyncio.Event()
    runtime = SimpleNamespace(control=SimpleNamespace(expire_approvals=expire))

    def trim():
        if state["expire"] >= 3:
            stop.set()

    await asyncio.wait_for(maintenance_loop(runtime, stop, interval_s=0.01, trim=trim), 5)
    assert state["expire"] >= 3
