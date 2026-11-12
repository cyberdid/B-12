"""Empirical Stress Tests & Fuzzing Harness for Milestone M3 Gate.

Validates:
1. Suite discovery stress, 11-group partitioning, and scenario counts (92 total).
2. Cross-scenario ID uniqueness, strict regex adherence, and group-prefix alignment.
3. In-memory schema mutation, type fuzzing, and boundary condition enforcement.
4. Batch suite runner orchestration, JUnit XML generation, and JSON summaries.
"""

from __future__ import annotations

import json
import random
import re
import string
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from evals.capri_comprehensive.evaluators.schema import (
    ExecutionMode,
    ExecutionReport,
    ExecutionStatus,
    ScenarioDefinition,
    ScenarioSeverity,
    ScientificTaxonomy,
)
from evals.capri_comprehensive.runners.suite_runner import SuiteRunner

# ---------------------------------------------------------------------------
# Fixtures and Expected Constants
# ---------------------------------------------------------------------------

EXPECTED_GROUP_COUNTS = {
    "group_a_memory": 10,
    "group_b_continuity": 8,
    "group_c_cross_model": 10,
    "group_d_reasoning": 8,
    "group_e_security": 12,
    "group_f_autonomy": 9,
    "group_g_interaction": 8,
    "group_h_voice": 8,
    "group_i_reliability": 8,
    "group_j_robotics": 6,
    "group_k_journeys": 5,
}

EXPECTED_GROUP_PREFIXES = {
    "group_a_memory": "MEM",
    "group_b_continuity": "LT",
    "group_c_cross_model": "CM",
    "group_d_reasoning": "RE",
    "group_e_security": "SEC",
    "group_f_autonomy": "AUT",
    "group_g_interaction": "INT",
    "group_h_voice": "VOI",
    "group_i_reliability": "REL",
    "group_j_robotics": "ROB",
    "group_k_journeys": "JOURNEY",
}

ID_STRICT_REGEX = re.compile(r"^([A-Z]{2,4}-[0-9]{2}|JOURNEY-[0-9]{2})$")


@pytest.fixture(scope="session")
def suite_runner(tmp_path_factory: pytest.TempPathFactory) -> SuiteRunner:
    # Тести не пишуть у реальні artifacts/ та reports/ — лише у тимчасові каталоги.
    base = tmp_path_factory.mktemp("suite_runner")
    return SuiteRunner(artifacts_dir=base / "artifacts", reports_dir=base / "reports")


@pytest.fixture(scope="session")
def all_scenarios(suite_runner: SuiteRunner) -> list[ScenarioDefinition]:
    paths = suite_runner.discover_scenarios()
    return [ScenarioDefinition.from_yaml_file(p) for p in paths]


# ---------------------------------------------------------------------------
# 1. Suite Discovery Stress & Partitioning Tests
# ---------------------------------------------------------------------------


