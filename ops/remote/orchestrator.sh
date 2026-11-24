#!/usr/bin/env bash
# e2-micro orchestrator: keeps a Colab GPU session serving the model, runs the eval queue in the
# local bubblewrap sandbox, survives the owner's laptop being off, and stops Colab when idle.
#
# Queue: ~/b12-queue/jobs.tsv, one job per line (tab-separated):
#   name  manifest  out_dir  repeats  arm  model  extra_runner_args
# A job is done when <out_dir>/pilot.log contains DONE (run_locked_pilot.sh is resumable).
# A manifest field `cmd:<command>` runs that command instead (same model env and tunnel; its
# working dir is the repo); DONE is appended to <out_dir>/pilot.log when it exits 0.
# Log: ~/b12-queue/orchestrator.log. Run as a systemd service (ops/remote/b12-orchestrator.service).
set -uo pipefail
# Overridable so the same loop runs on the owner's laptop (CPU sandbox) as well as on a VM.
REPO="${B12_REPO:-$HOME/Projects/B-12}"; Q="${B12_QUEUE:-$HOME/b12-queue}"
ASSETS="${B12_ASSETS:-$HOME/b12-assets}"
SESSION=b12eval; SOCK_DIR="$HOME/b12-embed"; SOCK="$SOCK_DIR/embed.sock"
export PATH="$HOME/.local/bin:$PATH"
mkdir -p "$Q" "$SOCK_DIR"; touch "$Q/jobs.tsv"
log() { echo "$(date -Is) $*" >>"$Q/orchestrator.log"; }
DRIVER_PID=""
SLEEP_PID=""

cleanup() {
  trap - TERM INT
  if [ -n "${DRIVER_PID:-}" ]; then
    kill -TERM -- "-$DRIVER_PID" 2>/dev/null || true
    wait "$DRIVER_PID" 2>/dev/null || true
    DRIVER_PID=""
  fi
  if [ -n "${SLEEP_PID:-}" ]; then
    kill -TERM "$SLEEP_PID" 2>/dev/null || true
    wait "$SLEEP_PID" 2>/dev/null || true
    SLEEP_PID=""
  fi
  log "orchestrator stopped"
  exit 0
}
trap cleanup TERM INT

interruptible_sleep() {
  sleep "$1" &
  SLEEP_PID=$!
  wait "$SLEEP_PID" 2>/dev/null || true
  SLEEP_PID=""
}

pending_jobs() {
  while IFS=$'\t' read -r name manifest out repeats arm model extra; do
    [ -z "${name:-}" ] || [ "${name:0:1}" = "#" ] && continue
    grep -qs DONE "$REPO/$out/pilot.log" || printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$name" "$manifest" "$out" "$repeats" "$arm" "$model" "$extra"
  done <"$Q/jobs.tsv"
}

