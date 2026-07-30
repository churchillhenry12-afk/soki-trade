$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$installer = Join-Path $env:TEMP ("soki-code-install-" + [Guid]::NewGuid() + ".ps1")
try {
    Invoke-WebRequest `
        -Uri "https://raw.githubusercontent.com/churchillhenry12-afk/soki-trade/main/packaging/install.ps1" `
        -OutFile $installer `
        -UseBasicParsing
    & $installer
}
finally {
    Remove-Item -Force $installer -ErrorAction SilentlyContinue
}
