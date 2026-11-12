#!/usr/bin/env bash
# Prepare the pinned Nemotron Bolt E4B deployment that profiles/bolt-e4b-ollama-0.33.3.json
# describes: the official Q4_K_M GGUF, the Ollama alias b12-bolt-e4b:q4km and the tokenizer
# assets. Every download is pinned to a revision and checked against a SHA-256.
#
#   scripts/setup-bolt.sh                # download (about 6.2 GB), verify, create the alias
#   scripts/setup-bolt.sh --verify-only  # check files and alias that are already in place
#
# Paths (override with environment variables):
#   B12_GGUF_DIR       where the GGUF goes   (default ~/.local/share/b12/models/bolt-e4b-q4)
#   B12_TOKENIZER_DIR  tokenizer assets      (default ~/.local/share/b12/tokenizers/bolt-e4b)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="$REPO/profiles/bolt-e4b-ollama-0.33.3.json"
ALIAS="b12-bolt-e4b:q4km"
GGUF_REPO="nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB"
GGUF_REVISION="1db54d5b12533ff1bcaa8e42cf4c667988a1f1be"
GGUF_FILE="Nemotron-3.5-Bolt-E4B-Q4_K_M.gguf"
GGUF_SHA256="c8af2b8aea10a690a1d9491db744a9446660173cb38fc489612b556615a69612"
TOKENIZER_REPO="nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-BF16"
GGUF_DIR="${B12_GGUF_DIR:-$HOME/.local/share/b12/models/bolt-e4b-q4}"
TOKENIZER_DIR="${B12_TOKENIZER_DIR:-$HOME/.local/share/b12/tokenizers/bolt-e4b}"
VERIFY_ONLY=0
[ "${1:-}" = "--verify-only" ] && VERIFY_ONLY=1

die() { echo "setup-bolt: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null || die "missing command: $1 ($2)"; }
need ollama "https://ollama.com/download"
need sha256sum "coreutils"
need python3 "Python 3"
[ "$VERIFY_ONLY" = 1 ] || need hf "pip install -U huggingface_hub"

profile() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))$1)" "$PROFILE"; }
TOKENIZER_REVISION="$(profile "['revision']")"
SERVER_VERSION="$(profile "['server_version']")"
MANIFEST_DIGEST="$(profile "['manifest_digest']")"

check_sha() {  # file expected-sha256
  [ -f "$1" ] || die "not found: $1"
  local actual
  actual="$(sha256sum "$1" | cut -d' ' -f1)"
  [ "$actual" = "$2" ] || die "SHA-256 mismatch for $1: $actual, expected $2"
  echo "ok  $(basename "$1")"
}

# The server version matters (the client may differ); b12 doctor checks the same value.
version="$(python3 -c 'import json, urllib.request as u
print(json.load(u.urlopen("http://127.0.0.1:11434/api/version", timeout=5))["version"])' \
  2>/dev/null || echo unknown)"
if [ "$version" != "$SERVER_VERSION" ]; then
  echo "warning: Ollama $version, the profile was calibrated on $SERVER_VERSION;" \
       "b12 doctor may report profile_mismatch" >&2
fi

# 1. Weights.
if [ "$VERIFY_ONLY" = 0 ]; then
  mkdir -p "$GGUF_DIR"
  hf download "$GGUF_REPO" "$GGUF_FILE" --revision "$GGUF_REVISION" --local-dir "$GGUF_DIR"
fi
check_sha "$GGUF_DIR/$GGUF_FILE" "$GGUF_SHA256"

# 2. Ollama alias: native template, no projector or drafter (same as the calibrated one).
if [ "$VERIFY_ONLY" = 0 ]; then
  modelfile="$(mktemp)"
  trap 'rm -f "$modelfile"' EXIT
  cat > "$modelfile" <<EOF
FROM $GGUF_DIR/$GGUF_FILE
PARAMETER num_ctx 2048
PARAMETER num_predict 192
PARAMETER temperature 1.0
PARAMETER top_p 0.95
PARAMETER draft_num_predict 0
EOF
  ollama create "$ALIAS" -f "$modelfile"
fi
digest="$(ollama list | awk -v a="$ALIAS" '$1 == a {print $2}')"
[ -n "$digest" ] || die "Ollama has no $ALIAS"
if [ "${MANIFEST_DIGEST:0:${#digest}}" = "$digest" ]; then
  echo "ok  $ALIAS digest $digest matches the profile"
else
  echo "warning: $ALIAS digest $digest differs from the profile (${MANIFEST_DIGEST:0:12});" \
       "b12 doctor will report profile_mismatch" >&2
fi

# 3. Tokenizer assets used for exact context admission.
names=(tokenizer.json tokenizer_config.json chat_template.jinja)
if [ "$VERIFY_ONLY" = 0 ]; then
  mkdir -p "$TOKENIZER_DIR"
  hf download "$TOKENIZER_REPO" "${names[@]}" --revision "$TOKENIZER_REVISION" \
    --local-dir "$TOKENIZER_DIR"
fi
for name in "${names[@]}"; do
  check_sha "$TOKENIZER_DIR/$name" "$(profile "['files']['$name']")"
done

cat <<EOF

Bolt is ready. Add to your shell or ~/.config/b12/env:
  export B12_MODEL_PROFILE=$PROFILE
  export B12_TOKENIZER_DIR=$TOKENIZER_DIR
Then: uv run b12 doctor --json && uv run b12 init
EOF
