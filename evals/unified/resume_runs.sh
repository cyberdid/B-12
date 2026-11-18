#!/usr/bin/env bash
# (Re)start every U2/U3 run of 18.11.2026 where it stopped. Safe to run repeatedly:
# finished records are kept, running drivers and bridges are left alone.
#   evals/unified/resume_runs.sh            # start whatever is not running
#   evals/unified/resume_runs.sh --status   # only print progress
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
A=evals/capri_comprehensive/artifacts
SET=evals/unified/scenario_sets/u2-u3-locked-v2.json
CLOUD="--model-timeout 230 --num-ctx 200000 --output-tokens 16384"
LOGDIR="${TMPDIR:-/tmp}/b12-bridges"; mkdir -p "$LOGDIR"
# name | out dir | repeats | arm | bridge port ("" = local Bolt)
RUNS=(
  "A0|$A/unified-locked-pilot-2026-11-18|3|A0|"
  "A1|$A/unified-locked-u2-A1-2026-11-18|3|A1|"
  "E1|$A/unified-locked-u2-E1-2026-11-18|3|E1|"
  "D|$A/unified-locked-u2-D-2026-11-18|3|D|"
  "haiku|$A/unified-locked-haiku-2026-11-18|1|A0|11500"
  "luna|$A/unified-locked-codex-2026-11-18|1|A0|11501"
)
declare -A BRIDGE=([11500]="claude claude-haiku-5-5" [11501]="codex gpt-6-luna")

expected() { python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["scenarios"]))' "$SET"; }
count() { find "$1" -name '*.json' -path '*/r*/*' 2>/dev/null | wc -l; }
running() { pgrep -f "run_locked_pilot.sh $SET $1 " >/dev/null; }

for spec in "${RUNS[@]}"; do
  IFS='|' read -r name out reps arm port <<<"$spec"
  total=$(( $(expected) * reps )); done_n=$(count "$out")
  state="stopped"; running "$out" && state="running"; [ "$done_n" -ge "$total" ] && state="complete"
  printf '%-6s %4s/%-4s %s\n' "$name" "$done_n" "$total" "$state"
  [ "${1:-}" = "--status" ] && continue
  [ "$state" != "stopped" ] && continue
  env_args=()
  if [ -n "$port" ]; then
    if ! curl -sf "http://127.0.0.1:$port/api/version" >/dev/null; then
      read -r backend model <<<"${BRIDGE[$port]}"
      setsid nohup .venv/bin/python -m evals.subscription_bridge --backend "$backend" \
        --model "$model" --port "$port" >"$LOGDIR/$name.log" 2>&1 </dev/null &
      sleep 3
    fi
    env_args=(B12_EVAL_OLLAMA_URL="http://127.0.0.1:$port" EXTRA_RUNNER_ARGS="$CLOUD" NO_GPU_WAIT=1)
  fi
  env "${env_args[@]}" setsid nohup evals/unified/run_locked_pilot.sh "$SET" "$out" "$reps" "$arm" \
    >/dev/null 2>&1 </dev/null &
  echo "  -> started $name"
done