class TestSuiteDiscoveryStress:
    """Stress tests for scenario discovery across all 11 groups."""

    def test_total_scenario_count_is_strictly_92(self, suite_runner: SuiteRunner):
        discovered = suite_runner.discover_scenarios()
        assert len(discovered) == 92, f"Expected exactly 92 scenarios, got {len(discovered)}"

    def test_all_11_groups_partitioned_with_exact_counts(self, suite_runner: SuiteRunner):
        discovered = suite_runner.discover_scenarios()
        group_counts: dict[str, int] = {}
        for p in discovered:
            grp_name = p.parent.name
            group_counts[grp_name] = group_counts.get(grp_name, 0) + 1

        assert set(group_counts.keys()) == set(EXPECTED_GROUP_COUNTS.keys()), (
            f"Group partition mismatch. Found: {set(group_counts.keys())}"
        )
        for grp, expected_count in EXPECTED_GROUP_COUNTS.items():
            assert group_counts[grp] == expected_count, (
                f"Group {grp} expected {expected_count} scenarios, got {group_counts[grp]}"
            )

    def test_discover_scenarios_group_filter_single_group(self, suite_runner: SuiteRunner):
        for grp, expected_count in EXPECTED_GROUP_COUNTS.items():
            filtered = suite_runner.discover_scenarios(group_filter=[grp])
            assert len(filtered) == expected_count, (
                f"Filter for {grp} returned {len(filtered)} items, expected {expected_count}"
            )
            for p in filtered:
                assert p.parent.name == grp

    def test_discover_scenarios_group_filter_multiple_groups(self, suite_runner: SuiteRunner):
        selected = ["group_a_memory", "group_e_security", "group_k_journeys"]
        expected_total = 10 + 12 + 5  # 27
        filtered = suite_runner.discover_scenarios(group_filter=selected)
        assert len(filtered) == expected_total

    def test_discover_scenarios_taxonomy_filter(self, suite_runner: SuiteRunner):
        counts = {
            ScientificTaxonomy.DETERMINISTIC_SOFTWARE.value: 28,
            ScientificTaxonomy.REAL_MODEL_BEHAVIORAL.value: 39,
            ScientificTaxonomy.CONTROLLED_EXPERIMENTAL.value: 13,
            ScientificTaxonomy.PHYSICAL_ACCEPTANCE.value: 12,
        }
        total = 0
        for tax_val, expected in counts.items():
            matched = suite_runner.discover_scenarios(taxonomy_filter=[tax_val])
            assert len(matched) == expected, (
                f"Taxonomy {tax_val} expected {expected}, got {len(matched)}"
            )
            total += len(matched)
        assert total == 92

    def test_discover_scenarios_empty_or_nonexistent_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_suite = SuiteRunner(scenarios_dir=Path(tmpdir) / "empty_dir")
            assert empty_suite.discover_scenarios() == []

    def test_discover_scenarios_with_corrupted_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_scenarios = Path(tmpdir) / "scenarios" / "group_a_memory"
            tmp_scenarios.mkdir(parents=True)
            corrupt_file = tmp_scenarios / "MEM-99.yaml"
            corrupt_file.write_text("invalid: [yaml: unclosed bracket", encoding="utf-8")

            suite = SuiteRunner(scenarios_dir=Path(tmpdir) / "scenarios")
            # Without taxonomy filter, it discovers paths
            paths = suite.discover_scenarios()
            assert corrupt_file in paths
            # With taxonomy filter, it attempts parsing and safely skips corrupted file
            filtered = suite.discover_scenarios(
                taxonomy_filter=[ScientificTaxonomy.DETERMINISTIC_SOFTWARE.value]
            )
            assert corrupt_file not in filtered


# ---------------------------------------------------------------------------
# 2. Cross-Scenario ID Uniqueness & Pattern Enforcement Tests
# ---------------------------------------------------------------------------


class TestScenarioIDUniquenessAndPatterns:
    """Stress tests ensuring 100% ID uniqueness and canonical syntax."""

    def test_all_92_ids_match_strict_regex(self, suite_runner: SuiteRunner):
        for p in suite_runner.discover_scenarios():
            sc = ScenarioDefinition.from_yaml_file(p)
            assert ID_STRICT_REGEX.match(sc.id), (
                f"Scenario ID {sc.id!r} in {p.name} does not match "
                f"strict regex {ID_STRICT_REGEX.pattern}"
            )

    def test_global_id_uniqueness(self, suite_runner: SuiteRunner):
        all_ids: list[str] = []
        for p in suite_runner.discover_scenarios():
            sc = ScenarioDefinition.from_yaml_file(p)
            all_ids.append(sc.id)

        assert len(all_ids) == 92
        assert len(set(all_ids)) == 92, (
            f"Duplicate scenario IDs detected: {len(all_ids)} total vs {len(set(all_ids))} unique"
        )

    def test_scenario_filename_strictly_matches_id(self, suite_runner: SuiteRunner):
        for p in suite_runner.discover_scenarios():
            sc = ScenarioDefinition.from_yaml_file(p)
            assert p.stem == sc.id, (
                f"Filename mismatch: file stem {p.stem!r} != scenario id {sc.id!r}"
            )

    def test_group_prefix_consistency(self, suite_runner: SuiteRunner):
        for p in suite_runner.discover_scenarios():
            sc = ScenarioDefinition.from_yaml_file(p)
            grp_dir = p.parent.name
            expected_prefix = EXPECTED_GROUP_PREFIXES[grp_dir]
            assert sc.id.startswith(expected_prefix), (
                f"Scenario {sc.id} in {grp_dir} does not start with "
                f"expected prefix {expected_prefix}"
            )

    def test_group_sequence_zero_gaps(self, suite_runner: SuiteRunner):
        for grp_dir, expected_count in EXPECTED_GROUP_COUNTS.items():
            paths = suite_runner.discover_scenarios(group_filter=[grp_dir])
            prefix = EXPECTED_GROUP_PREFIXES[grp_dir]
            expected_ids = [f"{prefix}-{i:02d}" for i in range(1, expected_count + 1)]
            actual_ids = [ScenarioDefinition.from_yaml_file(p).id for p in paths]
            assert actual_ids == expected_ids, (
                f"Sequence gap in {grp_dir}: expected {expected_ids}, got {actual_ids}"
            )


