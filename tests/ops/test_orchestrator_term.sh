#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
ORCH_PID=""
STUB_PID=""
CHILD_PID=""

cleanup() {
  for pid in "$CHILD_PID" "$STUB_PID" "$ORCH_PID"; do
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done
  rm -rf "$TMP"
}
trap cleanup EXIT

run_signal_case() {
  local sig="$1"
  local case_dir="$TMP/$sig"
  local home_dir="$case_dir/home"
  local repo_dir="$case_dir/repo"
  local queue_dir="$case_dir/queue"
  local assets_dir="$case_dir/assets"
  mkdir -p "$home_dir" "$repo_dir/evals/unified" "$queue_dir" "$assets_dir"

  cat >"$repo_dir/evals/unified/run_locked_pilot.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
q_dir="${B12_TEST_QUEUE_DIR:?}"
sleep 60 &
child=$!
printf '%s\n' "$$" >"$q_dir/stub.pid.tmp"
mv "$q_dir/stub.pid.tmp" "$q_dir/stub.pid"
printf '%s\n' "$child" >"$q_dir/child.pid.tmp"
mv "$q_dir/child.pid.tmp" "$q_dir/child.pid"
wait "$child"
EOF
  chmod +x "$repo_dir/evals/unified/run_locked_pilot.sh"

  printf 'stub-job\tmanifest.json\tout/stub\t1\tA0\tgemma4:12b\t--memory-temporal\n' >"$queue_dir/jobs.tsv"

  HOME="$home_dir" \
  B12_REPO="$repo_dir" \
  B12_QUEUE="$queue_dir" \
  B12_ASSETS="$assets_dir" \
  B12_ORCH_DRYRUN=1 \
  B12_TEST_QUEUE_DIR="$queue_dir" \
    bash "$ROOT/ops/remote/orchestrator.sh" &
  ORCH_PID=$!

  for _ in $(seq 50); do
    if [ -s "$queue_dir/stub.pid" ] && [ -s "$queue_dir/child.pid" ]; then
      break
    fi
    sleep 0.1
  done

  if [ ! -s "$queue_dir/stub.pid" ] || [ ! -s "$queue_dir/child.pid" ]; then
    echo "FAIL ($sig): stub driver did not start within 5s" >&2
    cat "$queue_dir/orchestrator.log" >&2 || true
    return 1
  fi

  STUB_PID="$(cat "$queue_dir/stub.pid")"
  CHILD_PID="$(cat "$queue_dir/child.pid")"

  if ! kill -0 "$STUB_PID" 2>/dev/null || ! kill -0 "$CHILD_PID" 2>/dev/null; then
    echo "FAIL ($sig): stub driver or child is not running before $sig" >&2
    return 1
  fi

  kill "-$sig" "$ORCH_PID"

  for _ in $(seq 50); do
    local orch_alive=0 stub_alive=0 child_alive=0
    kill -0 "$ORCH_PID" 2>/dev/null && orch_alive=1 || true
    kill -0 "$STUB_PID" 2>/dev/null && stub_alive=1 || true
    kill -0 "$CHILD_PID" 2>/dev/null && child_alive=1 || true
    if [ "$orch_alive" -eq 0 ] && [ "$stub_alive" -eq 0 ] && [ "$child_alive" -eq 0 ]; then
      ORCH_PID=""
      STUB_PID=""
      CHILD_PID=""
      return 0
    fi
    sleep 0.1
  done

  echo "FAIL ($sig): processes survived $sig past 5s (orch=$ORCH_PID stub=$STUB_PID child=$CHILD_PID)" >&2
  cat "$queue_dir/orchestrator.log" >&2 || true
  return 1
}

run_signal_case TERM
echo "PASS: orchestrator and stub driver process group exited on TERM"
