"""Long-horizon evidence driver (R17): run once per real day against the B-12 state.

  b12-state> python scripts/daily_check.py seed  --out evals/long_horizon   # day 0
  b12-state> python scripts/daily_check.py check --out evals/long_horizon   # day 1, 7, 30...
Seed stores synthetic anchors with known answers and forgets one of them. Each check
writes a dated record: anchor recall (canonical search), forgotten anchor absent from
search and from every state byte, integrity, pending purges, and snapshot verification.
Records are payload-free apart from the synthetic anchors. Elapsed days come from the
wall clock of the seed record; accelerated replays are never written here.
"""

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from b12.cli import load_settings
from b12.runtime import open_runtime

ANCHORS = [
    ("ДОВГОЯКІР-АЛЬФА", "Довготривалий якір: улюблена книга тестувальника — «Кобзар»."),
    ("ДОВГОЯКІР-БЕТА", "Довготривалий якір: тестова кімната сервера має номер 314."),
    ("ДОВГОЯКІР-ГАММА", "Довготривалий якір: тестовий кіт звертається на ім'я Бублик."),
]
FORGOTTEN = ("ДОВГОЯКІР-ЗАБУТИЙ", "Довготривалий якір, який буде забуто: код ЗЕЛЕНИЙЛИСТОПАД.")


def owner(runtime):
    actor_id = runtime.control.get_meta("owner_actor")
    if actor_id is None:
        raise SystemExit("run b12 init first")
    return runtime.control.resolve_actor(actor_id)


async def seed(runtime, out: Path):
    actor = owner(runtime)
    ids = {
        key: runtime.memory.remember(text, actor, source="long_horizon").id for key, text in ANCHORS
    }
    gone = runtime.memory.remember(FORGOTTEN[1], actor, source="long_horizon")
    receipt = await runtime.purge.forget(gone.id, actor.id)
    record = {
        "kind": "seed",
        "at": datetime.now(UTC).isoformat(),
        "anchors": ids,
        "forgotten": {"id": gone.id, "marker": "ЗЕЛЕНИЙЛИСТОПАД", "receipt": receipt.state},
    }
    (out / "seed.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
    return record


async def check(runtime, out: Path):
    actor = owner(runtime)
    seed_record = json.loads((out / "seed.json").read_text())
    seeded = datetime.fromisoformat(seed_record["at"])
    now = datetime.now(UTC)
    await runtime.purge.resume()
    recall = {}
    for key, text in ANCHORS:
        word = text.split("—")[-1].split()[-1].strip(".«»")
        hits = runtime.memory.search(word, actor)
        recall[key] = seed_record["anchors"][key] in {h.id for h in hits}
    marker = seed_record["forgotten"]["marker"].encode()
    own = out.resolve()  # the driver's own bookkeeping legitimately names the marker
    leaked = [
        str(p.relative_to(runtime.settings.state_dir))
        for p in runtime.settings.state_dir.rglob("*")
        if p.is_file() and own not in p.resolve().parents and marker in p.read_bytes()
    ]
    integrity = {}
    for path in runtime.settings.state_dir.rglob("*.sqlite3"):
        if "snapshots" in path.parts:
            continue
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            integrity[str(path.relative_to(runtime.settings.state_dir))] = connection.execute(
                "PRAGMA quick_check"
            ).fetchone()[0]
        finally:
            connection.close()
    snapshots = [runtime.operations.verify(s["id"])["ok"] for s in runtime.operations.inventory()]
    record = {
        "kind": "check",
        "at": now.isoformat(),
        "elapsed_days": round((now - seeded).total_seconds() / 86400, 3),
        "recall": recall,
        "forgotten_absent_from_search": runtime.memory.search("ЗЕЛЕНИЙЛИСТОПАД", actor) == [],
        "forgotten_bytes_found_in": leaked,
        "integrity_ok": all(v == "ok" for v in integrity.values()),
        "pending_purges": len(runtime.memory.pending_purges(actor)),
        "snapshots_ok": all(snapshots),
        "audit_events_verified": runtime.memory.verify_full(),
    }
    record["ok"] = (
        all(recall.values())
        and record["forgotten_absent_from_search"]
        and not leaked
        and record["integrity_ok"]
        and record["snapshots_ok"]
    )
    with (out / "checks.jsonl").open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def main():
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("seed", "check"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--config")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    runtime = open_runtime(load_settings(args.config))
    try:
        action = seed if args.mode == "seed" else check
        print(json.dumps(asyncio.run(action(runtime, out)), ensure_ascii=False, indent=2))
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
