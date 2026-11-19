"""Freeze U5 application v3 after two independent blind local-model oracle reviews.

This copies the reviewed draft into a new immutable fixture tree, marks the copied
oracles reviewed, recalculates fixture hashes, validates the resulting manifest, and
refuses to overwrite an existing frozen version.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from evals.unified.validate_scenarios import validate  # noqa: E402


SOURCE_SET = ROOT / "evals/unified/scenario_sets/u5-application-v3.json"
OUTPUT_SET = ROOT / "evals/unified/scenario_sets/u5-application-locked-v1.json"
SOURCE_FIXTURES = "evals/unified/draft_fixtures/u5-application-v3"
LOCKED_FIXTURES = "evals/unified/draft_fixtures/u5-application-locked-v1"
REVIEWS = ROOT / "reports/unified/oracle-review-u5-v3/reviews"
REVIEWERS = {
    "gemma4-12b": ("Gemma 4 12B", "4eb23ef187e2"),
    "nemotron-bolt-e4b": ("Nemotron Bolt E4B", "7eaa0c0553b8"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verified_reviews(family_ids: list[str]) -> None:
    for reviewer, (display, _digest) in REVIEWERS.items():
        labels_path = REVIEWS / reviewer / "labels.json"
        if not labels_path.is_file():
            raise SystemExit(f"missing oracle review: {labels_path}")
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        reviews = labels.get("reviews", [])
        if [row.get("family_id") for row in reviews] != family_ids:
            raise SystemExit(f"{display}: family coverage/order mismatch")
        if any(row.get("verdict") != "ok" for row in reviews):
            raise SystemExit(f"{display}: non-ok verdicts require adjudication before freeze")


def main() -> None:
    if OUTPUT_SET.exists():
        raise SystemExit(f"refusing to overwrite frozen manifest: {OUTPUT_SET}")
    source = json.loads(SOURCE_SET.read_text(encoding="utf-8"))
    if source.get("set_id") != "u5-application-v3":
        raise SystemExit("source set id is not u5-application-v3")
    rows = source["scenarios"]
    family_ids = list(dict.fromkeys(row["family_id"] for row in rows))
    verified_reviews(family_ids)

    fixture_root = ROOT / LOCKED_FIXTURES
    if fixture_root.exists():
        raise SystemExit(f"refusing to overwrite frozen fixtures: {fixture_root}")
    fixture_root.mkdir(parents=True)

    reviewer_names = " and ".join(display for display, _ in REVIEWERS.values())
    review_status = (
        "REVIEWED 2026-11-19: two independent blind local-model reviews by "
        "Gemma 4 12B (4eb23ef187e2) and Nemotron Bolt E4B (7eaa0c0553b8); "
        "unanimous ok on 24 families."
    )
    frozen_rows = []
    for original in rows:
        row = dict(original)
        row["status"] = "FROZEN"
        row["notes"] = (
            "Synthetic; frozen 2026-11-19 after two independent blind reviews by "
            f"{reviewer_names}; see reports/unified/oracle-review-u5-v3/."
        )
        for key in ("input_fixture", "setup_fixture", "oracle_fixture"):
            if key not in row:
                continue
            old_relative = row[key]
            if not old_relative.startswith(SOURCE_FIXTURES + "/"):
                raise SystemExit(f"unexpected fixture path: {old_relative}")
            relative = old_relative.replace(SOURCE_FIXTURES, LOCKED_FIXTURES, 1)
            source_path = ROOT / old_relative
            target_path = ROOT / relative
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if key == "oracle_fixture":
                oracle = json.loads(source_path.read_text(encoding="utf-8"))
                oracle["review_status"] = review_status
                target_path.write_text(
                    json.dumps(oracle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            else:
                shutil.copyfile(source_path, target_path)
            row[key] = relative
            row[key + "_sha256"] = sha256(target_path)
        frozen_rows.append(row)

    frozen = {
        "schema_version": source["schema_version"],
        "set_id": "u5-application-locked-v1",
        "scenarios": frozen_rows,
    }
    OUTPUT_SET.write_text(
        json.dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    problems = validate(frozen, ROOT)
    if problems:
        OUTPUT_SET.unlink(missing_ok=True)
        raise SystemExit("frozen manifest validation failed:\n" + "\n".join(problems))
    print(f"frozen {len(frozen_rows)} scenarios / {len(family_ids)} families")
    print(f"manifest sha256 {sha256(OUTPUT_SET)}")


if __name__ == "__main__":
    main()
