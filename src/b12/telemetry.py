"""Payload-free health and resource metrics for the owner status view."""

import statistics
import time
from pathlib import Path


def _rss_bytes() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]


def status(runtime) -> dict:
    agent, control = runtime.agent, runtime.control
    latencies = list(agent.metrics["latency_ms"])
    stores = {}
    for path in runtime.settings.state_dir.rglob("*.sqlite3"):
        if "snapshots" not in path.relative_to(runtime.settings.state_dir).parts:
            stores[str(path.relative_to(runtime.settings.state_dir))] = path.stat().st_size
    pending_purges = sum(
        len(runtime.memory.pending_purges(control.resolve_actor(actor_id)))
        for actor_id in control.actor_ids()
    )
    return {
        "uptime_s": round(time.time() - agent.started_at, 1),
        "active_turns": len(agent.active),
        "turns": agent.metrics["turns"],
        "turns_by_state": dict(agent.metrics["by_state"]),
        "latency_ms": {
            "count": len(latencies),
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "mean": statistics.fmean(latencies) if latencies else None,
        },
        "pending_purges": pending_purges,
        "pending_approvals": len(control.pending_approvals()),
        "snapshots": len(runtime.operations.inventory()),
        "deletion_ledger_entries": len(runtime.operations.deletions()),
        "rss_bytes": _rss_bytes(),
        "store_bytes": stores,
    }
