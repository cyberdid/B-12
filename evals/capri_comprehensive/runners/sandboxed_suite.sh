#!/usr/bin/env bash
# Run run_runtime_suite.py inside a bubblewrap sandbox.
#
# The real B-12 runtime gives the model host tools (files, commands) with the user's
# rights. Inside the sandbox the root filesystem is read-only, /home, /media, /mnt,
# /run/user and /tmp are empty tmpfs, and only the paths below are visible:
#   - the repository, read-only, except artifacts/ and reports/ (read-write);
#   - the Python virtualenv (it may live outside the repository), model profiles and
#     tokenizers, read-only.
# The network is shared so the runtime can reach Ollama on 127.0.0.1; B-12's own
# http_fetch stays denied because network_allow is empty.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
EVAL="$REPO/evals/capri_comprehensive"
B12_SHARE="$HOME/.local/share/b12"
BOLT_TOKENIZER="$HOME/Downloads/B-12-runtime/tokenizer"
VENV="$(readlink -f "$REPO/.venv")"
mkdir -p "$EVAL/artifacts" "$EVAL/reports"
EXTRA=()
if [ "${B12_EVAL_VARIANT:-}" = "deployed" ]; then
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
         --ro-bind "$EMB_WEIGHTS" "$EMB_WEIGHTS" --setenv B12_EVAL_VARIANT deployed)
fi
for path in "$B12_SHARE" "$BOLT_TOKENIZER" "$VENV"; do
  [ -d "$path" ] || { echo "missing $path" >&2; exit 1; }
done
exec bwrap \
  --ro-bind / / \
  --dev /dev --proc /proc \
  --tmpfs /tmp --tmpfs /home --tmpfs /media --tmpfs /mnt --tmpfs /run/user \
  --dir "$HOME" \
  --ro-bind "$REPO" "$REPO" \
  --bind "$EVAL/artifacts" "$EVAL/artifacts" \
  --bind "$EVAL/reports" "$EVAL/reports" \
  --ro-bind "$B12_SHARE" "$B12_SHARE" \
  --ro-bind "$BOLT_TOKENIZER" "$BOLT_TOKENIZER" \
  --ro-bind "$VENV" "$VENV" \
  "${EXTRA[@]}" \
  --unshare-pid --unshare-ipc --unshare-uts --die-with-parent --new-session \
  --setenv HOME "$HOME" --setenv B12_EVAL_SANDBOX 1 \
  --unsetenv B12_STATE_DIR --unsetenv B12_MODEL --unsetenv B12_MODEL_PROFILE \
  --unsetenv B12_TOKENIZER_DIR \
  --chdir "$REPO" \
  "$VENV/bin/python" -m evals.capri_comprehensive.runners.run_runtime_suite "$@"
