#!/usr/bin/env bash
# Run runtime-backed scenarios in a filesystem- and network-isolated bubblewrap sandbox.
#
# The real B-12 runtime gives the model host tools (files, commands) with the user's
# rights. Inside the sandbox the root filesystem is read-only, /home, /media, /mnt,
# /run, /tmp and /var/tmp are empty tmpfs, and only the paths below are visible:
#   - the repository, read-only, except artifacts/ and reports/ (read-write);
#   - the Python virtualenv (it may live outside the repository), model profiles and
#     tokenizers, read-only.
# A host-side allowlist broker is the only path to Ollama. The worker gets a private UDS
# mount and a loopback bridge inside a fresh network namespace; it cannot reach host or
# external network services directly.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO"
EVAL="$REPO/evals/capri_comprehensive"
B12_SHARE="$HOME/.local/share/b12"
BOLT_TOKENIZER="$HOME/Downloads/B-12-runtime/tokenizer"
VENV="$(readlink -f "$REPO/.venv")"
BROKER_DIR="$(mktemp -d /tmp/b12-eval-broker.XXXXXX)"
BROKER_LOG="$(mktemp /tmp/b12-eval-broker-log.XXXXXX)"
chmod 700 "$BROKER_DIR"
mkdir -p "$EVAL/artifacts" "$EVAL/reports"

cleanup() {
  if [ -n "${BROKER_PID:-}" ]; then
    kill -TERM "$BROKER_PID" 2>/dev/null || true
    wait "$BROKER_PID" 2>/dev/null || true
  fi
  rm -rf -- "$BROKER_DIR"
  [ -n "${STAGE:-}" ] && rm -rf -- "${STAGE:?}"
  rm -f -- "$BROKER_LOG"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

OLLAMA_UPSTREAM="${B12_EVAL_OLLAMA_URL:-http://127.0.0.1:11434}"
EVAL_MODEL="${B12_EVAL_MODEL:-gemma4:12b}"
case "$EVAL_MODEL" in
  gemma4:12b|gemma4:26b|gemma4:31b) ;;
  *) echo "unsupported B12_EVAL_MODEL profile: $EVAL_MODEL" >&2; exit 2 ;;
esac
"$VENV/bin/python" -m evals.ollama_broker \
  --socket "$BROKER_DIR/model.sock" \
  --upstream "$OLLAMA_UPSTREAM" \
  --model b12-bolt-e4b:q4km \
  --model "$EVAL_MODEL" \
  --ready-file "$BROKER_DIR/ready" >"$BROKER_LOG" 2>&1 &
BROKER_PID=$!
for _ in $(seq 1 100); do
  [ -f "$BROKER_DIR/ready" ] && break
  if ! kill -0 "$BROKER_PID" 2>/dev/null; then
    cat "$BROKER_LOG" >&2
    echo "model broker exited before becoming ready" >&2
    exit 1
  fi
  sleep 0.05
done
if [ ! -S "$BROKER_DIR/model.sock" ] || [ ! -f "$BROKER_DIR/ready" ]; then
  cat "$BROKER_LOG" >&2
  echo "model broker failed to become ready" >&2
  exit 1
fi

EXTRA=()
case "${B12_EVAL_VARIANT:-}" in deployed*)
  if [ -n "${B12_EVAL_EMBED_SOCKET:-}" ]; then
    # Remote embeddings (e2-micro orchestrator): only the socket's directory is visible and the
    # embedding "interpreter" is the stdlib shim that relays to it.
    [ -S "$B12_EVAL_EMBED_SOCKET" ] || { echo "missing $B12_EVAL_EMBED_SOCKET" >&2; exit 1; }
    EMB_DIR="$(dirname "$B12_EVAL_EMBED_SOCKET")"
    EXTRA=(--ro-bind "$EMB_DIR" "$EMB_DIR" --setenv B12_EVAL_VARIANT "$B12_EVAL_VARIANT"
           --setenv B12_EVAL_EMBED_SOCKET "$B12_EVAL_EMBED_SOCKET"
           --setenv B12_EVAL_SEMANTIC_PYTHON "$REPO/scripts/embed_socket_shim.py")
    [ -n "${B12_EVAL_PROFILE_FILE:-}" ] && EXTRA+=(--setenv B12_EVAL_PROFILE_FILE "$B12_EVAL_PROFILE_FILE")
  else
  # Semantic recall: the EmbeddingGemma 2 bridge, its interpreter, package source and the
  # cached weights, all read-only. Nothing else of that project is visible.
  EMB_VENV="$HOME/.local/share/embeddinggemma2/venv"
  UV_PYTHONS="$HOME/.local/share/uv/python"  # the venv's interpreter (via symlinks)
  EMB_PKG="$("$EMB_VENV/bin/python" -c 'import archive_index, pathlib; print(pathlib.Path(archive_index.__file__).parents[1])')"
  EMB_WEIGHTS="$HOME/.cache/huggingface/hub/models--google--embeddinggemma-2"
  for path in "$EMB_VENV" "$UV_PYTHONS" "$EMB_PKG" "$EMB_WEIGHTS"; do
    [ -e "$path" ] || { echo "missing $path" >&2; exit 1; }
  done
  EXTRA=(--ro-bind "$EMB_VENV" "$EMB_VENV" --ro-bind "$UV_PYTHONS" "$UV_PYTHONS"
         --ro-bind "$EMB_PKG" "$EMB_PKG"
         --ro-bind "$EMB_WEIGHTS" "$EMB_WEIGHTS" --setenv B12_EVAL_VARIANT "$B12_EVAL_VARIANT")
  [ -n "${B12_EVAL_PROFILE_FILE:-}" ] && EXTRA+=(--setenv B12_EVAL_PROFILE_FILE "$B12_EVAL_PROFILE_FILE")
  fi
  ;;