# `colab sessions` lists endpoints, not names; the name -> endpoint map is local to this host.
session_alive() {
  local endpoint
  endpoint="$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('~/.config/colab-cli/sessions.json'))).get('$SESSION', {}).get('endpoint', ''))" 2>/dev/null)"
  [ -n "$endpoint" ] && colab sessions 2>/dev/null | grep -q "$endpoint"
}
tunnel_ok() { curl -fs --max-time 10 http://127.0.0.1:11435/api/version >/dev/null; }

# Colab keeps its single SSH slot "busy" (HTTP 429) after an unclean disconnect, for hours
# (20.11.2026). The Jupyter kernel still works, so a stale sshd child is closed through it.
free_ssh_slot() {
  local fix; fix="$(mktemp)"
  printf '%s\n' 'import subprocess' \
    'subprocess.run("pkill -f \"sshd: root@\"", shell=True)' >"$fix"
  timeout 120 colab exec -s "$SESSION" -f "$fix" >/dev/null 2>&1; rm -f "$fix"; sleep 10
}

ssh_ready() {
  timeout 60 ssh -o ConnectTimeout=40 "$SESSION" true 2>/dev/null && return 0
  log "SSH refused (stale slot?): freeing it through the kernel"; free_ssh_slot
  timeout 60 ssh -o ConnectTimeout=40 "$SESSION" true 2>/dev/null
}

ensure_colab() {  # $1 = space-separated models
  [ "${B12_ORCH_DRYRUN:-0}" = "1" ] && return 0
  if ! session_alive; then
    ssh -O exit "$SESSION" >/dev/null 2>&1
    log "creating Colab session"; colab new -s "$SESSION" --gpu L4 >>"$Q/orchestrator.log" 2>&1 || return 1
  fi
  if ! ssh -O check "$SESSION" >/dev/null 2>&1; then
    ssh_ready || return 1
    ssh -fN -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
      -L 11435:127.0.0.1:11434 -L 11436:127.0.0.1:11436 "$SESSION" || return 1
  elif ! tunnel_ok; then
    # A master opened without forwards (e.g. by a manual ssh): add them to it.
    ssh -O forward -L 11435:127.0.0.1:11434 -L 11436:127.0.0.1:11436 "$SESSION" >/dev/null 2>&1
  fi
  local want have
  want="$(du -sbL "$ASSETS/embeddinggemma-2" | cut -f1)"
  have="$(ssh "$SESSION" 'cat /root/emb/.complete 2>/dev/null')"
  if [ "$have" != "$want" ]; then
    log "pushing embedding weights ($want bytes)"
    tar -C "$ASSETS" -chf - embeddinggemma-2 | ssh "$SESSION" \
      "rm -rf /root/emb/embeddinggemma-2; mkdir -p /root/emb && tar -C /root/emb -xf - && du -sb /root/emb/embeddinggemma-2 | cut -f1 > /root/emb/.complete" || return 1
    [ "$(ssh "$SESSION" 'cat /root/emb/.complete 2>/dev/null')" = "$want" ] || { log "weights incomplete"; return 1; }
  fi
  ssh "$SESSION" mkdir -p /root/b12/scripts
  scp -q "$REPO/scripts/st_embedder.py" "$REPO/scripts/embed_server.py" "$SESSION:/root/b12/scripts/" || return 1
  ssh "$SESSION" "sed -i 's|^MODEL_ID = .*|MODEL_ID = \"/root/emb/embeddinggemma-2\"|' /root/b12/scripts/st_embedder.py"
  MODELS="$1" ssh "$SESSION" "MODELS='$1' bash -s" <"$REPO/ops/remote/colab_bootstrap.sh" >"$Q/tags.json" 2>>"$Q/orchestrator.log" || return 1
  if ! pgrep -u "$USER" -f "UNIX-LISTEN:$SOCK" >/dev/null; then
    rm -f "$SOCK"
    (setsid socat "UNIX-LISTEN:$SOCK,fork,mode=600" TCP:127.0.0.1:11436 >/dev/null 2>&1 &)
    for _ in $(seq 20); do [ -S "$SOCK" ] && break; sleep 0.5; done
  fi
  tunnel_ok
}

profile_for() {  # model -> profile file name matching the served digest (template must match)
  if [ "${B12_ORCH_DRYRUN:-0}" = "1" ]; then
    echo "dryrun"
    return 0
  fi
  "$REPO/.venv/bin/python" "$REPO/ops/remote/profile_for.py" "$1" "$Q/tags.json"
}

run_job() {
  local name="$1" manifest="$2" out="$3" repeats="$4" arm="$5" model="$6" extra="$7" profile
  profile="$(profile_for "$model")" || { log "$name: no profile for $model"; return 1; }
  log "$name: running ($model, profile $profile)"
  # setsid makes the driver the leader of its own process group (pgid = $driver), so a stop
  # kills the driver and its sandboxes, never this loop (the 20.11.2026 bug).
  cd "$REPO" || return 1
  local runner=(evals/unified/run_locked_pilot.sh "$manifest" "$out" "$repeats" "$arm")
  if [ "${manifest#cmd:}" != "$manifest" ]; then
    mkdir -p "$REPO/$out"
    runner=(bash -c "${manifest#cmd:} && echo DONE >>'$REPO/$out/pilot.log'")
  fi
  setsid env B12_EVAL_MODEL="$model" B12_EVAL_PROFILE_FILE="$profile" \
    B12_EVAL_OLLAMA_URL=http://127.0.0.1:11435 B12_EVAL_VARIANT=deployed \
    B12_EVAL_EMBED_SOCKET="$SOCK" NO_GPU_WAIT=1 EXTRA_RUNNER_ARGS="--variant deployed $extra" \
    "${runner[@]}" >>"$Q/$name.log" 2>&1 &
  local driver=$! misses=0 records last_change
  DRIVER_PID="$driver"
  # Progress: new records for scenario jobs; for a cmd job, its log growing.
  progress() {
    { find "$REPO/$out" -mindepth 2 -maxdepth 2 -name '*.json' 2>/dev/null | wc -l
      stat -c %s "$Q/$name.log" 2>/dev/null; } | tr '\n' ' '
  }
  records="$(progress)"; last_change=$(date +%s)
  while kill -0 "$driver" 2>/dev/null; do
    interruptible_sleep 30
    local now_records; now_records="$(progress)"
    if [ "$now_records" != "$records" ]; then records="$now_records"; last_change=$(date +%s); fi
    if [ $(( $(date +%s) - last_change )) -ge 900 ]; then
      log "$name: no new record for 15 min, restarting the driver"
      kill -TERM -- "-$driver" 2>/dev/null; wait "$driver" 2>/dev/null; DRIVER_PID=""
      return 1
    fi
    if [ "${B12_ORCH_DRYRUN:-0}" = "1" ] || (tunnel_ok && session_alive); then misses=0; continue; fi
    misses=$((misses + 1))
    [ "$misses" -lt 3 ] && continue  # one failed listing is not a lost session
    log "$name: Colab lost (3 checks), stopping the driver to resume after reconnect"
    kill -TERM -- "-$driver" 2>/dev/null; wait "$driver" 2>/dev/null; DRIVER_PID=""
    return 1
  done
  wait "$driver"; DRIVER_PID=""; grep -qs DONE "$REPO/$out/pilot.log"
}

log "orchestrator start"
while true; do
  jobs_left="$(pending_jobs)"
  if [ -z "$jobs_left" ]; then
    if [ "${B12_ORCH_DRYRUN:-0}" != "1" ] && session_alive; then log "queue empty: stopping Colab"; ssh -O exit "$SESSION" >/dev/null 2>&1; colab stop -s "$SESSION" >>"$Q/orchestrator.log" 2>&1; fi
    interruptible_sleep 300; continue
  fi
  IFS=$'\t' read -r name manifest out repeats arm model extra <<<"$(head -1 <<<"$jobs_left")"
  models="$(cut -f6 <<<"$jobs_left" | sort -u | tr '\n' ' ')"
  if ! ensure_colab "$models"; then log "Colab not ready; retry in 2 min"; interruptible_sleep 120; continue; fi
  run_job "$name" "$manifest" "$out" "$repeats" "$arm" "$model" "$extra" || interruptible_sleep 30
done
