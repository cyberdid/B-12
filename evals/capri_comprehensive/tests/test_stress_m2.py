"""Empirical stress tests for statistical metrics and ablation architecture (Milestone M2).

Stress-tests:
1. Wilson score confidence interval boundary conditions (k=0/n=100, k=100/n=100, k=0/n=0, k=1/n=1).
2. Inverse normal CDF rational approximation and high-confidence interval bug reproduction.
3. Bootstrap latency estimation edge cases (empty, single-value, identical, 10k outliers).
4. Ablation runner configuration modifications across all 5 experimental dimensions.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from evals.capri_comprehensive.evaluators.deterministic import (
    check_script_cyrillic,
    evaluate_single_rule,
)
from evals.capri_comprehensive.evaluators.sandboxed_env import (
    HOST_HOME,
    SandboxedEnvironment,
)
from evals.capri_comprehensive.evaluators.schema import (
    EvaluationRule,
    ScenarioDefinition,
)
from evals.capri_comprehensive.runners.ablation_runner import (
    ABLATION_CONDITIONS,
    AblationDimension,
    AblationRunner,
    apply_ablation_to_scenario,
)
from evals.capri_comprehensive.runners.runner import ScenarioRunner
from evals.capri_comprehensive.statistical_analysis.metrics import (
    _normal_ppf,
    bootstrap_percentile_ci,
    calculate_binomial_summary,
    calculate_latency_summary,
    wilson_score_interval,
)

# ---------------------------------------------------------------------------
# 1. Wilson Score Confidence Interval Boundary Tests
# ---------------------------------------------------------------------------


def test_wilson_boundary_zero_successes_out_of_100() -> None:
    """k=0, n=100: lower bound must be exactly 0.0, upper bound strictly in (0, 0.05)."""
    low, high = wilson_score_interval(0, 100, confidence=0.95)
    assert low == 0.0
    assert 0.036 <= high <= 0.0371  # Exact Wilson is ~0.036993
    assert 0.0 <= low <= high <= 1.0

    summary = calculate_binomial_summary(0, 100, confidence=0.95)
    assert summary["raw_rate"] == 0.0
    assert summary["ci_low"] == 0.0
    assert 0.036 <= summary["ci_high"] <= 0.0371
    assert "0.0%" in summary["formatted"]


def test_wilson_boundary_all_successes_out_of_100() -> None:
    """k=100, n=100: upper bound must be exactly 1.0, lower bound strictly in (0.96, 1.0)."""
    low, high = wilson_score_interval(100, 100, confidence=0.95)
    assert 0.9629 <= low <= 0.9640  # Exact Wilson is ~0.963007
    assert high == 1.0
    assert 0.0 <= low <= high <= 1.0

    summary = calculate_binomial_summary(100, 100, confidence=0.95)
    assert summary["raw_rate"] == 1.0
    assert 0.9629 <= summary["ci_low"] <= 0.9640
    assert summary["ci_high"] == 1.0
    assert "100.0%" in summary["formatted"]


def test_wilson_boundary_zero_trials() -> None:
    """k=0, n=0: must return (0.0, 0.0) without ZeroDivisionError."""
    low, high = wilson_score_interval(0, 0, confidence=0.95)
    assert low == 0.0
    assert high == 0.0

    # Negative total should also return (0.0, 0.0) safely
    low_neg, high_neg = wilson_score_interval(0, -5, confidence=0.95)
    assert low_neg == 0.0
    assert high_neg == 0.0

    summary = calculate_binomial_summary(0, 0, confidence=0.95)
    assert summary["raw_rate"] == 0.0
    assert summary["ci_low"] == 0.0
    assert summary["ci_high"] == 0.0
    assert summary["formatted"] == "N/A (0/0)"


def test_wilson_boundary_single_trial_single_success() -> None:
    """k=1, n=1: strictly bounded in [0, 1] with non-zero lower bound and 1.0 upper bound."""
    low, high = wilson_score_interval(1, 1, confidence=0.95)
    assert 0.20 <= low <= 0.21  # Exact Wilson is ~0.206549
    assert high == 1.0
    assert 0.0 <= low <= high <= 1.0

    summary = calculate_binomial_summary(1, 1, confidence=0.95)
    assert summary["raw_rate"] == 1.0
    assert 0.20 <= summary["ci_low"] <= 0.21
    assert summary["ci_high"] == 1.0


def test_wilson_score_invalid_inputs() -> None:
    """Invalid input values must raise ValueError."""
    with pytest.raises(ValueError):
        wilson_score_interval(-1, 10)

    with pytest.raises(ValueError):
        wilson_score_interval(15, 10)

    with pytest.raises(ValueError):
        wilson_score_interval(5, 10, confidence=1.5)

    with pytest.raises(ValueError):
        wilson_score_interval(5, 10, confidence=0.0)


def test_wilson_score_high_confidence_99_bug_reproduction() -> None:
    """Verify valid Wilson score intervals for high confidence (confidence=0.99)."""
    low, high = wilson_score_interval(90, 100, confidence=0.99)
    assert low <= high, f"Expected low <= high, but got low={low} > high={high}"
    assert 0.79 <= low <= 0.81
    assert 0.95 <= high <= 0.96


def test_normal_ppf_sign_inversion_empirical_audit() -> None:
    """Empirically inspect _normal_ppf across central and tail regions."""
    # Central region (p_low=0.02425 <= p <= p_high=0.97575) works correctly
    z_050 = _normal_ppf(0.5)
    assert abs(z_050) < 1e-7

    z_095 = _normal_ppf(0.975)  # 95% CI upper tail: inside central region
    assert 1.959 <= z_095 <= 1.961

    # Tail region audit:
    # Quantile function of standard normal for p > 0.5 MUST be positive!
    # For p=0.995, exact z is +2.575829
    z_tail_high = _normal_ppf(0.995)
    assert z_tail_high > 0.0, "_normal_ppf(0.995) must return positive"
    assert 2.57 <= z_tail_high <= 2.58

    # And for lower tail p=0.005, exact z is -2.575829
    z_tail_low = _normal_ppf(0.005)
    assert z_tail_low < 0.0, "_normal_ppf(0.005) must return negative"
    assert -2.58 <= z_tail_low <= -2.57


# ---------------------------------------------------------------------------
# 2. Bootstrap Latency Estimation Stress Tests
# ---------------------------------------------------------------------------


def test_bootstrap_latency_empty_input() -> None:
    """Empty list must return cleanly with zero counts and (0.0, 0.0) CIs."""
    summary = calculate_latency_summary([])
    assert summary["count"] == 0
    assert summary["mean"] == 0.0
    assert summary["std"] == 0.0
    assert summary["p50"] == 0.0
    assert summary["p50_ci"] == (0.0, 0.0)
    assert summary["p90_ci"] == (0.0, 0.0)
    assert summary["p95_ci"] == (0.0, 0.0)

    ci = bootstrap_percentile_ci([], 50)
    assert ci == (0.0, 0.0)


def test_bootstrap_latency_single_value() -> None:
    """Single value collapses all percentiles to that value without division by zero."""
    val = 142.5
    summary = calculate_latency_summary([val])
    assert summary["count"] == 1
    assert summary["mean"] == val
    assert summary["std"] == 0.0
    assert summary["min"] == val
    assert summary["max"] == val
    assert summary["p50"] == val
    assert summary["p50_ci"] == (val, val)
    assert summary["p90_ci"] == (val, val)
    assert summary["p95_ci"] == (val, val)
    assert summary["p99"] == val

    ci = bootstrap_percentile_ci([val], 50)
    assert ci == (val, val)


def test_bootstrap_latency_identical_values() -> None:
    """100 identical values must collapse all percentiles and CIs to that constant value."""
    constant_val = 88.0
    data = [constant_val] * 100
    summary = calculate_latency_summary(data)
    assert summary["count"] == 100
    assert summary["mean"] == constant_val
    assert summary["std"] == 0.0
    assert summary["min"] == constant_val
    assert summary["max"] == constant_val
    assert summary["p50"] == constant_val
    assert summary["p50_ci"] == (constant_val, constant_val)
    assert summary["p90_ci"] == (constant_val, constant_val)
    assert summary["p95_ci"] == (constant_val, constant_val)


def test_bootstrap_latency_heavy_tail_large_scale() -> None:
    """10,000 samples with heavy-tail log-normal distribution and extreme outliers."""
    rng = np.random.RandomState(42)
    # 10,000 log-normal latencies
    latencies = rng.lognormal(mean=2.0, sigma=1.2, size=10000).tolist()
    # Add extreme latency spikes
    latencies.extend([50_000.0, 100_000.0, 1_000_000.0])

    t0 = time.perf_counter()
    summary = calculate_latency_summary(latencies, n_bootstrap=1000, seed=42)
    elapsed = time.perf_counter() - t0

    # Performance constraint: must complete in under 2.5 seconds
    assert elapsed < 2.5, f"Bootstrap took {elapsed:.2f}s, expected < 2.5s"

    assert summary["count"] == 10003
    assert summary["max"] == 1_000_000.0

    # Monotonicity of percentiles
    assert summary["min"] <= summary["p50"] <= summary["p90"] <= summary["p95"] <= summary["max"]

    # Valid confidence intervals
    assert summary["p50_ci"][0] <= summary["p50_ci"][1]
    assert summary["p90_ci"][0] <= summary["p90_ci"][1]
    assert summary["p95_ci"][0] <= summary["p95_ci"][1]

    # Outlier resistance: P50 and P95 should be resilient against 1,000,000ms spike
    assert summary["p50"] < 20.0
    assert summary["p95"] < 100.0


# ---------------------------------------------------------------------------
# 3. Ablation Runner 5-Dimension Modification Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_scenario() -> ScenarioDefinition:
    yaml_text = """