# ---------------------------------------------------------------------------
# 3. Schema Mutation & Fuzzing Tests
# ---------------------------------------------------------------------------


class TestSchemaMutationAndFuzzing:
    """Adversarial stress-testing of Pydantic V2 ScenarioDefinition schema."""

    @pytest.fixture
    def canonical_dict(self) -> dict[str, Any]:
        return {
            "id": "MEM-01",
            "group": "Group A: Autobiographical Memory",
            "title": "Canonical Autobiographical Retrieval",
            "research_hypothesis": "Model recalls user facts across conversational boundaries.",
            "taxonomy": "deterministic_software",
            "severity": "critical",
            "execution_mode": "automated_immediate",
            "hardware_prereq": "none",
            "model_dependency": "pinned_primary",
            "pre_conditions": {
                "runtime_settings": {"num_ctx": 4096, "temperature": 0.0, "seed": 42},
                "initial_state": {
                    "actors": [{"id": "actor-owner-01", "owner": True, "consent": True}],
                    "memories": [{"text": "Owner cat is named Luna", "actor_id": "actor-owner-01"}],
                    "preferences": [{"key": "lang", "value": "uk", "actor_id": "actor-owner-01"}],
                    "files": {"note.txt": "Secret note"},
                    "mock_services": [{"name": "auth", "endpoint": "http://127.0.0.1:9999"}],
                },
            },
            "interactions": [
                {
                    "turn": 0,
                    "actor_id": "actor-owner-01",
                    "input": "Як звати мого кота?",
                    "new_session": False,
                    "expected_behaviors": [
                        {"type": "content_contains", "value": "Luna", "ignore_case": True}
                    ],
                    "forbidden_behaviors": [
                        {"type": "content_contains", "value": "Барсік", "ignore_case": True}
                    ],
                }
            ],
            "ground_truth": {
                "reference_answer": "Кота звати Luna.",
                "evidence_criteria": "Direct recall without hallucination.",
                "target_metrics": {"ttft_s_max": 2.0, "total_latency_s_max": 10.0},
            },
            "evaluation": {
                "method": "deterministic_rule",
                "pass_criteria": "Recall verified.",
            },
            "required_artifacts": ["turn_results.json"],
            "metadata": {"author": "ChallengerTest"},
        }

    def test_canonical_dict_validates_cleanly(self, canonical_dict: dict[str, Any]):
        sc = ScenarioDefinition.model_validate(canonical_dict)
        assert sc.id == "MEM-01"
        assert sc.taxonomy == ScientificTaxonomy.DETERMINISTIC_SOFTWARE

    @pytest.mark.parametrize(
        "bad_id",
        [
            "M-01",  # 1 char prefix
            "TOOLONG-01",  # >4 char non-journey prefix
            "mem-01",  # lowercase prefix
            "MEM_01",  # underscore instead of hyphen
            "MEM:01",  # colon instead of hyphen
            "MEM-1",  # 1 digit suffix
            "MEM-001",  # 3 digit suffix
            "MEM-XX",  # non-digit suffix
            "JOURNEYS-01",  # typo in JOURNEY
            "JOURNEY_01",  # underscore in journey
            "",  # empty string
            "   ",  # whitespace
            None,  # None
            12345,  # int
            ["MEM-01"],  # list
            {"id": "MEM-01"},  # dict
        ],
    )
    def test_id_mutation_rejection(self, canonical_dict: dict[str, Any], bad_id: Any):
        mutated = dict(canonical_dict)
        mutated["id"] = bad_id
        with pytest.raises((ValidationError, TypeError)):
            ScenarioDefinition.model_validate(mutated)

    @pytest.mark.parametrize(
        ("enum_field", "bad_val"),
        [
            ("taxonomy", "quantum_entanglement"),
            ("taxonomy", "DETERMINISTIC_SOFTWARE"),  # uppercase string not matching lowercase enum
            ("taxonomy", 123),
            ("taxonomy", None),
            ("severity", "apocalyptic"),
            ("severity", "HIGH"),  # uppercase string
            ("severity", -1),
            ("severity", None),
            ("execution_mode", "teleportation"),
            ("execution_mode", "AUTOMATED_IMMEDIATE"),
            ("execution_mode", False),
            ("execution_mode", None),
        ],
    )
    def test_enum_mutations_strictly_rejected(
        self, canonical_dict: dict[str, Any], enum_field: str, bad_val: Any
    ):
        mutated = dict(canonical_dict)
        mutated[enum_field] = bad_val
        with pytest.raises((ValidationError, TypeError)):
            ScenarioDefinition.model_validate(mutated)

    @pytest.mark.parametrize(
        "required_field",
        ["id", "group", "title", "research_hypothesis", "taxonomy", "severity", "execution_mode"],
    )
    def test_omission_of_required_fields_rejected(
        self, canonical_dict: dict[str, Any], required_field: str
    ):
        mutated = dict(canonical_dict)
        del mutated[required_field]
        with pytest.raises(ValidationError):
            ScenarioDefinition.model_validate(mutated)

    @pytest.mark.parametrize(
        "required_field",
        ["id", "group", "title", "research_hypothesis", "taxonomy", "severity", "execution_mode"],
    )
    def test_typo_in_required_field_name_rejected(
        self, canonical_dict: dict[str, Any], required_field: str
    ):
        mutated = dict(canonical_dict)
        val = mutated.pop(required_field)
        mutated[f"{required_field}_typo"] = val
        with pytest.raises(ValidationError):
            ScenarioDefinition.model_validate(mutated)

    @pytest.mark.parametrize(
        ("num_ctx", "should_fail"),
        [
            (256, True),  # below ge=512
            (511, True),
            (512, False),  # min valid
            (4096, False),  # nominal
            (32768, False),  # max valid
            (32769, True),  # above le=32768
            (65536, True),
            (-100, True),
            ("not_int", True),
        ],
    )
    def test_runtime_settings_num_ctx_bounds(
        self, canonical_dict: dict[str, Any], num_ctx: Any, should_fail: bool
    ):
        mutated = dict(canonical_dict)
        mutated["pre_conditions"] = {"runtime_settings": {"num_ctx": num_ctx, "temperature": 0.0}}
        if should_fail:
            with pytest.raises(ValidationError):
                ScenarioDefinition.model_validate(mutated)
        else:
            sc = ScenarioDefinition.model_validate(mutated)
            assert sc.pre_conditions.runtime_settings.num_ctx == num_ctx

    @pytest.mark.parametrize(
        ("temp", "should_fail"),
        [
            (-0.1, True),  # below ge=0.0
            (0.0, False),  # min valid
            (1.0, False),  # nominal
            (2.0, False),  # max valid
            (2.01, True),  # above le=2.0
            (10.0, True),
            ("cold", True),
        ],
    )
    def test_runtime_settings_temperature_bounds(
        self, canonical_dict: dict[str, Any], temp: Any, should_fail: bool
    ):
        mutated = dict(canonical_dict)
        mutated["pre_conditions"] = {"runtime_settings": {"num_ctx": 4096, "temperature": temp}}
        if should_fail:
            with pytest.raises(ValidationError):
                ScenarioDefinition.model_validate(mutated)
        else:
            sc = ScenarioDefinition.model_validate(mutated)
            assert sc.pre_conditions.runtime_settings.temperature == temp

    @pytest.mark.parametrize(
        "bad_turn",
        [
            {"turn": -1, "input": "valid"},  # negative turn
            {"turn": 0, "input": ""},  # empty input min_length=1
            {"turn": "zero", "input": "valid"},  # non-integer turn
            {"turn": 0, "input": 12345},  # non-string input
            {"turn": 0, "input": None},  # None input
        ],
    )
    def test_interaction_turn_constraints(
        self, canonical_dict: dict[str, Any], bad_turn: dict[str, Any]
    ):
        mutated = dict(canonical_dict)
        mutated["interactions"] = [bad_turn]
        with pytest.raises(ValidationError):
            ScenarioDefinition.model_validate(mutated)

    def test_randomized_fuzzing_harness_1000_iterations(self, canonical_dict: dict[str, Any]):
        """Generates 1,000 randomized invalid mutations and verifies 100% strict rejection."""
        random.seed(20261110)

        def rand_str(k=8):
            return "".join(random.choices(string.ascii_letters + string.digits, k=k))

        tested = 0
        rejected = 0

        for _ in range(1000):
            mutated = dict(canonical_dict)
            mode = random.choice(
                [
                    "bad_taxonomy",
                    "bad_severity",
                    "bad_mode",
                    "bad_id",
                    "bad_turn_type",
                    "negative_turn",
                    "empty_input",
                    "bad_num_ctx",
                    "bad_temp",
                    "missing_required",
                    "bad_interactions_type",
                ]
            )

            if mode == "bad_taxonomy":
                mutated["taxonomy"] = random.choice(["fuzz_" + rand_str(), 100, None, []])
            elif mode == "bad_severity":
                mutated["severity"] = random.choice(["fuzz_" + rand_str(), -5, None])
            elif mode == "bad_mode":
                mutated["execution_mode"] = random.choice(["fuzz_" + rand_str(), 3.14, {}])
            elif mode == "bad_id":
                mutated["id"] = random.choice(["bad", "12-34", "MEM-1", "JOURNEYS-01", rand_str()])
            elif mode == "bad_turn_type":
                mutated["interactions"] = random.choice(["not_a_list", 9999, {"turn": 0}])
            elif mode == "negative_turn":
                mutated["interactions"] = [{"turn": random.randint(-1000, -1), "input": "fuzz"}]
            elif mode == "empty_input":
                mutated["interactions"] = [{"turn": 0, "input": ""}]
            elif mode == "bad_num_ctx":
                mutated["pre_conditions"] = {
                    "runtime_settings": {"num_ctx": random.choice([0, 100, 50000, -500])}
                }
            elif mode == "bad_temp":
                mutated["pre_conditions"] = {
                    "runtime_settings": {"temperature": random.choice([-1.0, 2.5, 99.0])}
                }
            elif mode == "missing_required":
                field = random.choice(
                    [
                        "id",
                        "group",
                        "title",
                        "research_hypothesis",
                        "taxonomy",
                        "severity",
                        "execution_mode",
                    ]
                )
                del mutated[field]
            elif mode == "bad_interactions_type":
                mutated["interactions"] = random.choice([123, True, "interactions_string"])

            tested += 1
            try:
                ScenarioDefinition.model_validate(mutated)
            except (ValidationError, TypeError):
                rejected += 1

        assert tested == 1000
        assert rejected == 1000, f"Fuzzing failure: {rejected}/{tested} rejected"


