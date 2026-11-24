#!/usr/bin/env bash
# Queue the standing gemma regression set (regression-gemma-v1) for one runtime commit.
#   ops/remote/queue_regression.sh <commit> [repeats=1]
# Pins the eval checkout ($B12_REPO, default .worktrees/eval-run) to <commit> — only when no other
# queued job is still running there — and appends one job to $B12_QUEUE/jobs.tsv. The running
# orchestrator picks it up. Report afterwards:
#   .venv/bin/python -m evals.unified.regression_report <out_dir> --baseline <previous out_dir>
set -euo pipefail
COMMIT="${1:?commit}"; REPEATS="${2:-1}"
REPO="${B12_REPO:-$HOME/Projects/B-12/.worktrees/eval-run}"; Q="${B12_QUEUE:-$HOME/b12-queue-local}"
touch "$Q/jobs.tsv"
while IFS=$'\t' read -r name manifest out _rest; do
  [ -z "${name:-}" ] || [ "${name:0:1}" = "#" ] && continue
  if ! grep -qs DONE "$REPO/$out/pilot.log"; then
    echo "job $name is not done yet; queue the regression after it" >&2; exit 2
  fi
done <"$Q/jobs.tsv"
git -C "$REPO" checkout -q --detach "$COMMIT"
SHORT="$(git -C "$REPO" rev-parse --short HEAD)"
OUT="evals/capri_comprehensive/artifacts/regression-gemma-v1-$SHORT-$(date +%Y-%m-%d)"
# Deployed defaults plus the two background reviews the set measures (M94, M115, M118).
FLAGS="--model-timeout 300 --memory-temporal --goals-in-context --recall-as-of"
FLAGS="$FLAGS --recall-conversations --memory-ranking --standing-intents --skills"
FLAGS="$FLAGS --memory-review --skill-review"
printf 'regression-%s\tevals/unified/scenario_sets/regression-gemma-v1.json\t%s\t%s\tA0\tgemma4:12b\t%s\n' \
  "$SHORT" "$OUT" "$REPEATS" "$FLAGS" >>"$Q/jobs.tsv"
echo "$OUT"
