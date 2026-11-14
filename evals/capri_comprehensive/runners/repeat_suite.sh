#!/usr/bin/env bash
# N full runs of the main suite (pinned Bolt / swappable gemma4:12b); raw batches are kept
# in reports/repeats/runK/. A run starts only when no other program holds GPU memory, and
# a watcher logs any foreign GPU use during it (gpu_contention.log), so a run disturbed
# by, say, a game is known. Usage: repeat_suite.sh [N=3] [FIRST=1]
# With B12_EVAL_VARIANT=deployed-<model> (a model served elsewhere, see live_components)
# the variant's batch is kept under reports/repeats/<variant>/runK/; B12_REPEAT_NO_GPU_WAIT=1
# skips the local GPU wait when the model does not run on this machine.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO"
R=evals/capri_comprehensive/reports
N="${1:-3}"; FIRST="${2:-1}"
V="${B12_EVAL_VARIANT:-}"
BATCH="$R/batch_summary${V:+_$V}.json"
SUMMARY="$R/STATISTICAL_SUMMARY${V:+_${V^^}}.md"
OUT="$R/repeats${V:+/$V}"
foreign_mb() {
  nvidia-smi --query-compute-apps=process_name,used_memory --format=csv,noheader,nounits 2>/dev/null \
    | grep -v -E 'ollama|llama-server' | awk -F', ' '{s+=$2} END {print s+0}'
}
for n in $(seq "$FIRST" "$N"); do
  if [ "${B12_REPEAT_NO_GPU_WAIT:-}" != "1" ]; then
    until [ "$(foreign_mb)" -lt 200 ]; do sleep 60; done
  fi
  echo "== run $n start $(date -Is) (GPU free)"
  mkdir -p "$OUT/run$n"
  ( while true; do mb=$(foreign_mb); [ "$mb" -ge 200 ] && echo "$(date -Is) foreign_gpu_mb=$mb"; sleep 60; done ) \
    > "$OUT/run$n/gpu_contention.log" &
  W=$!
  evals/capri_comprehensive/runners/sandboxed_suite.sh 2>&1 | grep --line-buffered -E '^\[|counts|Traceback|Error'
  echo "== run $n live checks $(date -Is)"
  .venv/bin/python -m evals.capri_comprehensive.runners.run_live_suite 2>&1 \
    | grep --line-buffered -E 'PASS|FAIL|counts|Traceback|Error'
  kill "$W"
  cp "$BATCH" "$SUMMARY" "$OUT/run$n/"
  echo "== run $n saved $(date -Is); contention lines: $(wc -l < "$OUT/run$n/gpu_contention.log")"
done
echo "== done $(date -Is)"
