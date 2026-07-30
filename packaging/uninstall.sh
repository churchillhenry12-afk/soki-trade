#!/usr/bin/env bash
set -euo pipefail

soki_root="${SOKI_INSTALL_DIR:-$HOME/.local/share/soki-code}"
soki_bin_directory="${SOKI_BIN_DIR:-$HOME/.local/bin}"
hermes_command="$soki_root/runtime/hermes/hermes-agent/venv/bin/hermes"

if [[ -x "$hermes_command" ]]; then
  HERMES_HOME="$soki_root/runtime/hermes" "$hermes_command" gateway stop >/dev/null 2>&1 || true
fi

rm -f "$soki_bin_directory/soki-code" "$soki_bin_directory/soki-trade"
rm -rf "$soki_root/app" "$soki_root/runtime"

echo "Soki Code and its bundled automation runtime were removed."
if [[ "${SOKI_PURGE_DATA:-0}" == "1" ]]; then
  rm -rf "$soki_root/data"
  rmdir "$soki_root" 2>/dev/null || true
  echo "Soki user data was also removed."
else
  echo "User data was preserved at $soki_root/data"
fi
