"""Canonical-memory growth benchmark: 200 / 2k / 20k / 200k records.

  python scripts/load_memory.py --out /abs/result.json [--sizes 200,2000,20000,200000]
Measures insert throughput and per-operation latency (P50/P95 over repeated calls)
for search (with inflection expansion), is_live, recent and a global-style purge of
one record (canonical cleanup incl. WAL checkpoint). Synthetic UA text only.
"""

import argparse
import json
import platform
import random
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from b12.contracts import Actor
from b12.memory import MemoryStore

WORDS = "кіт пес сервер шафка код кава ранок звіт логи робот мікрофон камера дім сад ліс".split()


def text(rng, index):
    return f"запис {index}: " + " ".join(rng.choice(WORDS) for _ in range(8))


def timed(function, repeats):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    return {
        "p50_ms": statistics.median(samples),
        "p95_ms": samples[int(len(samples) * 0.95) - 1] if len(samples) > 1 else samples[0],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--sizes", default="200,2000,20000,200000")
    args = parser.parse_args()
    rng = random.Random(7)
    actor = Actor(id="owner", consent=True)
    root = Path(tempfile.mkdtemp(prefix="b12-growth-"))
    store = MemoryStore(root / "memory.sqlite3")
    results, count = [], 0
    for size in [int(s) for s in args.sizes.split(",")]:
        started = time.perf_counter()
        while count < size:
            store.remember(text(rng, count), actor)
            count += 1
        inserted = time.perf_counter() - started
        queries = ["шафку", "кота логи", "мікрофоном", "сервер звіт ранок"]
        row = {
            "size": size,
            "insert_per_s_last_batch": round(
                (size - (results[-1]["size"] if results else 0)) / inserted, 1
            ),
            "search": timed(lambda: store.search(rng.choice(queries), actor, limit=8), 40),
            "is_live": timed(lambda: store.is_live(str(uuid4()), actor), 200),
            "recent_20": timed(lambda: store.recent(actor, limit=20), 40),
            "db_bytes": sum(p.stat().st_size for p in root.iterdir()),
        }
        victims = [store.remember(text(rng, -1), actor) for _ in range(5)]
        row["purge_one"] = timed(lambda: store.begin_purge(victims.pop().id, actor), 5)
        row["verify_full_ms"] = timed(store.verify_full, 1)["p50_ms"]
        results.append(row)
        print(json.dumps(row), flush=True)
    store.close()
    Path(args.out).write_text(
        json.dumps(
            {
                "at": datetime.now(UTC).isoformat(),
                "host": platform.node(),
                "python": platform.python_version(),
                "sqlite": __import__("sqlite3").sqlite_version,
                "storage": str(root),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
