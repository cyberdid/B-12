"""The locked_test set follows the owner's gate decisions (18.11.2026)."""

import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "evals/unified/draft_sources"
SOURCE = SOURCES / "u2_u3_locked_cases_v2.json"
MANIFEST = ROOT / "evals/unified/scenario_sets/u2-u3-locked-v2.json"
V1_MANIFEST = ROOT / "evals/unified/scenario_sets/u2-u3-locked-v1.json"
DEV_SOURCE = SOURCES / "u2_u3_draft_cases_v4.json"
CASUAL_CLASSES = {"C01", "C02", "C03", "C04", "C05", "C13", "C14", "C15", "C16", "C17"}
UNRUNNABLE_CLASSES = {"C20", "C24", "C25", "C26", "C27", "C28", "C29", "C30", "M28", "M29"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def cases():
    return read(SOURCE)["cases"]


def test_manifest_is_valid_and_entirely_locked_test():
    spec = importlib.util.spec_from_file_location(
        "locked_validator", ROOT / "evals/unified/validate_scenarios.py"
    )
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    document = read(MANIFEST)
    assert validator.validate(document, ROOT) == []
    rows = document["scenarios"]
    assert len(rows) == 120
    assert {row["split"] for row in rows} == {"locked_test"}
    assert not [row for row in rows if row["notes"].startswith("BLOCKED:")]
    assert {row["status"] for row in rows} == {"FROZEN"}
    assert validator.validate(read(V1_MANIFEST), ROOT) == []


def test_counts_meet_the_protocol_minimums():
    tracks = Counter(case["track"] for case in cases())
    assert tracks == {"control": 30, "memory": 30}
    control = [case for case in cases() if case["track"] == "control"]
    casual = sum(case["oracle"]["catalog_class"] in CASUAL_CLASSES for case in control)
    assert casual >= 10 and len(control) - casual >= 20
    assert not {case["oracle"]["catalog_class"] for case in cases()} & UNRUNNABLE_CLASSES


def test_no_prompt_or_file_path_is_shared_with_the_dev_set():
    dev = read(DEV_SOURCE)["cases"]
    dev_prompts = {v["user_prompt"] for case in dev for v in case["variants"]}
    dev_paths = {p for case in dev for p in case["input"].get("synthetic_files", {})}
    for case in cases():
        assert not {v["user_prompt"] for v in case["variants"]} & dev_prompts
        assert not set(case["input"].get("synthetic_files", {})) & dev_paths


def test_family_ids_do_not_collide_with_dev():
    dev_ids = {case["family_id"] for case in read(DEV_SOURCE)["cases"]}
    assert not {case["family_id"] for case in cases()} & dev_ids


def test_paraphrase_family_has_no_shared_word_stems():
    def stems(text):
        return {w[:4] for w in re.findall(r"[а-яіїєґ']+", text.lower()) if len(w) >= 4}

    case = next(c for c in cases() if c["oracle"]["catalog_class"] == "M02")
    record = stems(case["input"]["synthetic_memory"][0]["content"])
    for variant in case["variants"]:
        assert not record & stems(variant["user_prompt"]), variant["variant_id"]


def test_authoring_script_reproduces_source(tmp_path):
    out = tmp_path / "cases.json"
    subprocess.run(
        [sys.executable, "-I", str(SOURCES / "author_u2_u3_locked_v2.py"), str(out)],
        check=True,
        capture_output=True,
    )
    assert out.read_bytes() == SOURCE.read_bytes()


def test_v2_changes_only_the_families_accepted_from_the_reviews():
    old = {c["family_id"]: c for c in read(SOURCES / "u2_u3_locked_cases_v1.json")["cases"]}
    changed = {c["family_id"] for c in cases() if c != old[c["family_id"]]}
    assert changed == {"C33", "C37", "C46", "C60", "M33", "M37", "M58", "M60"}


def test_frozen_oracles_record_the_review():
    for path in (ROOT / "evals/unified/draft_fixtures/u2-u3-locked-v2").rglob("*.oracle.json"):
        assert read(path)["review_status"].startswith("REVIEWED 2026-11-18")
