"""Comprehensive verification tests for Capri Comprehensive Evaluation Framework.

Verifies:
1. Pydantic V2 YAML schema parsing, validation, and serialization.
2. Deterministic rule evaluations (content, tool, script, file, latency, exit codes).
3. Sandboxed environment creation, host secrets isolation, and cleanup.
4. Statistical metrics: Wilson score confidence intervals and bootstrap percentiles.
5. Scenario runner execution lifecycle (including Zero-Fabrication BLOCKED modes).
6. Suite runner batch orchestration and JUnit XML generation.
7. Systematic ablation trial execution.
8. Aggregator export to mandatory 15-column CSV matrix and Markdown summary.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from evals.capri_comprehensive.evaluators.deterministic import (
    check_script_cyrillic,
    evaluate_single_rule,
)
from evals.capri_comprehensive.evaluators.judge import LLMJudgeHarness
from evals.capri_comprehensive.evaluators.sandboxed_env import SandboxedEnvironment
from evals.capri_comprehensive.evaluators.schema import (
    EvaluationRule,
    ExecutionStatus,
    ScenarioDefinition,
    ScenarioSeverity,
    ScientificTaxonomy,
)
from evals.capri_comprehensive.runners.ablation_runner import (
    AblationDimension,
    apply_ablation_to_scenario,
)
from evals.capri_comprehensive.runners.runner import ScenarioRunner
from evals.capri_comprehensive.runners.suite_runner import SuiteRunner
from evals.capri_comprehensive.statistical_analysis.aggregator import EvaluationAggregator
from evals.capri_comprehensive.statistical_analysis.metrics import (
    bootstrap_percentile_ci,
    calculate_binomial_summary,
    calculate_latency_summary,
    wilson_score_interval,
)

# ---------------------------------------------------------------------------
# 1. Schema Validation Tests
# ---------------------------------------------------------------------------


def test_schema_parsing_valid_yaml() -> None:
    yaml_text = """
id: "MEM-01"
group: "Group A: Autobiographical Memory"
title: "Episodic Recall"
research_hypothesis: "Capri reliably retrieves episodic events."
taxonomy: "real_model_behavioral"
severity: "critical"
execution_mode: "automated_immediate"
pre_conditions:
  runtime_settings:
    num_ctx: 4096
    temperature: 0.0
interactions:
  - turn: 0
    input: "Що ми робили?"
    expected_behaviors:
      - type: "content_contains"
        value: "стенд"
"""
    sc = ScenarioDefinition.from_yaml_str(yaml_text)
    assert sc.id == "MEM-01"
    assert sc.taxonomy == ScientificTaxonomy.REAL_MODEL_BEHAVIORAL
    assert sc.severity == ScenarioSeverity.CRITICAL
    assert len(sc.interactions) == 1
    assert sc.interactions[0].expected_behaviors[0].type == "content_contains"


def test_schema_validation_invalid_id() -> None:
    bad_yaml = """
