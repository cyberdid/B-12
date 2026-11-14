#!/usr/bin/env bash
# N full runs of the main suite (pinned Bolt / swappable gemma4:12b); raw batches are kept
# in reports/repeats/runK/. A run starts only when no other program holds GPU memory, and
# a watcher logs any foreign GPU use during it (gpu_contention.log), so a run disturbed
# by, say, a game is known. Usage: repeat_suite.sh [N=3] [FIRST=1]
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO"
R=evals/capri_comprehensive/reports
N="${1:-3}"; FIRST="${2:-1}"
foreign_mb() {
  nvidia-smi --query-compute-apps=process_name,used_memory --format=csv,noheader,nounits 2>/dev/null \
    | grep -v -E 'ollama|llama-server' | awk -F', ' '{s+=$2} END {print s+0}'
}
for n in $(seq "$FIRST" "$N"); do
  until [ "$(foreign_mb)" -lt 200 ]; do sleep 60; done
  echo "== run $n start $(date -Is) (GPU free)"
  mkdir -p "$R/repeats/run$n"
  ( while true; do mb=$(foreign_mb); [ "$mb" -ge 200 ] && echo "$(date -Is) foreign_gpu_mb=$mb"; sleep 60; done ) \
    > "$R/repeats/run$n/gpu_contention.log" &
  W=$!
  evals/capri_comprehensive/runners/sandboxed_suite.sh 2>&1 | grep --line-buffered -E '^\[|counts|Traceback|Error'
  echo "== run $n live checks $(date -Is)"
  .venv/bin/python -m evals.capri_comprehensive.runners.run_live_suite 2>&1 \
    | grep --line-buffered -E 'PASS|FAIL|counts|Traceback|Error'
  kill "$W"
  cp "$R/batch_summary.json" "$R/STATISTICAL_SUMMARY.md" "$R/repeats/run$n/"
  echo "== run $n saved $(date -Is); contention lines: $(wc -l < "$R/repeats/run$n/gpu_contention.log")"
done
echo "== done $(date -Is)"
