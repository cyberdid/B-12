"""Verification script for tools_mode and gating_mode implementation."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition
from evals.capri_comprehensive.runners.ablation_runner import (
    AblationDimension,
    apply_ablation_to_scenario,
)

# Test scenario loading
sc_path = Path("evals/capri_comprehensive/scenarios/group_d_reasoning/RE-01.yaml")
sc = ScenarioDefinition.from_yaml_file(sc_path)

# Verify A4_TOOLS mutation
ablated_full = apply_ablation_to_scenario(sc, AblationDimension.A4_TOOLS, "FULL")
assert ablated_full.metadata["tools_mode"] == "FULL"

ablated_strict = apply_ablation_to_scenario(sc, AblationDimension.A4_TOOLS, "STRICT")
assert ablated_strict.metadata["tools_mode"] == "STRICT"

ablated_min = apply_ablation_to_scenario(sc, AblationDimension.A4_TOOLS, "MINIMAL")
assert ablated_min.metadata["tools_mode"] == "MINIMAL"

# Verify A3_GATING mutation
ablated_det = apply_ablation_to_scenario(sc, AblationDimension.A3_GATING, "DETERMINISTIC")
assert ablated_det.metadata["gating_mode"] == "DETERMINISTIC"

ablated_soft = apply_ablation_to_scenario(sc, AblationDimension.A3_GATING, "PROMPT_ONLY")
assert ablated_soft.metadata["gating_mode"] == "PROMPT_ONLY"

print("Ablation metadata mutations verified successfully!")
