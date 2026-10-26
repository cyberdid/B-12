#!/usr/bin/env bash
# Root-free install of the B-12 systemd user service.
# Usage: scripts/install-user-service.sh /abs/b12 /abs/profile.json /abs/tokenizer [port]
# Does not start the service; run: systemctl --user enable --now b12.service
set -euo pipefail
b12_bin=${1:?absolute path to the b12 executable}
profile=${2:?absolute path to the calibrated model profile}
tokenizer=${3:?absolute path to pinned tokenizer assets}
port=${4:-8712}
for path in "$b12_bin" "$profile" "$tokenizer"; do
  [[ "$path" = /* && -e "$path" ]] || { echo "not an existing absolute path: $path" >&2; exit 1; }
done
config_dir=${XDG_CONFIG_HOME:-$HOME/.config}
unit_dir=$config_dir/systemd/user
env_file=$config_dir/b12/env
repo=$(cd "$(dirname "$0")/.." && pwd)
umask 077
mkdir -p "$unit_dir" "$config_dir/b12"
if [[ ! -e "$env_file" ]]; then
  cat > "$env_file" <<ENV
B12_PORT=$port
B12_MODEL_PROFILE=$profile
B12_TOKENIZER_DIR=$tokenizer
ENV
fi
chmod 600 "$env_file"
sed -e "s|@B12_BIN@|$b12_bin|" -e "s|@ENV_FILE@|$env_file|" \
  "$repo/deploy/b12.service" > "$unit_dir/b12.service"
B12_MODEL_PROFILE="$profile" B12_TOKENIZER_DIR="$tokenizer" "$b12_bin" init >/dev/null
systemctl --user daemon-reload
echo "installed $unit_dir/b12.service (env $env_file); start: systemctl --user enable --now b12.service"
