"""Run inside the unified bubblewrap worker (B12_EVAL_ENTRY=unified-probe): report what a
model's tools could see. Exits non-zero if answer material or host logs are visible."""

import json
import os
import sys
from pathlib import Path


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    manifest, scenario = Path(argv[0]), argv[1]
    repo = Path.cwd()
    rows = json.loads(manifest.read_text(encoding="utf-8"))["scenarios"]
    row = next(r for r in rows if r["scenario_id"] == scenario)
    report = {
        "own_input_visible": (repo / row["input_fixture"]).is_file(),
        "own_setup_visible": (repo / row["setup_fixture"]).is_file(),
        "own_oracle_visible": (repo / row["oracle_fixture"]).exists(),
        "other_fixtures": sum(1 for _ in (repo / "evals/unified/draft_fixtures").rglob("*.json")),
        "reports_entries": len(os.listdir(repo / "reports")) if (repo / "reports").is_dir() else 0,
        "draft_sources_entries": len(os.listdir(repo / "evals/unified/draft_sources"))
        if (repo / "evals/unified/draft_sources").is_dir()
        else 0,
        "artifacts_entries": len(os.listdir(repo / "evals/capri_comprehensive/artifacts")),
        "var_log_entries": len(os.listdir("/var/log")) if os.path.isdir("/var/log") else 0,
    }
    print(json.dumps(report))
    leaked = (
        report["own_oracle_visible"]
        or report["other_fixtures"] > 2
        or report["reports_entries"]
        or report["draft_sources_entries"]
        or report["var_log_entries"]
        or report["artifacts_entries"] > 1
    )
    sys.exit(1 if leaked else 0)


if __name__ == "__main__":
    main()
