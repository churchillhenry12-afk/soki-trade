$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$sokiRoot = if ($env:SOKI_INSTALL_DIR) {
    $env:SOKI_INSTALL_DIR
}
else {
    Join-Path $env:LOCALAPPDATA "SokiCode"
}
$sokiBinDirectory = if ($env:SOKI_BIN_DIR) {
    $env:SOKI_BIN_DIR
}
else {
    Join-Path $env:USERPROFILE ".local\bin"
}
$hermesHome = Join-Path $sokiRoot "runtime\hermes"
$hermesCommand = Join-Path $hermesHome "hermes-agent\venv\Scripts\hermes.exe"

if (Test-Path $hermesCommand) {
    $env:HERMES_HOME = $hermesHome
    & $hermesCommand gateway stop 2>$null
}

Remove-Item -Force `
    (Join-Path $sokiBinDirectory "soki-code.cmd"), `
    (Join-Path $sokiBinDirectory "soki-trade.cmd") `
    -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force `
    (Join-Path $sokiRoot "app"), `
    (Join-Path $sokiRoot "runtime") `
    -ErrorAction SilentlyContinue

Write-Host "Soki Code and its bundled automation runtime were removed."
if ($env:SOKI_PURGE_DATA -eq "1") {
    Remove-Item -Recurse -Force (Join-Path $sokiRoot "data") -ErrorAction SilentlyContinue
    Remove-Item -Force $sokiRoot -ErrorAction SilentlyContinue
    Write-Host "Soki user data was also removed."
}
else {
    Write-Host "User data was preserved at $(Join-Path $sokiRoot 'data')"
}