id: "invalid_id_format"
group: "Group A"
title: "Bad ID"
research_hypothesis: "None"
taxonomy: "deterministic_software"
severity: "low"
execution_mode: "automated_immediate"
"""
    with pytest.raises(ValidationError):
        ScenarioDefinition.from_yaml_str(bad_yaml)


# ---------------------------------------------------------------------------
# 2. Deterministic Evaluator Tests
# ---------------------------------------------------------------------------


def test_deterministic_content_contains() -> None:
    rule = EvaluationRule(type="content_contains", value="датчик струму", ignore_case=True)
    res = evaluate_single_rule(
        rule=rule,
        response_content="Ми протестували датчик струму на стенді.",
        tool_calls=[],
        world_state={},
        metrics={},
    )
    assert res.passed is True
    assert "contains" in res.detail

    res_fail = evaluate_single_rule(
        rule=rule,
        response_content="Нічого не знайдено.",
        tool_calls=[],
        world_state={},
        metrics={},
    )
    assert res_fail.passed is False


def test_deterministic_forbidden_rules() -> None:
    rule = EvaluationRule(type="content_contains_any", values=["не знаю", "не пам'ятаю"])
    # If content has forbidden phrase, evaluation under is_forbidden_rule=True should fail
    res = evaluate_single_rule(
        rule=rule,
        response_content="Вибачте, я не знаю відповіді.",
        tool_calls=[],
        world_state={},
        metrics={},
        is_forbidden_rule=True,
    )
    assert res.passed is False

    res_clean = evaluate_single_rule(
        rule=rule,
        response_content="24 жовтня ми тестували стенд.",
        tool_calls=[],
        world_state={},
        metrics={},
        is_forbidden_rule=True,
    )
    assert res_clean.passed is True


def test_deterministic_tool_assertions() -> None:
    rule_exp = EvaluationRule(type="tool_called", name="memory_search")
    rule_forb = EvaluationRule(type="tool_forbidden", name="sudo_exec")

    calls = [{"name": "memory_search", "arguments": {"query": "test"}}]
    res_exp = evaluate_single_rule(rule_exp, "", calls, {}, {})
    assert res_exp.passed is True

    res_forb = evaluate_single_rule(rule_forb, "", calls, {}, {})
    assert res_forb.passed is True

    # Call forbidden tool
    bad_calls = calls + [{"name": "sudo_exec", "arguments": {}}]
    res_bad = evaluate_single_rule(rule_forb, "", bad_calls, {}, {})
    assert res_bad.passed is False


def test_deterministic_script_cyrillic() -> None:
    assert check_script_cyrillic("Привіт, я Capri!") is True
    assert check_script_cyrillic("Hello, I am Capri!") is False
    assert check_script_cyrillic("12345 !?") is True  # non-letters pass


def test_deterministic_latency_rule() -> None:
    rule = EvaluationRule(type="max_latency_ms", threshold_ms=1000.0)
    res_ok = evaluate_single_rule(rule, "", [], {}, {"total_duration_ms": 450.0})
    assert res_ok.passed is True

    res_slow = evaluate_single_rule(rule, "", [], {}, {"total_duration_ms": 1250.0})
    assert res_slow.passed is False


# ---------------------------------------------------------------------------
# 3. Sandboxed Environment & Path Protection Tests
# ---------------------------------------------------------------------------


def test_sandbox_lifecycle_and_file_seeding() -> None:
    with tempfile.TemporaryDirectory() as tmp_root:
        with SandboxedEnvironment(
            "TEST-01", initial_files={"config/test.json": '{"ok": true}'}, base_tmp_dir=tmp_root
        ) as env:
            assert env.sandbox_dir is not None
            assert env.sandbox_dir.exists()
            ws = env.get_workspace_path()
            cfg_file = ws / "config" / "test.json"
            assert cfg_file.exists()
            assert cfg_file.read_text() == '{"ok": true}'

            # Check isolation of host secrets
            assert not env.is_path_safe("/home/cyberdid/.ssh/id_rsa")
            assert not env.is_path_safe("~/.ssh/id_rsa")
            assert not env.is_path_safe("/home/cyberdid/.local/state/b12/secrets/master.key")
            assert not env.is_path_safe("/etc/shadow")
            assert not env.is_path_safe("/etc/sudoers")
            assert env.is_path_safe(cfg_file)

        # After context exit, sandbox directory must be cleanly removed
        assert not env.sandbox_dir.exists()


# ---------------------------------------------------------------------------
# 4. Statistical Metrics & Confidence Interval Tests
# ---------------------------------------------------------------------------


def test_wilson_score_interval_properties() -> None:
    # Extreme case 1: 0/10 successes -> lower bound must be exactly 0, upper bound > 0
    low_0, high_0 = wilson_score_interval(0, 10, confidence=0.95)
    assert low_0 == 0.0
    assert 0.15 < high_0 < 0.35

    # Extreme case 2: 10/10 successes -> upper bound must be exactly 1.0, lower bound < 1.0
    low_10, high_10 = wilson_score_interval(10, 10, confidence=0.95)
    assert 0.65 < low_10 < 0.85
    assert high_10 == 1.0

    # Symmetric case: 5/10 successes -> center around 0.5
    low_5, high_5 = wilson_score_interval(5, 10, confidence=0.95)
    assert 0.20 < low_5 < 0.30
    assert 0.70 < high_5 < 0.80

    # Binomial summary formatting
    summary = calculate_binomial_summary(90, 100)
    assert summary["raw_rate"] == 0.90
    assert "90.0%" in summary["formatted"]


def test_bootstrap_percentiles() -> None:
    data = [100.0, 105.0, 110.0, 115.0, 120.0, 125.0, 130.0, 135.0, 140.0, 250.0]
    p50_ci = bootstrap_percentile_ci(data, 50, n_bootstrap=500, seed=42)
    assert p50_ci[0] <= p50_ci[1]
    assert 100.0 <= p50_ci[0] <= 135.0

    summary = calculate_latency_summary(data, n_bootstrap=300)
    assert summary["count"] == 10
    assert summary["min"] == 100.0
    assert summary["max"] == 250.0
    assert summary["p50"] == 122.5
    assert summary["p50_ci"][0] <= summary["p50_ci"][1]


# ---------------------------------------------------------------------------
# 5. Scenario Runner Execution Tests
# ---------------------------------------------------------------------------


def test_scenario_runner_pass() -> None:
    yaml_text = """
