#!/usr/bin/env bash
set -euo pipefail

installer="$(mktemp "${TMPDIR:-/tmp}/soki-code-install.XXXXXX")"
cleanup() {
  rm -f "$installer"
}
trap cleanup EXIT

curl -fsSL \
  "https://raw.githubusercontent.com/churchillhenry12-afk/soki-trade/main/packaging/install.sh" \
  -o "$installer"
bash "$installer"