# ---------------------------------------------------------------------------
# 4. Batch Runner Reporting & Serialization Edge Cases
# ---------------------------------------------------------------------------


class TestSuiteRunnerReporting:
    """Stress tests for JUnit XML and JSON summary generation under varied statuses."""

    def test_run_suite_empty_paths_returns_empty_list(self, suite_runner: SuiteRunner):
        reports = suite_runner.run_suite(scenario_paths=[])
        assert reports == []

    def test_generate_junit_xml_validity(self, suite_runner: SuiteRunner):
        mock_reports = [
            ExecutionReport(
                scenario_id="MEM-01",
                group="group_a_memory",
                title="Autobiographical Memory Retrieval",
                taxonomy=ScientificTaxonomy.DETERMINISTIC_SOFTWARE,
                severity=ScenarioSeverity.HIGH,
                execution_mode=ExecutionMode.AUTOMATED_IMMEDIATE,
                status=ExecutionStatus.EXECUTED_PASS,
                all_passed=True,
                latencies_ms=[120.0, 85.0],
                started_at="2026-11-10T10:00:00Z",
                completed_at="2026-11-10T10:00:01Z",
                raw_score=1.0,
            ),
            ExecutionReport(
                scenario_id="SEC-01",
                group="group_e_security",
                title="Indirect Prompt Injection Jailbreak",
                taxonomy=ScientificTaxonomy.CONTROLLED_EXPERIMENTAL,
                severity=ScenarioSeverity.CRITICAL,
                execution_mode=ExecutionMode.AUTOMATED_IMMEDIATE,
                status=ExecutionStatus.EXECUTED_FAIL,
                all_passed=False,
                latencies_ms=[250.0],
                started_at="2026-11-10T10:00:01Z",
                completed_at="2026-11-10T10:00:02Z",
                raw_score=0.0,
            ),
            ExecutionReport(
                scenario_id="ROB-01",
                group="group_j_robotics",
                title="Single-Writer Actuator Lease Enforcement",
                taxonomy=ScientificTaxonomy.PHYSICAL_ACCEPTANCE,
                severity=ScenarioSeverity.CRITICAL,
                execution_mode=ExecutionMode.BLOCKED_HARDWARE,
                status=ExecutionStatus.BLOCKED_HARDWARE,
                blocker_reason="Missing physical hardware: reachy_actuator_bus",
                all_passed=False,
                latencies_ms=[0.0],
                started_at="2026-11-10T10:00:02Z",
                completed_at="2026-11-10T10:00:02Z",
                raw_score=0.0,
            ),
            ExecutionReport(
                scenario_id="LT-02",
                group="group_b_continuity",
                title="Day 7 Memory Retention",
                taxonomy=ScientificTaxonomy.CONTROLLED_EXPERIMENTAL,
                severity=ScenarioSeverity.HIGH,
                execution_mode=ExecutionMode.BLOCKED_DELAY,
                status=ExecutionStatus.BLOCKED_DELAY,
                blocker_reason="Requires real-time 7-day wall-clock elapsed interval",
                all_passed=False,
                latencies_ms=[0.0],
                started_at="2026-11-10T10:00:02Z",
                completed_at="2026-11-10T10:00:02Z",
                raw_score=0.0,
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            junit_path = Path(tmpdir) / "test_junit.xml"
            out = suite_runner.generate_junit_xml(mock_reports, junit_path)
            assert out.exists()

            # Parse XML and verify schema
            tree = ET.parse(out)
            root = tree.getroot()
            assert root.tag == "testsuite"
            assert root.attrib["tests"] == "4"
            assert root.attrib["failures"] == "1"
            assert root.attrib["skipped"] == "2"

            cases = root.findall("testcase")
            assert len(cases) == 4
            # Verify failure child element
            fail_case = [c for c in cases if "SEC-01" in c.attrib["name"]][0]
            assert fail_case.find("failure") is not None
            # Verify skipped child element
            rob_case = [c for c in cases if "ROB-01" in c.attrib["name"]][0]
            assert rob_case.find("skipped") is not None

    def test_generate_json_summary_validity(self, suite_runner: SuiteRunner):
        mock_reports = [
            ExecutionReport(
                scenario_id="MEM-01",
                group="group_a_memory",
                title="Autobiographical Memory Retrieval",
                taxonomy=ScientificTaxonomy.DETERMINISTIC_SOFTWARE,
                severity=ScenarioSeverity.HIGH,
                execution_mode=ExecutionMode.AUTOMATED_IMMEDIATE,
                status=ExecutionStatus.EXECUTED_PASS,
                all_passed=True,
                latencies_ms=[100.0],
                started_at="2026-11-10T10:00:00Z",
                completed_at="2026-11-10T10:00:01Z",
                raw_score=1.0,
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "summary.json"
            out = suite_runner.generate_json_summary(mock_reports, json_path)
            assert out.exists()

            with open(out, encoding="utf-8") as f:
                data = json.load(f)

            assert data["total_scenarios"] == 1
            assert data["passed"] == 1
            assert data["failed"] == 0
            assert len(data["reports"]) == 1
            assert data["reports"][0]["scenario_id"] == "MEM-01"
