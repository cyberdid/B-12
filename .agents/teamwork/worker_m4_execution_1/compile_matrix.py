"""Helper script to compile the 15-column CAPRI_SCENARIO_MATRIX.csv and statistical summaries."""

from pathlib import Path
import json
from evals.capri_comprehensive.evaluators.schema import ExecutionReport, ScenarioDefinition
from evals.capri_comprehensive.runners.suite_runner import SuiteRunner
from evals.capri_comprehensive.statistical_analysis.aggregator import EvaluationAggregator

def main():
    root = Path("/home/cyberdid/Projects/B-12")
    reports_dir = root / "evals" / "capri_comprehensive" / "reports"
    artifacts_dir = root / "evals" / "capri_comprehensive" / "artifacts"
    ablations_dir = artifacts_dir / "ablations"

    suite = SuiteRunner()
    sc_paths = suite.discover_scenarios()
    sc_map = {p.stem: ScenarioDefinition.from_yaml_file(p) for p in sc_paths}

    batch_json = reports_dir / "batch_summary.json"
    with open(batch_json, encoding="utf-8") as f:
        data = json.load(f)
    reports = [ExecutionReport.model_validate(r) for r in data["reports"]]

    # Load ablation sensitivities from ablations artifacts if available
    ablation_sens = {}
    for ab_file in ablations_dir.glob("*.json"):
        try:
            with open(ab_file, encoding="utf-8") as f:
                ab_data = json.load(f)
            sid = ab_data.get("scenario_id")
            dim = ab_data.get("dimension")
            res = ab_data.get("results", {})
            # Determine sensitivity label
            passes = [cond_res.get("passed", False) for cond_res in res.values()]
            if all(passes):
                label = f"{dim}_INVARIANT"
            elif any(passes):
                label = f"{dim}_HIGH"
            else:
                label = f"{dim}_MODERATE"
            if sid:
                ablation_sens[sid] = label
        except Exception:
            pass

    agg = EvaluationAggregator(reports)
    matrix_csv = reports_dir / "CAPRI_SCENARIO_MATRIX.csv"
    agg.write_scenario_matrix_csv(matrix_csv, sc_map, ablation_sensitivities=ablation_sens)
    print(f"Generated {matrix_csv} ({len(reports)} rows x 15 columns)")

    # Also generate markdown statistical summary
    summary_md = reports_dir / "STATISTICAL_SUMMARY.md"
    agg.generate_markdown_summary(summary_md)
    print(f"Generated {summary_md}")

if __name__ == "__main__":
    main()
