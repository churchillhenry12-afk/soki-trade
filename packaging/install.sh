#!/usr/bin/env bash
set -euo pipefail

# One Soki Code installation owns both the Soki application and its pinned
# Hermes Agent runtime. Hermes remains an internal, MIT-licensed dependency.
soki_repository="https://github.com/churchillhenry12-afk/soki-trade.git"
soki_ref="${SOKI_REF:-main}"
soki_root="${SOKI_INSTALL_DIR:-$HOME/.local/share/soki-code}"
soki_bin_directory="${SOKI_BIN_DIR:-$HOME/.local/bin}"
soki_app_directory="$soki_root/app"
soki_data_directory="$soki_root/data"
hermes_home="$soki_root/runtime/hermes"
hermes_directory="$hermes_home/hermes-agent"

hermes_tag="v2026.7.20"
hermes_commit="3ef6bbd201263d354fd83ec55b3c306ded2eb72a"
hermes_installer_url="https://raw.githubusercontent.com/NousResearch/hermes-agent/$hermes_tag/scripts/install.sh"
hermes_installer_sha256="c5ba7e89627577fab914514736ecfb3359b66956ca00199bfef616ca35953cb9"

temporary_directory="$(mktemp -d "${TMPDIR:-/tmp}/soki-code.XXXXXX")"
hermes_installer="$temporary_directory/hermes-install.sh"

cleanup() {
  rm -rf "$temporary_directory"
}
trap cleanup EXIT

sha256_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    echo "A SHA-256 utility (shasum or sha256sum) is required." >&2
    return 1
  fi
}

find_executable() {
  local name="$1"
  shift
  if command -v "$name" >/dev/null 2>&1; then
    command -v "$name"
    return 0
  fi
  local candidate
  for candidate in "$@"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if ! command -v curl >/dev/null 2>&1; then
  echo "Soki Code requires curl." >&2
  exit 1
fi

mkdir -p "$soki_root" "$soki_bin_directory" "$soki_data_directory"

printf '\033[38;2;167;183;255m'
echo "  ┏━┓ ┏━┓ ╻┏ ╻    ┏━╸ ┏━┓ ┏━┓ ┏━╸"
echo "  ┗━┓ ┃ ┃ ┣┻┓┃    ┃   ┃ ┃ ┃ ┃ ┣╸ "
echo "  ┗━┛ ┗━┛ ╹ ╹╹    ┗━╸ ┗━┛ ┗━┛ ┗━╸"
printf '\033[0m\n'
echo "Installing one product: Soki Code with its automation runtime."

echo "Downloading the verified Soki automation runtime..."
curl -fsSL "$hermes_installer_url" -o "$hermes_installer"
if [[ "$(sha256_file "$hermes_installer")" != "$hermes_installer_sha256" ]]; then
  echo "Hermes installer checksum verification failed. Nothing was executed." >&2
  exit 1
fi

export HERMES_HOME="$hermes_home"
bash "$hermes_installer" \
  --branch main \
  --commit "$hermes_commit" \
  --dir "$hermes_directory" \
  --hermes-home "$hermes_home" \
  --skip-setup \
  --non-interactive

git_command="$(find_executable git \
  "$hermes_home/git/cmd/git" \
  "$hermes_home/git/bin/git" \
  "$hermes_home/bin/git")" || {
    echo "The bundled runtime could not provide Git." >&2
    exit 1
  }

echo "Installing Soki Code..."
if [[ -d "$soki_app_directory/.git" ]]; then
  "$git_command" -C "$soki_app_directory" fetch --depth 1 origin "$soki_ref"
  "$git_command" -C "$soki_app_directory" checkout -B soki-installed FETCH_HEAD
else
  if [[ -e "$soki_app_directory" ]]; then
    echo "$soki_app_directory already exists but is not a Soki installation." >&2
    exit 1
  fi
  "$git_command" clone --depth 1 --branch "$soki_ref" \
    "$soki_repository" "$soki_app_directory"
fi

uv_command="$(find_executable uv \
  "$HOME/.local/bin/uv" \
  "$HOME/.cargo/bin/uv" \
  "$hermes_home/bin/uv")" || {
    echo "The bundled runtime could not provide uv." >&2
    exit 1
  }
npm_command="$(find_executable npm \
  "$hermes_home/node/bin/npm" \
  "$hermes_home/bin/npm")" || {
    echo "The bundled runtime could not provide Node.js/npm." >&2
    exit 1
  }
hermes_command=""
for candidate in \
  "$hermes_directory/venv/bin/hermes" \
  "$hermes_home/bin/hermes"; do
  if [[ -x "$candidate" ]]; then
    hermes_command="$candidate"
    break
  fi
done
if [[ -z "$hermes_command" ]]; then
    echo "The bundled Hermes executable was not found." >&2
    exit 1
fi

(
  cd "$soki_app_directory"
  "$uv_command" sync
  "$npm_command" ci --prefix apps/soki-code-web
)

runtime_key=""
if [[ -f "$hermes_home/.env" ]]; then
  runtime_key="$(sed -n 's/^API_SERVER_KEY=//p' "$hermes_home/.env" | tail -n 1 | tr -d "'\"")"
fi
if [[ -z "$runtime_key" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    runtime_key="$(openssl rand -hex 32)"
  else
    runtime_key="$("$uv_command" run python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  fi
fi

"$hermes_command" config set API_SERVER_ENABLED true
"$hermes_command" config set API_SERVER_HOST 127.0.0.1
"$hermes_command" config set API_SERVER_KEY "$runtime_key"
"$hermes_command" tools enable --platform api_server computer_use
"$hermes_command" tools post-setup cua_driver || \
  echo "Computer-control support will finish installing during Soki setup."
if ! "$hermes_command" gateway restart; then
  "$hermes_command" gateway install
  "$hermes_command" gateway start
fi

chmod +x \
  "$soki_app_directory/soki" \
  "$soki_app_directory"/infrastructure/scripts/*.sh

launcher="$soki_bin_directory/soki-code"
cat >"$launcher" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export HERMES_HOME='$hermes_home'
export HERMES_BIN='$hermes_command'
export QFORGE_DATABASE_URL='sqlite:///$soki_data_directory/qforge.db'
export QFORGE_PROVIDER_CONFIG_PATH='$soki_data_directory/provider-config.json'
export QFORGE_GATEWAY_CONFIG_PATH='$soki_data_directory/gateway-config.json'
export QFORGE_MARKET_DATA_DIRECTORY='$soki_data_directory/market'
export QFORGE_HERMES_CONFIG_PATH='$soki_data_directory/hermes-config.json'
export QFORGE_ATTACHMENT_DIRECTORY='$soki_data_directory/attachments'
cd '$soki_app_directory'
exec ./soki "\$@"
EOF
chmod +x "$launcher"
ln -sfn "$launcher" "$soki_bin_directory/soki-trade"

echo
echo "Soki Code installed successfully."
echo "Start it with:"
echo "  $launcher"
if [[ ":$PATH:" != *":$soki_bin_directory:"* ]]; then
  echo
  echo "Add Soki Code to this shell:"
  printf '  export PATH="%s:$PATH"\n' "$soki_bin_directory"
fi
if [[ "$(uname -s)" == "Darwin" ]]; then
  echo
  echo "macOS will ask you to approve Screen Recording and Accessibility"
  echo "when Soki first controls the desktop. Those OS permissions cannot be pre-approved."
fi
