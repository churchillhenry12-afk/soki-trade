$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDirectory

$mode = "desktop"
$launcherArguments = @()
if ($args.Count -gt 0) {
    if ($args[0] -in @("desktop", "web", "terminal")) {
        $mode = [string] $args[0]
        if ($args.Count -gt 1) {
            $launcherArguments = @($args[1..($args.Count - 1)])
        }
    }
    else {
        # Flags such as --check belong to the terminal client.
        $mode = "terminal"
        $launcherArguments = @($args)
    }
}

Write-Host ""
Write-Host "  S O K I   C O D E" -ForegroundColor Magenta
Write-Host "  local automation - guarded trading" -ForegroundColor DarkGray
Write-Host ""

if ($mode -in @("desktop", "web")) {
    & (Join-Path $projectDirectory "infrastructure\scripts\run.ps1") @launcherArguments
    exit 0
}

function Test-SokiApi {
    try {
        $health = Invoke-RestMethod `
            -Uri "http://127.0.0.1:8000/health" `
            -TimeoutSec 2
        return $health.status -eq "ok" -and $null -ne $health.runtime
    }
    catch {
        return $false
    }
}

function Get-Port8000Owner {
    try {
        return Get-NetTCPConnection `
            -LocalPort 8000 `
            -State Listen `
            -ErrorAction Stop |
            Select-Object -First 1
    }
    catch {
        return $null
    }
}

function Get-WindowsProcessInfo([int] $ownerProcessId) {
    try {
        return Get-CimInstance `
            -ClassName Win32_Process `
            -Filter "ProcessId = $ownerProcessId" `
            -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Stop-WindowsProcessTree([int] $ownerProcessId) {
    & taskkill.exe /PID $ownerProcessId /T /F 2>$null | Out-Null
}

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $uvCommand) {
    Write-Error "Soki Code needs uv. Re-run the official Soki Code installer."
    exit 1
}

if (-not (Test-Path (Join-Path $projectDirectory ".venv\Scripts\python.exe"))) {
    Write-Host "Preparing Soki Code for first launch..."
    & $uvCommand.Source sync
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to prepare the Soki Code Python environment."
    }
}

$apiStarted = $false
$apiProcess = $null
$apiListenerProcessId = $null
$previousPythonPath = $env:PYTHONPATH
$previousDemoMode = $env:QFORGE_DEMO_MODE

try {
    $apiReady = Test-SokiApi

    if (-not $apiReady) {
        $existingListener = Get-Port8000Owner
        if ($null -ne $existingListener) {
            $existingProcessId = [int] $existingListener.OwningProcess
            $existingProcess = Get-WindowsProcessInfo $existingProcessId
            $existingCommandLine = if ($null -ne $existingProcess) {
                [string] $existingProcess.CommandLine
            }
            else {
                ""
            }
            if ($existingCommandLine -match "qforge_api\.main:app") {
                Write-Host "Removing a stale Soki Code API process..."
                Stop-WindowsProcessTree $existingProcessId
                for ($attempt = 0; $attempt -lt 50; $attempt++) {
                    Start-Sleep -Milliseconds 100
                    if ($null -eq (Get-Port8000Owner)) {
                        break
                    }
                }
            }
            else {
                $existingProcessName = if ($null -ne $existingProcess) {
                    [string] $existingProcess.Name
                }
                else {
                    "unknown process"
                }
                throw (
                    "Port 8000 is already used by $existingProcessName " +
                    "(PID $existingProcessId). Close that application, then run soki-code again."
                )
            }
        }

        $env:PYTHONPATH = "packages/shared/src;apps/api/src"
        $env:QFORGE_DEMO_MODE = "false"
        $logDirectory = Join-Path $env:TEMP "soki-code"
        $apiOutputLog = Join-Path $logDirectory "api.log"
        $apiErrorLog = Join-Path $logDirectory "api-error.log"
        New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
        Remove-Item -Force $apiOutputLog, $apiErrorLog -ErrorAction SilentlyContinue
        $apiProcess = Start-Process `
            -FilePath $uvCommand.Source `
            -ArgumentList @(
                "run",
                "uvicorn",
                "qforge_api.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000"
            ) `
            -WorkingDirectory $projectDirectory `
            -RedirectStandardOutput $apiOutputLog `
            -RedirectStandardError $apiErrorLog `
            -PassThru `
            -WindowStyle Hidden
        $apiStarted = $true

        for ($attempt = 0; $attempt -lt 240; $attempt++) {
            Start-Sleep -Milliseconds 125
            if (Test-SokiApi) {
                $apiReady = $true
                break
            }
            if ($apiProcess.HasExited) {
                break
            }
        }

        if ($apiReady) {
            $startedListener = Get-Port8000Owner
            if ($null -ne $startedListener) {
                $apiListenerProcessId = [int] $startedListener.OwningProcess
            }
        }

        if (-not $apiReady) {
            Write-Host ""
            Write-Host "Soki Code API startup diagnostics" -ForegroundColor Red
            if (Test-Path $apiErrorLog) {
                Write-Host "--- api-error.log ---"
                Get-Content -Path $apiErrorLog -Tail 100
            }
            if (Test-Path $apiOutputLog) {
                Write-Host "--- api.log ---"
                Get-Content -Path $apiOutputLog -Tail 100
            }
            throw "Soki Code API failed to start after 30 seconds."
        }
    }

    Write-Host "Starting soki code"
    Write-Host "One terminal - one agent conversation - /setup for connections - /help for commands"
    Write-Host "Real candles download automatically. Live execution remains disabled."
    Start-Sleep -Milliseconds 400

    $env:PYTHONPATH = "packages/shared/src;apps/terminal-tui/src"
    $terminalArguments = @("run", "python", "-m", "qforge_tui.main") + $launcherArguments
    & $uvCommand.Source @terminalArguments
}
finally {
    if ($apiStarted) {
        if ($null -ne $apiListenerProcessId) {
            Stop-WindowsProcessTree $apiListenerProcessId
        }
        elseif ($null -ne $apiProcess -and -not $apiProcess.HasExited) {
            Stop-WindowsProcessTree $apiProcess.Id
        }
    }
    $env:PYTHONPATH = $previousPythonPath
    $env:QFORGE_DEMO_MODE = $previousDemoMode
}
