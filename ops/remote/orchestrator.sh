#!/usr/bin/env bash
# e2-micro orchestrator: keeps a Colab GPU session serving the model, runs the eval queue in the
# local bubblewrap sandbox, survives the owner's laptop being off, and stops Colab when idle.
#
# Queue: ~/b12-queue/jobs.tsv, one job per line (tab-separated):
#   name  manifest  out_dir  repeats  arm  model  extra_runner_args
# A job is done when <out_dir>/pilot.log contains DONE (run_locked_pilot.sh is resumable).
# Log: ~/b12-queue/orchestrator.log. Run as a systemd service (ops/remote/b12-orchestrator.service).
set -uo pipefail
REPO="$HOME/Projects/B-12"; Q="$HOME/b12-queue"; ASSETS="$HOME/b12-assets"
SESSION=b12eval; SOCK_DIR="$HOME/b12-embed"; SOCK="$SOCK_DIR/embed.sock"
export PATH="$HOME/.local/bin:$PATH"
mkdir -p "$Q" "$SOCK_DIR"; touch "$Q/jobs.tsv"
log() { echo "$(date -Is) $*" >>"$Q/orchestrator.log"; }

pending_jobs() {
  while IFS=$'\t' read -r name manifest out repeats arm model extra; do
    [ -z "${name:-}" ] || [ "${name:0:1}" = "#" ] && continue
    grep -qs DONE "$REPO/$out/pilot.log" || printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$name" "$manifest" "$out" "$repeats" "$arm" "$model" "$extra"
  done <"$Q/jobs.tsv"
}

session_alive() { colab sessions 2>/dev/null | grep -q "$SESSION"; }
tunnel_ok() { curl -fs --max-time 10 http://127.0.0.1:11435/api/version >/dev/null; }

ensure_colab() {  # $1 = space-separated models
  if ! session_alive; then
    ssh -O exit "$SESSION" >/dev/null 2>&1
    log "creating Colab session"; colab new -s "$SESSION" --gpu L4 >>"$Q/orchestrator.log" 2>&1 || return 1
  fi
  if ! ssh -O check "$SESSION" >/dev/null 2>&1; then
    ssh -fN -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
      -L 11435:127.0.0.1:11434 -L 11436:127.0.0.1:11436 "$SESSION" || return 1
  fi
  if ! ssh "$SESSION" test -d /root/emb/embeddinggemma-2; then
    log "pushing embedding weights"
    tar -C "$ASSETS" -cf - embeddinggemma-2 | ssh "$SESSION" 'mkdir -p /root/emb && tar -C /root/emb -xf -' || return 1
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
  "$REPO/.venv/bin/python" "$REPO/ops/remote/profile_for.py" "$1" "$Q/tags.json"
}

run_job() {
  local name="$1" manifest="$2" out="$3" repeats="$4" arm="$5" model="$6" extra="$7" profile
  profile="$(profile_for "$model")" || { log "$name: no profile for $model"; return 1; }
  log "$name: running ($model, profile $profile)"
  (cd "$REPO" && setsid env B12_EVAL_MODEL="$model" B12_EVAL_PROFILE_FILE="$profile" \
     B12_EVAL_OLLAMA_URL=http://127.0.0.1:11435 B12_EVAL_VARIANT=deployed \
     B12_EVAL_EMBED_SOCKET="$SOCK" NO_GPU_WAIT=1 EXTRA_RUNNER_ARGS="--variant deployed $extra" \
     evals/unified/run_locked_pilot.sh "$manifest" "$out" "$repeats" "$arm" >>"$Q/$name.log" 2>&1) &
  local driver=$!
  while kill -0 "$driver" 2>/dev/null; do
    sleep 30
    if ! tunnel_ok || ! session_alive; then
      log "$name: Colab lost, stopping the driver to resume after reconnect"
      pkill -TERM -g "$(ps -o pgid= "$driver" | tr -d ' ')" 2>/dev/null; wait "$driver" 2>/dev/null
      return 1
    fi
  done
  wait "$driver"; grep -qs DONE "$REPO/$out/pilot.log"
}

log "orchestrator start"
while true; do
  jobs_left="$(pending_jobs)"
  if [ -z "$jobs_left" ]; then
    if session_alive; then log "queue empty: stopping Colab"; ssh -O exit "$SESSION" >/dev/null 2>&1; colab stop -s "$SESSION" >>"$Q/orchestrator.log" 2>&1; fi
    sleep 300; continue
  fi
  IFS=$'\t' read -r name manifest out repeats arm model extra <<<"$(head -1 <<<"$jobs_left")"
  models="$(cut -f6 <<<"$jobs_left" | sort -u | tr '\n' ' ')"
  if ! ensure_colab "$models"; then log "Colab not ready; retry in 2 min"; sleep 120; continue; fi
  run_job "$name" "$manifest" "$out" "$repeats" "$arm" "$model" "$extra" || sleep 30
done