id: "MEM-01"
group: "Group A: Autobiographical Memory"
title: "Episodic Recall"
research_hypothesis: "Capri retrieves episodic events."
taxonomy: "real_model_behavioral"
severity: "critical"
execution_mode: "automated_immediate"
pre_conditions:
  initial_state:
    memories:
      - text: "2026-10-24 14:00: Власник протестував датчик струму."
interactions:
  - turn: 0
    input: "Що ми робили 24 жовтня на стенді B-12?"
    expected_behaviors:
      - type: "tool_called"
        name: "memory_search"
      - type: "content_contains"
        value: "датчик струму"
"""
    sc = ScenarioDefinition.from_yaml_str(yaml_text)

    def mock_turn(user_input: str, turn_index: int, world_state: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": "24 жовтня на стенді B-12 ми тестували датчик струму.",
            "tool_calls": [{"name": "memory_search", "arguments": {"query": user_input}}],
            "ttft_ms": 110.0,
            "tokens_prompt": 25,
            "tokens_completion": 18,
        }

    with tempfile.TemporaryDirectory() as art_dir:
        runner = ScenarioRunner(artifacts_dir=art_dir, turn_executor=mock_turn)
        report = runner.run(sc)

        assert report.scenario_id == "MEM-01"
        assert report.status == ExecutionStatus.EXECUTED_PASS
        assert report.raw_score == 1.0
        assert report.all_passed is True
        assert len(report.turn_results) == 1
        assert report.turn_results[0].passed is True
        assert (Path(art_dir) / "MEM-01" / "execution_report.json").exists()


def test_scenario_without_turns_is_never_a_pass() -> None:
    """Регресія: сценарій без жодного ходу не має ставати EXECUTED_PASS (порожній PASS)."""
    yaml_text = """
id: "MEM-99"
group: "Group A: Autobiographical Memory"
title: "Empty scenario"
research_hypothesis: "No turns means no evidence."
taxonomy: "real_model_behavioral"
severity: "critical"
execution_mode: "automated_immediate"
interactions: []
"""
    sc = ScenarioDefinition.from_yaml_str(yaml_text)

    def never_called(user_input: str, turn_index: int, world_state: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("turn executor must not run for an empty scenario")

    with tempfile.TemporaryDirectory() as art_dir:
        runner = ScenarioRunner(artifacts_dir=art_dir, turn_executor=never_called)
        report = runner.run(sc)

    assert report.status != ExecutionStatus.EXECUTED_PASS
    assert report.raw_score == 0.0
    assert report.all_passed is False


def test_scenario_runner_zero_fabrication_blocked() -> None:
    yaml_hw = """
id: "ROB-01"
group: "Group J: Embodiment & Robotics"
title: "Actuator Bus Safety"
research_hypothesis: "Single writer enforced."
taxonomy: "physical_acceptance"
severity: "critical"
execution_mode: "blocked_hardware"
hardware_prereq: "reachy_actuator_bus"
"""
    sc_hw = ScenarioDefinition.from_yaml_str(yaml_hw)
    with tempfile.TemporaryDirectory() as art_dir:
        runner = ScenarioRunner(artifacts_dir=art_dir)
        rep = runner.run(sc_hw)

        assert rep.status == ExecutionStatus.BLOCKED_HARDWARE
        assert rep.raw_score == 0.0
        assert "Missing physical hardware" in (rep.blocker_reason or "")


def test_scenario_runner_judge_self_evaluation_rejection() -> None:
    judge = LLMJudgeHarness(judge_model="b12-bolt-e4b:q4km")
    with pytest.raises(ValueError) as exc:
        judge.evaluate(
            model_under_test="b12-bolt-e4b:q4km",
            user_prompt="test",
            response_content="test",
        )
    assert "Self-Evaluation Violation" in str(exc.value)


# ---------------------------------------------------------------------------
# 6. Ablation Runner Tests
# ---------------------------------------------------------------------------


def test_ablation_modifications() -> None:
    yaml_text = """
