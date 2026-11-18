import importlib.util
import json
import re
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "evals/unified/draft_sources"
SOURCE = SOURCES / "u2_u3_draft_cases_v3.json"
MANIFEST = ROOT / "evals/unified/scenario_sets/u2-u3-draft-v3.json"
FIXTURES = ROOT / "evals/unified/draft_fixtures/u2-u3-v3"
SUPERSEDED = [ROOT / f"evals/unified/scenario_sets/u2-u3-draft-v{n}.json" for n in (1, 2)]
BLOCKED = {"C24", "C25", "C26", "C30", "M28", "M29"}
REGISTERED_TOOLS = {
    "file_read",
    "file_list",
    "file_search",
    "file_write",
    "memory_search",
    "memory_store",
    "memory_forget",
    "memory_supersede",
    "note_add",
    "system_info",
    "run_command",
    "http_fetch",
    "web_search",
    "sudo_exec",
}


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def cases():
    return {case["family_id"]: case for case in read(SOURCE)["cases"]}


def test_committed_current_set_validates_and_has_expected_shape():
    validator = load_module(ROOT / "evals/unified/validate_scenarios.py", "corpus_validator")
    document = read(MANIFEST)
    assert validator.validate(document, ROOT) == []
    rows = document["scenarios"]
    families = Counter(row["family_id"] for row in rows)
    assert len(rows) == 120 and len(families) == 60 and set(families.values()) == {2}
    assert Counter(row["track"] for row in rows) == {"control": 60, "memory": 60}
    assert {row["split"] for row in rows} == {"dev"}
    assert {row["status"] for row in rows} == {"DRAFT"}
    assert {row["family_id"] for row in rows if row["notes"].startswith("BLOCKED:")} == BLOCKED


def test_superseded_sets_still_match_their_hashes():
    validator = load_module(ROOT / "evals/unified/validate_scenarios.py", "corpus_validator_old")
    for manifest in SUPERSEDED:
        assert validator.validate(read(manifest), ROOT) == [], manifest.name


def test_model_visible_inputs_hold_only_the_prompt():
    inputs = sorted(FIXTURES.rglob("*.input.json"))
    setups = sorted(FIXTURES.rglob("*.setup.json"))
    oracles = sorted(FIXTURES.rglob("*.oracle.json"))
    assert len(inputs) == len(setups) == len(oracles) == 120
    for path in inputs:
        assert set(read(path)) == {"schema_version", "family_id", "variant_id", "user_prompt"}
    for path in setups:
        document = read(path)
        assert document["visibility"] == "evaluator_only"
        assert b"accepted_outcomes" not in path.read_bytes()
    for path in oracles:
        assert read(path)["review_status"] == "UNREVIEWED"


def test_rebuilding_from_source_reproduces_committed_hashes(tmp_path):
    builder = load_module(ROOT / "evals/unified/build_scenario_drafts.py", "corpus_builder")
    catalog = read(SOURCE)
    rebuilt = builder.build_set(
        catalog["cases"],
        root=tmp_path,
        fixture_rel_dir="evals/unified/draft_fixtures/u2-u3-v3",
        manifest_rel_path="evals/unified/scenario_sets/u2-u3-draft-v3.json",
        set_id=catalog["set_id"],
    )
    assert rebuilt == read(MANIFEST)


def test_authoring_script_reproduces_source(tmp_path):
    out = tmp_path / "cases.json"
    module = SOURCES / "author_u2_u3_v3.py"
    import subprocess
    import sys

    subprocess.run([sys.executable, "-I", str(module), str(out)], check=True, capture_output=True)
    assert out.read_bytes() == SOURCE.read_bytes()


def test_tool_names_are_registered_runtime_tools():
    for family, case in cases().items():
        assert set(case["input"]["available_tools"]) <= REGISTERED_TOOLS, family
        for key in ("accepted_tools",):
            assert set(case["oracle"].get(key, [])) <= REGISTERED_TOOLS, family
        for call in case["oracle"].get("required_tool_calls", []):
            assert call["name"] in REGISTERED_TOOLS, family


def test_memory_and_goal_ids_are_uuids():
    for family, case in cases().items():
        for row in case["input"].get("synthetic_memory", []):
            uuid.UUID(row["memory_id"])
        for row in case["input"].get("synthetic_goals", []):
            uuid.UUID(row["goal_id"])
        for evidence in case["oracle"]["required_evidence_ids"]:
            if evidence.startswith(("mem:", "goal:")):
                uuid.UUID(evidence.split(":", 1)[1]), family
    forget = cases()["M27"]["oracle"]["required_tool_calls"][0]
    seeded = {row["alias"]: row["memory_id"] for row in cases()["M27"]["input"]["synthetic_memory"]}
    assert forget["memory_id"] == seeded["m27-r1"]


def test_paraphrase_family_has_no_shared_word_stems():
    def stems(text):
        return {w[:5] for w in re.findall(r"[а-яіїєґ']+", text.lower()) if len(w) >= 5}

    case = cases()["M02"]
    record = stems(case["input"]["synthetic_memory"][0]["content"])
    for variant in case["variants"]:
        assert not record & stems(variant["user_prompt"]), variant["variant_id"]


def test_background_events_use_one_ukrainian_wrapper():
    for family in ("C27", "C28", "C29"):
        case = cases()[family]
        assert case["input"]["event_id"]
        for variant in case["variants"]:
            assert variant["user_prompt"].startswith("[фонова подія] "), (family, variant)


def test_source_uses_only_synthetic_contact_domains():
    for token in SOURCE.read_text(encoding="utf-8").split():
        if "@" in token:
            assert ".invalid" in token, token


def test_v3_changes_exactly_the_families_accepted_from_the_gemini_review():
    old = {c["family_id"]: c for c in read(SOURCES / "u2_u3_draft_cases_v2.json")["cases"]}
    changed = {family for family, case in cases().items() if case != old[family]}
    assert changed == {"C05", "C07", "C11", "C12", "C16", "C21", "M09", "M12", "M18"}