esac
# A venv made by uv points at an interpreter under ~/.local/share/uv (hidden by the /home
# tmpfs): bind that interpreter's install root read-only (found on the e2-micro, 20.11.2026).
# The directory holding the installs (uv links versions through cpython-3.12-… symlinks).
PY_ROOT="$(dirname "$(dirname "$(dirname "$(readlink -f "$VENV/bin/python")")")")"
case "$PY_ROOT" in "$HOME"/*) EXTRA+=(--ro-bind "$PY_ROOT" "$PY_ROOT") ;; esac
for path in "$B12_SHARE" "$BOLT_TOKENIZER" "$VENV"; do
  [ -d "$path" ] || { echo "missing $path" >&2; exit 1; }
done
# Entry point: the comprehensive suite (default) or one unified U2/U3 scenario. The latter
# gets fresh empty tmpfs mounts at /sandbox and /actors for its synthetic files.
ENTRY=(-m evals.capri_comprehensive.runners.run_networkless_runtime_suite)
ROOT_ARGS=(--ro-bind / /)
case "${B12_EVAL_ENTRY:-suite}" in
  suite) ;;
  unified-u2u3|unified-probe)
    ENTRY=(-m evals.unified.run_u2_u3)
    [ "$B12_EVAL_ENTRY" = unified-probe ] && ENTRY=(-m evals.unified.sandbox_probe)
    # bwrap 0.9 cannot create /sandbox under a read-only bind of /, so bind each top-level
    # host entry read-only (symlinks recreated) over the fresh root instead; the mount
    # points /sandbox and /actors then become empty writable tmpfs.
    ROOT_ARGS=()
    for top in /*; do
      case "${top#/}" in sandbox|actors|proc|dev|lost+found) continue ;; esac
      if [ -L "$top" ]; then
        ROOT_ARGS+=(--symlink "$(readlink "$top")" "$top")
      elif [ -d "$top" ]; then
        ROOT_ARGS+=(--ro-bind "$top" "$top")
      fi
    done
    EXTRA+=(--tmpfs /sandbox --tmpfs /actors)
    # Leak fix (19.11.2026): a model searching the home directory found judge sheets and the
    # oracle review in the repository. The worker now sees only this scenario's input and setup
    # fixtures; answers, reviews, reports, other runs' records and host logs are hidden.
    OUT_ARG="${3:?unified entry needs: manifest scenario_id out_dir}"
    mkdir -p "$OUT_ARG"
    OUT_ABS="$(cd "$OUT_ARG" && pwd)"
    STAGE="$(mktemp -d /tmp/b12-u2u3-stage.XXXXXX)"
    "$VENV/bin/python" - "$1" "$2" "$STAGE" <<'PY'
import json, shutil, sys
from pathlib import Path
manifest, scenario, stage = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
row = next(r for r in json.loads(manifest.read_text(encoding="utf-8"))["scenarios"]
           if r["scenario_id"] == scenario)
for key in ("input_fixture", "setup_fixture"):
    if row.get(key):
        target = stage / row[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(row[key], target)
PY
    for hidden in reports paper raw wiki research docs tests evals/unified/draft_sources; do
      [ -d "$REPO/$hidden" ] && EXTRA+=(--tmpfs "$REPO/$hidden")
    done
    mkdir -p "$STAGE/evals/unified/draft_fixtures"
    EXTRA+=(--ro-bind "$STAGE/evals/unified/draft_fixtures" "$REPO/evals/unified/draft_fixtures")
    EXTRA+=(--tmpfs "$EVAL/artifacts" --tmpfs "$EVAL/reports" --bind "$OUT_ABS" "$OUT_ABS")
    [ -d /var/log ] && EXTRA+=(--tmpfs /var/log)
    ;;
  *) echo "unsupported B12_EVAL_ENTRY: ${B12_EVAL_ENTRY}" >&2; exit 2 ;;
esac
bwrap \
  "${ROOT_ARGS[@]}" \
  --dev /dev --proc /proc \
  --tmpfs /tmp --tmpfs /var/tmp --tmpfs /home --tmpfs /media --tmpfs /mnt --tmpfs /run \
  --dir "$HOME" \
  --dir /tmp/model-broker \
  --ro-bind "$BROKER_DIR" /tmp/model-broker \
  --ro-bind "$REPO" "$REPO" \
  --bind "$EVAL/artifacts" "$EVAL/artifacts" \
  --bind "$EVAL/reports" "$EVAL/reports" \
  --ro-bind "$B12_SHARE" "$B12_SHARE" \
  --ro-bind "$BOLT_TOKENIZER" "$BOLT_TOKENIZER" \
  --ro-bind "$VENV" "$VENV" \
  "${EXTRA[@]}" \
  --unshare-net --unshare-pid --unshare-ipc --unshare-uts --die-with-parent --new-session \
  --setenv HOME "$HOME" --setenv B12_EVAL_SANDBOX 1 \
  --setenv B12_EVAL_BROKER_SOCKET /tmp/model-broker/model.sock \
  --setenv B12_EVAL_OLLAMA_URL http://127.0.0.1:11434 \
  --setenv B12_EVAL_MODEL "$EVAL_MODEL" \
  --unsetenv B12_STATE_DIR --unsetenv B12_MODEL --unsetenv B12_MODEL_PROFILE \
  --unsetenv B12_TOKENIZER_DIR \
  --chdir "$REPO" \
  "$VENV/bin/python" "${ENTRY[@]}" "$@"
