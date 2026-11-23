#!/usr/bin/env bash
# Runs ON the Colab VM (piped over SSH by orchestrator.sh). Idempotent: Ollama 0.33.3 serving
# the requested models, the embedding libraries, and the embedding server on 127.0.0.1:11436.
# Expects /root/b12/scripts/{st_embedder,embed_server}.py and /root/emb/embeddinggemma-2.
set -euo pipefail
MODELS="${MODELS:-gemma4:12b}"
command -v zstd >/dev/null || { apt-get update -qq >/dev/null; apt-get install -y -qq zstd >/dev/null; }
command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION=0.33.3 sh >/tmp/ollama-install.log 2>&1
if ! curl -fs 127.0.0.1:11434/api/version >/dev/null; then
  # Detached from the SSH channel (stdin/stdout/stderr), or the caller's ssh never returns.
  (OLLAMA_KEEP_ALIVE=-1 setsid nohup ollama serve </dev/null >/tmp/ollama.log 2>&1 &)
  for _ in $(seq 60); do curl -fs 127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
fi
for model in $MODELS; do
  ollama list | awk 'NR>1{print $1}' | grep -qx "$model" || ollama pull "$model" >/tmp/pull.log 2>&1
done
python3 -c 'import sentence_transformers as s, transformers as t; assert (s.__version__, t.__version__) == ("6.1.0", "5.19.0")' 2>/dev/null \
  || pip install -q sentence-transformers==6.1.0 transformers==5.19.0 >/tmp/pip.log 2>&1
if ! (exec 3<>/dev/tcp/127.0.0.1/11436) 2>/dev/null; then
  # The whole background subshell is detached from the SSH channel, not only the python: the
  # subshell itself kept the channel's stdout open, so the caller's ssh never returned
  # (23.11.2026: the orchestrator hung 27 min after the embedding server was up).
  (cd /root/b12/scripts && HF_HUB_OFFLINE=1 exec setsid nohup python3 embed_server.py \
     --backend st_embedder:Embedder --port 11436) </dev/null >/tmp/embed.log 2>&1 &
  for _ in $(seq 180); do (exec 3<>/dev/tcp/127.0.0.1/11436) 2>/dev/null && break; sleep 1; done
fi
curl -fs 127.0.0.1:11434/api/tags
