"""Systematic Ablation Study Runner for Capri Comprehensive Evaluation.

Implements the 5 mandatory experimental ablation designs:
1. Ablation A1: Memory Subsystem (FULL vs RAW vs OFF)
2. Ablation A2: Context Window Scaling (2048 vs 4096 vs 8192)
3. Ablation A3: Policy Gating (DETERMINISTIC vs PROMPT_ONLY)
4. Ablation A4: Tool Schema Specification (FULL vs STRICT vs MINIMAL)
5. Ablation A5: Model Family & Architecture (bolt-e4b vs gemma4:12b vs qwen)
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from evals.capri_comprehensive.evaluators.schema import (
    ExecutionReport,
    ScenarioDefinition,
)
from evals.capri_comprehensive.runners.runner import ScenarioRunner

logger = logging.getLogger("evals.ablation")


class AblationDimension(StrEnum):
    A1_MEMORY = "A1_MEMORY"
    A2_CONTEXT = "A2_CONTEXT"
    A3_GATING = "A3_GATING"
    A4_TOOLS = "A4_TOOLS"
    A5_MODEL = "A5_MODEL"


ABLATION_CONDITIONS = {
    AblationDimension.A1_MEMORY: ["FULL", "RAW", "OFF"],
    AblationDimension.A2_CONTEXT: ["2048", "4096", "8192"],
    AblationDimension.A3_GATING: ["DETERMINISTIC", "PROMPT_ONLY"],
    AblationDimension.A4_TOOLS: ["FULL", "STRICT", "MINIMAL"],
    AblationDimension.A5_MODEL: ["b12-bolt-e4b:q4km", "gemma4:12b", "qwen3.5:27b-q4_K_M"],
}


def apply_ablation_to_scenario(
    scenario: ScenarioDefinition,
    dimension: AblationDimension,
    condition: str,
) -> ScenarioDefinition:
    """Create an ablated copy of ScenarioDefinition under the specified condition."""
    ablated = copy.deepcopy(scenario)

    if dimension == AblationDimension.A1_MEMORY:
        if condition == "OFF":
            ablated.pre_conditions.initial_state.memories = []
            # Forbid memory tools
            for turn in ablated.interactions:
                turn.expected_behaviors = [
                    r for r in turn.expected_behaviors if r.name != "memory_search"
                ]
        elif condition == "RAW":
            # Keep memories but strip external search expectation
            for turn in ablated.interactions:
                turn.expected_behaviors = [
                    r for r in turn.expected_behaviors if r.name != "memory_search"
                ]

    elif dimension == AblationDimension.A2_CONTEXT:
        num_ctx = int(condition)
        ablated.pre_conditions.runtime_settings.num_ctx = num_ctx

    elif dimension == AblationDimension.A3_GATING:
        ablated.metadata["gating_mode"] = condition  # DETERMINISTIC vs PROMPT_ONLY

    elif dimension == AblationDimension.A4_TOOLS:
        ablated.metadata["tools_mode"] = condition  # FULL, STRICT, MINIMAL

    elif dimension == AblationDimension.A5_MODEL:
        ablated.pre_conditions.runtime_settings.model = condition

    return ablated


class AblationRunner:
    """Orchestrates systematic ablation trials across scenarios and conditions."""

    def __init__(
        self,
        scenario_runner: ScenarioRunner | None = None,
        artifacts_dir: str | Path | None = None,
    ):
        base_dir = Path(__file__).resolve().parent.parent
        self.artifacts_dir = (
            Path(artifacts_dir) if artifacts_dir else base_dir / "artifacts" / "ablations"
        )
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.scenario_runner = scenario_runner or ScenarioRunner(artifacts_dir=self.artifacts_dir)

    def run_ablation(
        self,
        scenario: ScenarioDefinition,
        dimension: AblationDimension,
        conditions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute scenario under all conditions of a specific ablation dimension."""
        cond_list = conditions or ABLATION_CONDITIONS[dimension]
        reports_by_condition: dict[str, ExecutionReport] = {}

        print(f"\nRunning Ablation {dimension.value} on {scenario.id} ({scenario.title})")
        for cond in cond_list:
            ablated_sc = apply_ablation_to_scenario(scenario, dimension, cond)
            rep = self.scenario_runner.run(
                ablated_sc, ablation_condition=f"{dimension.value}:{cond}"
            )
            reports_by_condition[cond] = rep
            status_text = "PASS" if rep.all_passed else rep.status.value
            p50 = float(np.median(rep.latencies_ms)) if rep.latencies_ms else 0.0
            print(f"  Condition: {cond:<18} -> {status_text:<12} | Latency: {p50:.1f}ms")

        # Compile comparison summary
        summary = {
            "scenario_id": scenario.id,
            "dimension": dimension.value,
            "conditions": cond_list,
            "results": {
                cond: {
                    "status": rep.status.value,
                    "passed": rep.all_passed,
                    "raw_score": rep.raw_score,
                    "p50_latency_ms": (
                        float(np.median(rep.latencies_ms)) if rep.latencies_ms else 0.0
                    ),
                    "tokens_prompt": rep.tokens_prompt,
                    "tokens_completion": rep.tokens_completion,
                }
                for cond, rep in reports_by_condition.items()
            },
        }

        # Save ablation artifact
        summary_path = self.artifacts_dir / f"{scenario.id}_{dimension.value}.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        return summary

    def run_all_dimensions(
        self,
        scenario: ScenarioDefinition,
    ) -> dict[str, Any]:
        """Run all 5 ablation dimensions for a given scenario."""
        all_res = {}
        for dim in AblationDimension:
            all_res[dim.value] = self.run_ablation(scenario, dim)
        return all_res


def main() -> None:
    parser = argparse.ArgumentParser(description="Capri Systematic Ablation Runner")
    parser.add_argument("scenario_path", help="Path to scenario YAML file")
    parser.add_argument(
        "--dimension", "-d", choices=[d.value for d in AblationDimension], default=None
    )
    args = parser.parse_args()

    sc = ScenarioDefinition.from_yaml_file(args.scenario_path)
    runner = AblationRunner()

    if args.dimension:
        dim = AblationDimension(args.dimension)
        runner.run_ablation(sc, dim)
    else:
        runner.run_all_dimensions(sc)


if __name__ == "__main__":
    main()
