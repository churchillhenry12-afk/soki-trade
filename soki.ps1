$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDirectory

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

function Get-WindowsProcessInfo([int] $processId) {
    try {
        return Get-CimInstance `
            -ClassName Win32_Process `
            -Filter "ProcessId = $processId" `
            -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Stop-WindowsProcessTree([int] $processId) {
    & taskkill.exe /PID $processId /T /F 2>$null | Out-Null
}

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $uvCommand) {
    Write-Error "Soki Trade needs uv. Re-run the official Soki Trade installer."
    exit 1
}

if (-not (Test-Path (Join-Path $projectDirectory ".venv\Scripts\python.exe"))) {
    Write-Host "Preparing Soki Trade for first launch..."
    & $uvCommand.Source sync
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to prepare the Soki Trade Python environment."
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
                Write-Host "Removing a stale Soki Trade API process..."
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
                    "(PID $existingProcessId). Close that application, then run soki-trade again."
                )
            }
        }

        $env:PYTHONPATH = "packages/shared/src;apps/api/src"
        $env:QFORGE_DEMO_MODE = "false"
        $logDirectory = Join-Path $env:TEMP "soki-trade"
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
                "127.0.0.1",
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
            Write-Host "Soki Trade API startup diagnostics" -ForegroundColor Red
            if (Test-Path $apiErrorLog) {
                Write-Host "--- api-error.log ---"
                Get-Content -Path $apiErrorLog -Tail 100
            }
            if (Test-Path $apiOutputLog) {
                Write-Host "--- api.log ---"
                Get-Content -Path $apiOutputLog -Tail 100
            }
            throw "Soki Trade API failed to start after 30 seconds."
        }
    }

    Write-Host "Starting Soki Trade"
    Write-Host "One terminal - one agent conversation - /setup for connections - /help for commands"
    Write-Host "Real candles download automatically. Live execution remains disabled."
    Start-Sleep -Milliseconds 400

    $env:PYTHONPATH = "packages/shared/src;apps/terminal-tui/src"
    $terminalArguments = @("run", "python", "-m", "qforge_tui.main") + $args
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