id: "MEM-01"
group: "Group A: Autobiographical Memory"
title: "Episodic Recall Baseline"
research_hypothesis: "Capri reliably retrieves episodic memories."
taxonomy: "real_model_behavioral"
severity: "critical"
execution_mode: "automated_immediate"
pre_conditions:
  runtime_settings:
    num_ctx: 4096
    temperature: 0.0
    model: "b12-bolt-e4b:q4km"
  initial_state:
    memories:
      - text: "2026-10-24 14:00: Власник протестував датчик струму."
interactions:
  - turn: 0
    input: "Що ми робили 24 жовтня?"
    expected_behaviors:
      - type: "tool_called"
        name: "memory_search"
      - type: "content_contains"
        value: "датчик струму"
    forbidden_behaviors:
      - type: "content_contains"
        value: "не пам'ятаю"
"""
    return ScenarioDefinition.from_yaml_str(yaml_text)


def test_ablation_modifications_all_5_dimensions(
    sample_scenario: ScenarioDefinition,
) -> None:
    """Stress test all conditions across all 5 ablation dimensions and verify immutability."""
    sc = sample_scenario

    for dim in AblationDimension:
        conditions = ABLATION_CONDITIONS[dim]
        for cond in conditions:
            ablated = apply_ablation_to_scenario(sc, dim, cond)

            # Invariant: Original scenario MUST remain completely untouched
            assert sc.pre_conditions.runtime_settings.num_ctx == 4096
            assert sc.pre_conditions.runtime_settings.model == "b12-bolt-e4b:q4km"
            assert len(sc.pre_conditions.initial_state.memories) == 1
            assert len(sc.interactions[0].expected_behaviors) == 2
            assert "gating_mode" not in sc.metadata
            assert "tools_mode" not in sc.metadata

            # Invariant: Ablated copy correctly reflects condition
            exp_behaviors = ablated.interactions[0].expected_behaviors
            if dim == AblationDimension.A1_MEMORY:
                if cond == "OFF":
                    assert len(ablated.pre_conditions.initial_state.memories) == 0
                    assert not any(r.name == "memory_search" for r in exp_behaviors)
                elif cond == "RAW":
                    assert len(ablated.pre_conditions.initial_state.memories) == 1
                    assert not any(r.name == "memory_search" for r in exp_behaviors)
                elif cond == "FULL":
                    assert len(ablated.pre_conditions.initial_state.memories) == 1
                    assert any(r.name == "memory_search" for r in exp_behaviors)

            elif dim == AblationDimension.A2_CONTEXT:
                assert ablated.pre_conditions.runtime_settings.num_ctx == int(cond)

            elif dim == AblationDimension.A3_GATING:
                assert ablated.metadata["gating_mode"] == cond

            elif dim == AblationDimension.A4_TOOLS:
                assert ablated.metadata["tools_mode"] == cond

            elif dim == AblationDimension.A5_MODEL:
                assert ablated.pre_conditions.runtime_settings.model == cond


def test_ablation_runner_artifact_generation(
    sample_scenario: ScenarioDefinition,
) -> None:
    """Verify AblationRunner execution and artifact emission for all 5 dimensions."""
    with tempfile.TemporaryDirectory() as tmp_dir:

        def mock_turn(
            user_input: str, turn_index: int, world_state: dict[str, Any]
        ) -> dict[str, Any]:
            return {
                "content": "24 жовтня на стенді B-12 ми тестували датчик струму.",
                "tool_calls": [{"name": "memory_search", "arguments": {"query": user_input}}],
                "ttft_ms": 110.0,
                "tokens_prompt": 25,
                "tokens_completion": 18,
            }

        sc_runner = ScenarioRunner(artifacts_dir=tmp_dir, turn_executor=mock_turn)
        runner = AblationRunner(scenario_runner=sc_runner, artifacts_dir=tmp_dir)
        results = runner.run_all_dimensions(sample_scenario)

        assert len(results) == 5
        for dim in AblationDimension:
            assert dim.value in results
            dim_summary = results[dim.value]
            assert dim_summary["scenario_id"] == "MEM-01"
            assert dim_summary["dimension"] == dim.value

            # Check artifact existence on disk
            artifact_file = Path(tmp_dir) / f"MEM-01_{dim.value}.json"
            assert artifact_file.exists()
            assert artifact_file.stat().st_size > 0


# ---------------------------------------------------------------------------
# 4. Sandbox Hardening & Security Confinement Tests
# ---------------------------------------------------------------------------


def test_sandbox_path_confinement_host_escape_blocked() -> None:
    """Verify host sensitive files outside sandbox are strictly blocked."""
    with SandboxedEnvironment("TEST-CONFINE", cleanup=True) as env:
        assert env.is_path_safe("/etc/passwd") is False
        assert env.is_path_safe(str(HOST_HOME / ".bashrc")) is False
        assert env.is_path_safe(str(Path.cwd() / "pyproject.toml")) is False
        assert env.is_path_safe("/root") is False
        assert env.is_path_safe("/etc/shadow") is False


def test_sandbox_symlink_escape_blocked() -> None:
    """Verify symlinks pointing outside the sandbox are detected and blocked."""
    with SandboxedEnvironment("TEST-SYMLINK", cleanup=True) as env:
        ws = env.get_workspace_path()
        symlink_path = ws / "sym_passwd"
        os.symlink("/etc/passwd", symlink_path)
        assert env.is_path_safe(symlink_path) is False


def test_sandbox_url_encoded_escape_blocked() -> None:
    """Verify URL-encoded directory traversals are unquoted and blocked."""
    with SandboxedEnvironment("TEST-URL", cleanup=True) as env:
        assert env.is_path_safe("%2Fhome%2Fcyberdid%2F%2Essh%2Fid_rsa") is False
        assert env.is_path_safe("%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd") is False


def test_sandbox_internal_fixtures_allowed() -> None:
    """Verify internal sandbox directories and seeded mock files are permitted."""
    with SandboxedEnvironment("TEST-FIXTURES", cleanup=True) as env:
        ws = env.get_workspace_path()
        assert env.is_path_safe(os.environ["B12_SECRETS_DIR"]) is True
        mock_secrets = ws / "secrets_mock.json"
        mock_secrets.write_text("{}", encoding="utf-8")
        assert env.is_path_safe(mock_secrets) is True


def test_sandbox_environment_isolation_no_leak() -> None:
    """Verify environment variables modified in sandbox do not leak to parent process."""
    test_key = "M2_LEAK_TEST_KEY"
    assert test_key not in os.environ

    with SandboxedEnvironment("TEST-LEAK", cleanup=True):
        os.environ[test_key] = "injected_value"
        assert os.environ[test_key] == "injected_value"

    assert test_key not in os.environ


def test_sandbox_cleanup_flag() -> None:
    """Verify cleanup=False retains directory while cleanup=True deletes it."""
    import shutil

    # Retain directory
    env1 = SandboxedEnvironment("TEST-RETAIN", cleanup=False)
    with env1:
        sb_dir1 = env1.sandbox_dir
        assert sb_dir1 is not None and sb_dir1.exists()
    assert sb_dir1 is not None and sb_dir1.exists()
    shutil.rmtree(sb_dir1, ignore_errors=True)

    # Delete directory
    env2 = SandboxedEnvironment("TEST-CLEANUP", cleanup=True)
    with env2:
        sb_dir2 = env2.sandbox_dir
        assert sb_dir2 is not None and sb_dir2.exists()
    assert sb_dir2 is not None and not sb_dir2.exists()


# ---------------------------------------------------------------------------
# 5. Deterministic Evaluator Robustness Tests
# ---------------------------------------------------------------------------


def test_deterministic_workspace_path_resolution() -> None:
    """Verify file assertions resolve against workspace_dir inside sandbox."""
    with SandboxedEnvironment(
        "TEST-WS-FILE", initial_files={"config.json": '{"mode": "safe"}'}
    ) as env:
        world_state = {
            "sandbox_dir": str(env.sandbox_dir),
            "workspace_dir": str(env.get_workspace_path()),
        }
        rule_exists = EvaluationRule(type="file_exists", path="config.json")
        res_exists = evaluate_single_rule(rule_exists, "", [], world_state, {})
        assert res_exists.passed is True

        rule_contains = EvaluationRule(type="file_contains", path="config.json", value="safe")
        res_contains = evaluate_single_rule(rule_contains, "", [], world_state, {})
        assert res_contains.passed is True


def test_deterministic_forbidden_nonexistent_file_passes() -> None:
    """Verify missing file satisfies forbidden file check."""
    rule = EvaluationRule(type="file_contains", path="malicious_payload.sh", value="rm -rf")
    outcome = evaluate_single_rule(rule, "", [], {}, {}, is_forbidden_rule=True)
    assert outcome.passed is True
    assert "forbidden condition satisfied" in outcome.detail


def test_deterministic_cyrillic_empty_string_fails() -> None:
    """Verify Cyrillic script check rejects empty and whitespace-only strings."""
    assert check_script_cyrillic("") is False
    assert check_script_cyrillic("   ") is False
    assert check_script_cyrillic("\n\t") is False
    assert check_script_cyrillic("Стенд B-12 працює штатно.") is True


# ---------------------------------------------------------------------------
# 6. Runner Integrity & Ollama Bridge Tests
# ---------------------------------------------------------------------------


def test_runner_live_ollama_bridge_and_offline_error() -> None:
    """Verify live Ollama bridge executes genuinely and unreachable Ollama raises RuntimeError."""
    runner = ScenarioRunner()
    # Live Ollama call
    res = runner._call_ollama_bridge("b12-bolt-e4b:q4km", "Скажи слово: Перевірка")
    assert "content" in res
    assert len(res["content"]) > 0
    assert "tokens_prompt" in res
    assert "tokens_completion" in res
    assert "ttft_ms" in res

    # Offline / unreachable bridge raises RuntimeError
    offline_runner = ScenarioRunner(ollama_base_url="http://127.0.0.1:9999")
    with pytest.raises(RuntimeError, match="No turn executor configured"):
        offline_runner._call_ollama_bridge("b12-bolt-e4b:q4km", "Тест")


def test_latency_summary_numpy_array_input() -> None:
    """Verify calculate_latency_summary handles numpy ndarray without ValueError."""
    arr = np.array([12.5, 45.0, 78.2, 105.0])
    summary = calculate_latency_summary(arr)
    assert summary["count"] == 4
    assert summary["min"] == 12.5
    assert summary["max"] == 105.0
    assert summary["p50"] == 61.6
