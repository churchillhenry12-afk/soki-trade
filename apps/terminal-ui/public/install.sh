#!/usr/bin/env bash
set -euo pipefail

release_url="https://github.com/churchillhenry12-afk/soki-trade/releases/download/v0.1.0/soki-trade-0.1.0.tar.gz"
release_sha256="887cd40d0b67a3e9362072ade97cff8617b90d51bf2b30cdf4470c701a749f53"
public_origin="https://soki-trade-agent.vercel.app"
install_directory="${SOKI_INSTALL_DIR:-$HOME/.local/share/soki-trade}"
bin_directory="${SOKI_BIN_DIR:-$HOME/.local/bin}"
temporary_directory="$(mktemp -d "${TMPDIR:-/tmp}/soki-trade.XXXXXX")"
archive_path="$temporary_directory/soki-trade.tar.gz"

cleanup() {
  rm -rf "$temporary_directory"
}
trap cleanup EXIT

if ! command -v curl >/dev/null 2>&1; then
  echo "Soki Trade requires curl to download the verified release." >&2
  exit 1
fi

if ! command -v tar >/dev/null 2>&1; then
  echo "Soki Trade requires tar to unpack the verified release." >&2
  exit 1
fi

echo "Downloading Soki Trade..."
curl -fsSL "$release_url" -o "$archive_path"

if command -v shasum >/dev/null 2>&1; then
  actual_sha256="$(shasum -a 256 "$archive_path" | awk '{print $1}')"
elif command -v sha256sum >/dev/null 2>&1; then
  actual_sha256="$(sha256sum "$archive_path" | awk '{print $1}')"
else
  echo "Soki Trade requires shasum or sha256sum to verify the release." >&2
  exit 1
fi

if [[ "$actual_sha256" != "$release_sha256" ]]; then
  echo "Release checksum verification failed. Nothing was installed." >&2
  exit 1
fi

mkdir -p "$install_directory" "$bin_directory"
tar -xzf "$archive_path" -C "$install_directory" --strip-components=1
chmod +x "$install_directory/soki" "$install_directory"/infrastructure/scripts/*.sh

environment_file="$install_directory/.env"
touch "$environment_file"
chmod 600 "$environment_file"
if ! grep -q '^QFORGE_CORS_ORIGINS=' "$environment_file"; then
  printf '%s\n' \
    "QFORGE_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,$public_origin" \
    >>"$environment_file"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing the uv Python runtime manager from Astral..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv was installed but is not on PATH. Open a new terminal and rerun this installer." >&2
  exit 1
fi

echo "Preparing the Soki Trade runtime..."
(
  cd "$install_directory"
  uv sync
)

ln -sfn "$install_directory/soki" "$bin_directory/soki-trade"

echo
echo "Soki Trade installed successfully."
echo "Start it with:"
echo "  $bin_directory/soki-trade"
if [[ ":$PATH:" != *":$bin_directory:"* ]]; then
  echo
  echo "Add this directory to PATH for the short 'soki-trade' command:"
  printf '  export PATH="%s:$PATH"\n' "$bin_directory"
fi