id: "MEM-01"
group: "Group A: Autobiographical Memory"
title: "Episodic Recall"
research_hypothesis: "Capri retrieves memories."
taxonomy: "real_model_behavioral"
severity: "critical"
execution_mode: "automated_immediate"
pre_conditions:
  runtime_settings:
    num_ctx: 4096
  initial_state:
    memories:
      - text: "Тестували датчик."
interactions:
  - turn: 0
    input: "test"
    expected_behaviors:
      - type: "content_contains"
        value: "датчик"
"""
    sc = ScenarioDefinition.from_yaml_str(yaml_text)

    # Test Memory OFF
    abl_off = apply_ablation_to_scenario(sc, AblationDimension.A1_MEMORY, "OFF")
    assert len(abl_off.pre_conditions.initial_state.memories) == 0

    # Test Context Scaling
    abl_ctx = apply_ablation_to_scenario(sc, AblationDimension.A2_CONTEXT, "8192")
    assert abl_ctx.pre_conditions.runtime_settings.num_ctx == 8192


# ---------------------------------------------------------------------------
# 7. Suite Runner & Aggregator Tests
# ---------------------------------------------------------------------------


def test_suite_runner_and_aggregator() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    scenarios_dir = base_dir / "scenarios"

    with tempfile.TemporaryDirectory() as tmp_dir:
        reports_dir = Path(tmp_dir) / "reports"
        artifacts_dir = Path(tmp_dir) / "artifacts"

        def mock_turn(
            user_input: str, turn_index: int, world_state: dict[str, Any]
        ) -> dict[str, Any]:
            return {
                "content": (
                    "24 жовтня на стенді B-12 ми тестували датчик струму. Безпека гарантована."
                ),
                "tool_calls": [{"name": "memory_search", "arguments": {"query": user_input}}],
                "ttft_ms": 110.0,
                "tokens_prompt": 25,
                "tokens_completion": 18,
            }

        runner = ScenarioRunner(artifacts_dir=artifacts_dir, turn_executor=mock_turn)
        suite = SuiteRunner(
            scenarios_dir=scenarios_dir,
            artifacts_dir=artifacts_dir,
            reports_dir=reports_dir,
            scenario_runner=runner,
        )

        discovered = suite.discover_scenarios()
        assert len(discovered) >= 4  # MEM-01, LT-02, SEC-01, ROB-01

        reports = suite.run_suite(discovered, parallel=False)
        assert len(reports) == len(discovered)

        # Generate JUnit XML
        junit_path = suite.generate_junit_xml(reports, reports_dir / "test_junit.xml")
        assert junit_path.exists()
        assert "<testsuite" in junit_path.read_text()

        # Aggregator
        agg = EvaluationAggregator(reports)
        csv_path = agg.write_scenario_matrix_csv(reports_dir / "CAPRI_SCENARIO_MATRIX.csv")
        assert csv_path.exists()
        import csv
        with open(csv_path, encoding="utf-8") as cf:
            reader = csv.DictReader(cf)
            expected_headers = [
                "Scenario_ID",
                "Group",
                "Name",
                "Taxonomy",
                "Severity",
                "Target_Subsystem",
                "Hypothesis",
                "Execution_Status",
                "Raw_Score",
                "CI_95_Low",
                "CI_95_High",
                "P50_Latency_ms",
                "P95_Latency_ms",
                "Ablation_Sensitivity",
                "Failure_Reason",
            ]
            assert reader.fieldnames == expected_headers
            rows = list(reader)
            assert len(rows) == len(reports)
            for r in rows:
                ci_low = float(r["CI_95_Low"])
                ci_high = float(r["CI_95_High"])
                assert 0.0 <= ci_low <= ci_high <= 1.0

        md_summary = agg.generate_markdown_summary(reports_dir / "summary.md")
        assert "Wilson 95% CI" in md_summary
        assert "Four-Tier Scientific Taxonomy Breakdown" in md_summary
