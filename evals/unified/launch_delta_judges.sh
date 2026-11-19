#!/usr/bin/env bash
# Judge only the items of a run that are not in its previous sheet (records re-run since).
#   evals/unified/launch_delta_judges.sh <judge_dir_name> <run_dir> <judge_a> <judge_b>
# Writes sheet_v2.json (full, current) next to the old sheet.json, and the delta prompt to
# reports/unified/.judge-work-<name>-delta/; judges as in launch_judges.sh.
set -euo pipefail
NAME="$1"; RUN="$2"; shift 2
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$REPO"
D="$REPO/reports/unified/$NAME"; W="$REPO/reports/unified/.judge-work-$NAME-delta"
mkdir -p "$W"
.venv/bin/python - "$D" "$W" "$RUN" <<'PY'
import json, sys
from pathlib import Path
from evals.unified.judge_sheet import build_pilot
D, W, run = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
old = {s["item_id"] for s in json.loads((D / "sheet.json").read_text(encoding="utf-8"))}
sheet = build_pilot("evals/unified/scenario_sets/u2-u3-locked-v2.json", run, Path.cwd())
(D / "sheet_v2.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
new = [{k: v for k, v in s.items() if k != "members"} for s in sheet if s["item_id"] not in old]
(W / "prompt_0.txt").write_text((D / "rubric.md").read_text() + "\n\nITEMS (JSON):\n" + json.dumps(new, ensure_ascii=False, indent=1))
print(len(sheet), "items now,", len(new), "new to judge")
PY
for judge in "$@"; do
  mkdir -p "$W/$judge-0"; f="$W/prompt_0.txt"
  case "$judge" in
    codex) (cd "$W/$judge-0" && nohup codex exec -s read-only --ephemeral --skip-git-repo-check --output-schema "$D/schema.json" -o "$W/$judge-0/out.json" "$(cat "$f")" >"$W/$judge-0/run.log" 2>&1 &) ;;
    gemini) (cd "$W/$judge-0" && nohup agy --mode plan --output-format json --json-schema "$D/schema.json" -p "$(cat "$f")" >"$W/$judge-0/out.json" 2>"$W/$judge-0/err.log" &) ;;
    opus) (cd "$W/$judge-0" && nohup agy --model claude-opus-5-5-high --mode plan --output-format json --json-schema "$D/schema.json" -p "$(cat "$f")" >"$W/$judge-0/out.json" 2>"$W/$judge-0/err.log" &) ;;
  esac
done
