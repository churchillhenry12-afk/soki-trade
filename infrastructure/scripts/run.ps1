$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectDirectory = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $projectDirectory

function Test-Port([int] $port) {
    return $null -ne (
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    )
}

function Get-FreePort([int] $start) {
    $candidate = $start
    while (Test-Port $candidate) {
        $candidate++
    }
    return $candidate
}

function Test-SokiApi([int] $port) {
    try {
        $result = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 2
        return $result.status -eq "ok"
    }
    catch {
        return $false
    }
}

function Test-SokiWeb([int] $port) {
    try {
        $result = Invoke-WebRequest "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 2
        return $result.Content -match "<title>soki code</title>"
    }
    catch {
        return $false
    }
}

function Stop-ProcessTree([Diagnostics.Process] $process) {
    if (-not $process.HasExited) {
        & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
    }
}

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $uvCommand -or $null -eq $npmCommand) {
    throw "Soki Code is incomplete. Re-run the official Soki Code installer."
}
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Soki Code Python dependencies are missing. Re-run the installer."
}
if (-not (Test-Path "apps\soki-code-web\node_modules")) {
    throw "Soki Code web dependencies are missing. Re-run the installer."
}

$apiProcess = $null
$webProcess = $null
$apiPort = 8000
$webPort = 5173
$apiReused = Test-SokiApi $apiPort
$webReused = $false

try {
    if (-not $apiReused) {
        if (Test-Port $apiPort) {
            $apiPort = Get-FreePort 8001
        }
        $env:PYTHONPATH = "packages/shared/src;apps/api/src"
        $env:QFORGE_DEMO_MODE = "false"
        $logDirectory = Join-Path $env:TEMP "soki-code"
        New-Item -ItemType Directory -Force $logDirectory | Out-Null
        $apiProcess = Start-Process `
            -FilePath $uvCommand.Source `
            -ArgumentList @(
                "run", "uvicorn", "qforge_api.main:app",
                "--host", "0.0.0.0", "--port", "$apiPort"
            ) `
            -WorkingDirectory $projectDirectory `
            -RedirectStandardOutput (Join-Path $logDirectory "api.log") `
            -RedirectStandardError (Join-Path $logDirectory "api-error.log") `
            -PassThru `
            -WindowStyle Hidden
        for ($attempt = 0; $attempt -lt 240; $attempt++) {
            if (Test-SokiApi $apiPort) { break }
            if ($apiProcess.HasExited) { break }
            Start-Sleep -Milliseconds 125
        }
        if (-not (Test-SokiApi $apiPort)) {
            throw "Soki Code API failed to start. Logs: $logDirectory"
        }
    }

    if ($apiPort -eq 8000) {
        $webReused = Test-SokiWeb $webPort
    }
    if (-not $webReused) {
        if (Test-Port $webPort) {
            $webPort = Get-FreePort 5174
        }
        $previousApiUrl = $env:VITE_API_URL
        $env:VITE_API_URL = "http://127.0.0.1:$apiPort"
        $webProcess = Start-Process `
            -FilePath $npmCommand.Source `
            -ArgumentList @(
                "run", "dev", "--prefix", "apps/soki-code-web",
                "--", "--host", "127.0.0.1", "--port", "$webPort"
            ) `
            -WorkingDirectory $projectDirectory `
            -PassThru
        $env:VITE_API_URL = $previousApiUrl
        for ($attempt = 0; $attempt -lt 160; $attempt++) {
            if (Test-SokiWeb $webPort) { break }
            if ($webProcess.HasExited) { break }
            Start-Sleep -Milliseconds 125
        }
        if (-not (Test-SokiWeb $webPort)) {
            throw "Soki Code web app failed to start."
        }
    }

    $desktopUrl = "http://127.0.0.1:$webPort"
    Start-Process $desktopUrl
    Write-Host "  web      $desktopUrl"
    Write-Host "  api      http://127.0.0.1:$apiPort"
    Write-Host "  agent    local automation - guarded approvals"
    Write-Host "  trading  research + paper only"
    Write-Host ""

    if ($null -eq $apiProcess -and $null -eq $webProcess) {
        Write-Host "Soki Code is already running."
        exit 0
    }
    Write-Host "Keep this terminal open. Press Ctrl+C to stop Soki Code."
    while (
        ($null -ne $apiProcess -and -not $apiProcess.HasExited) -or
        ($null -ne $webProcess -and -not $webProcess.HasExited)
    ) {
        Start-Sleep -Milliseconds 500
    }
}
finally {
    if ($null -ne $webProcess) { Stop-ProcessTree $webProcess }
    if ($null -ne $apiProcess) { Stop-ProcessTree $apiProcess }
}
