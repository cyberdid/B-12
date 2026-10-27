"""Render README charts from local run artifacts (system matplotlib).

  /usr/bin/python3 scripts/make_readme_charts.py artifacts docs/images
Inputs: task14-eval-2026-10-27-merged/summary.json, task15-soak-2026-10-26/metrics.jsonl (first soak),
task15-soak-2026-10-26-run2/{metrics,events}.jsonl (8 h soak), task15-growth-2026-10-26.json.
Outputs PNGs referenced by README.md.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BLUE, ORANGE, GREEN, GREY = "#2f6fed", "#e8833a", "#1f8f4e", "#5d6676"
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})


def eval_chart(artifacts: Path, out: Path):
    summary = json.loads((artifacts / "task14-eval-2026-10-27-merged/summary.json").read_text())
    data = summary["by_ctx"]["4096"]["by_category"]
    names = ["tools", "memory", "adversarial", "behavior", "ua", "en", "conversation"]
    labels = {
        "tools": "tools\n(43)",
        "memory": "memory\n(14)",
        "adversarial": "adversarial\n(9)",
        "behavior": "behavior\n(7)",
        "ua": "ua\n(20)",
        "en": "en\n(15)",
        "conversation": "60-turn\n(1)",
    }
    rates = [data[n]["passed"] / data[n]["runs"] * 100 for n in names]
    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.bar([labels[n] for n in names], rates, color=BLUE)
    for bar, n in zip(bars, names, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1,
            f"{data[n]['passed']}/{data[n]['runs']}",
            ha="center",
            fontsize=9,
            color=GREY,
        )
    ax.set_ylim(0, 110)
    ax.set_ylabel("pass rate, %")
    ax.set_title(
        "Real Bolt E4B eval, ctx 4096, 109 cases × 5 repeats, merged code 60a4c0b"
    )
    fig.tight_layout()
    fig.savefig(out / "eval-by-category.png", dpi=130)


def soak_chart(artifacts: Path, out: Path):
    rows = [
        json.loads(line)
        for line in (artifacts / "task15-soak-2026-10-26/metrics.jsonl").read_text().splitlines()
    ]
    start = datetime.fromisoformat(rows[0]["at"])
    fig, ax = plt.subplots(figsize=(9, 4))
    pids = []
    for row in rows:
        if row["pid"] not in pids:
            pids.append(row["pid"])
    styles = {pids[0]: (ORANGE, "worker 1–2: full audit check per transaction")}
    for pid in pids[1:-1]:
        styles[pid] = (ORANGE, None)
    styles[pids[-1]] = (GREEN, "after fix cd803eb: incremental audit check")
    for pid in pids:
        sel = [r for r in rows if r["pid"] == pid and r["p50_ms"]]
        minutes = [(datetime.fromisoformat(r["at"]) - start).total_seconds() / 60 for r in sel]
        color, label = styles[pid]
        ax.plot(minutes, [r["p50_ms"] / 1000 for r in sel], color=color, label=label, lw=2)
    ax.set_xlabel("soak minutes")
    ax.set_ylabel("turn latency P50, s")
    ax.set_title("Software soak found linear latency growth; fixed during the run")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out / "soak-latency.png", dpi=130)


def soak8_chart(artifacts: Path, out: Path):
    run = artifacts / "task15-soak-2026-10-26-run2"
    rows = [json.loads(x) for x in (run / "metrics.jsonl").read_text().splitlines() if x]
    events = [json.loads(x) for x in (run / "events.jsonl").read_text().splitlines() if x]
    when = lambda s: datetime.fromisoformat(s)  # noqa: E731
    start = when(events[0]["at"])
    gaps, paused_at = [], None
    for e in events:
        if e["event"] == "soak_paused":
            paused_at = when(e["at"])
        elif e["event"] == "soak_resumed" and paused_at:
            gaps.append((paused_at, when(e["at"])))
            paused_at = None

    def active_h(ts):
        t = when(ts)
        idle = sum((min(t, b) - a).total_seconds() for a, b in gaps if t > a)
        return ((t - start).total_seconds() - idle) / 3600

    rows = [r for r in rows if r["p50_ms"]]
    hours = [active_h(r["at"]) for r in rows]
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(9, 5.4), sharex=True)
    top.plot(hours, [r["p50_ms"] for r in rows], color=GREEN, lw=1.6, label="P50")
    top.plot(hours, [r["p95_ms"] for r in rows], color=ORANGE, lw=1.6, label="P95")
    top.set_ylabel("turn latency, ms")
    top.set_title("8 h software soak (active time; 3 pauses): latency stays flat")
    top.legend(frameon=False, ncol=2)
    bottom.plot(hours, [r["rss_kb"] / 1024 for r in rows], color=BLUE, lw=1.6)
    bottom.set_ylabel("worker RSS, MB")
    bottom.set_xlabel("active hours (counters restart with each worker)")
    fig.tight_layout()
    fig.savefig(out / "soak-8h.png", dpi=130)


def growth_chart(artifacts: Path, out: Path):
    results = json.loads((artifacts / "task15-growth-2026-10-26.json").read_text())["results"]
    sizes = [r["size"] for r in results]
    fig, ax = plt.subplots(figsize=(9, 4))
    for key, color, label in [
        ("is_live", GREEN, "is_live (after audit fix)"),
        ("search", BLUE, "search with UA inflections"),
        ("recent_20", ORANGE, "recent(20) before fix 25c0db6"),
        ("purge_one", GREY, "purge one record (FTS rebuild, by design)"),
    ]:
        ax.plot(
            sizes, [r[key]["p50_ms"] for r in results], marker="o", color=color, label=label, lw=2
        )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("canonical memories")
    ax.set_ylabel("P50, ms")
    ax.set_title("Memory growth benchmark 200 → 200k records")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "memory-growth.png", dpi=130)


if __name__ == "__main__":
    artifacts, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    eval_chart(artifacts, out)
    soak_chart(artifacts, out)
    soak8_chart(artifacts, out)
    growth_chart(artifacts, out)
