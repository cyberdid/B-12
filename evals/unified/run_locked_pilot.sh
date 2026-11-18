#!/usr/bin/env bash
# Run every scenario of a frozen U2/U3 set N times on the pinned model, one bubblewrap
# worker per scenario, waiting whenever a foreign process uses the GPU (the owner games on
# it). Raw records: <out>/rN/<scenario>.json; existing records are kept (resumable).
#
#   evals/unified/run_locked_pilot.sh <manifest> <out_dir> [repeats=3] [arm=A0]
# Cloud models via the subscription bridge: set B12_EVAL_OLLAMA_URL to the bridge,
# EXTRA_RUNNER_ARGS="--model-timeout 230 --num-ctx 200000 --output-tokens 16384" and
# NO_GPU_WAIT=1 (the bridge does not use the local GPU).
set -uo pipefail
MANIFEST="${1:?manifest}"
OUT="${2:?out dir}"
REPEATS="${3:-3}"
ARM="${4:-A0}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
mkdir -p "$OUT"
LOG="$OUT/pilot.log"
mapfile -t IDS < <(python3 -c 'import json,sys; [print(r["scenario_id"]) for r in json.load(open(sys.argv[1]))["scenarios"]]' "$MANIFEST")

read -r -a EXTRA <<<"${EXTRA_RUNNER_ARGS:-}"

gpu_busy() {
  [ "${NO_GPU_WAIT:-0}" = 1 ] && return 1
  # Any compute process other than Ollama's runner, or a graphics-heavy app, counts as busy.
  nvidia-smi --query-compute-apps=process_name --format=csv,noheader 2>/dev/null \
    | grep -v -E 'ollama|llama-server|steamwebhelper' | grep -q .
}

for r in $(seq 1 "$REPEATS"); do
  mkdir -p "$OUT/r$r"
  for id in "${IDS[@]}"; do
    [ -s "$OUT/r$r/$id.json" ] && continue
    while gpu_busy; do
      echo "$(date -Is) r$r $id waiting: foreign GPU process" >>"$LOG"
      sleep 60
    done
    start=$(date +%s)
    if B12_EVAL_ENTRY=unified-u2u3 timeout 900 \
        evals/capri_comprehensive/runners/sandboxed_suite.sh "$MANIFEST" "$id" "$OUT/r$r" --arm "$ARM" "${EXTRA[@]}" \
        >>"$LOG" 2>&1; then
      echo "$(date -Is) r$r $id ok $(( $(date +%s) - start ))s" >>"$LOG"
    else
      echo "$(date -Is) r$r $id ERROR exit=$?" >>"$LOG"
    fi
  done
done
echo "$(date -Is) DONE" >>"$LOG"
