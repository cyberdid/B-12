#!/usr/bin/env bash
# Build a blind judge sheet for one run and launch two judges per part, in the background.
#   evals/unified/launch_judges.sh <name> <run_dir> <judge_a> <judge_b>
# judges: codex | gemini | opus. Outputs: reports/unified/semantic-judge-<name>/sheet.json and
# reports/unified/.judge-work-<name>/<judge>-<n>/out.json (git-excluded work dir).
set -euo pipefail
NAME="$1"; RUN="$2"; shift 2
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$REPO"
D="$REPO/reports/unified/semantic-judge-$NAME"; W="$REPO/reports/unified/.judge-work-$NAME"
mkdir -p "$D" "$W"
cp reports/unified/semantic-judge-locked-pilot-2026-11-18/rubric.md reports/unified/semantic-judge-locked-pilot-2026-11-18/schema.json "$D/"
.venv/bin/python - "$D" "$W" "$RUN" <<'PY'
import json, sys
from pathlib import Path
from evals.unified.judge_sheet import build_pilot
D, W, run = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sheet = build_pilot("evals/unified/scenario_sets/u2-u3-locked-v2.json", run, Path.cwd())
(D / "sheet.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
items = [{k: v for k, v in s.items() if k != "members"} for s in sheet]
rubric = (D / "rubric.md").read_text(); parts, cur = [], []
for item in items:
    cur.append(item)
    if len(json.dumps(cur, ensure_ascii=False)) > 90000:
        parts.append(cur[:-1]); cur = [item]
parts.append(cur)
for n, part in enumerate(parts):
    (W / f"prompt_{n}.txt").write_text(rubric + "\n\nITEMS (JSON):\n" + json.dumps(part, ensure_ascii=False, indent=1))
print(len(sheet), "items", sum(len(s["criteria"]) for s in sheet), "criteria", len(parts), "parts")
PY
for f in "$W"/prompt_*.txt; do
  n=$(basename "$f" .txt | cut -d_ -f2)
  for judge in "$@"; do
    mkdir -p "$W/$judge-$n"
    case "$judge" in
      codex) (cd "$W/$judge-$n" && nohup codex exec -s read-only --ephemeral --skip-git-repo-check --output-schema "$D/schema.json" -o "$W/$judge-$n/out.json" "$(cat "$f")" >"$W/$judge-$n/run.log" 2>&1 &) ;;
      gemini) (cd "$W/$judge-$n" && nohup agy --mode plan --output-format json --json-schema "$D/schema.json" -p "$(cat "$f")" >"$W/$judge-$n/out.json" 2>"$W/$judge-$n/err.log" &) ;;
      opus) (cd "$W/$judge-$n" && nohup agy --model claude-opus-5-5-high --mode plan --output-format json --json-schema "$D/schema.json" -p "$(cat "$f")" >"$W/$judge-$n/out.json" 2>"$W/$judge-$n/err.log" &) ;;
      *) echo "unknown judge $judge" >&2; exit 2 ;;
    esac
  done
done
