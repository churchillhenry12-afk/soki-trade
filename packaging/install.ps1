$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$sokiRepository = "https://github.com/churchillhenry12-afk/soki-trade.git"
$sokiRef = if ($env:SOKI_REF) { $env:SOKI_REF } else { "main" }
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
$sokiAppDirectory = Join-Path $sokiRoot "app"
$sokiDataDirectory = Join-Path $sokiRoot "data"
$hermesHome = Join-Path $sokiRoot "runtime\hermes"
$hermesDirectory = Join-Path $hermesHome "hermes-agent"

$hermesTag = "v2026.7.20"
$hermesCommit = "3ef6bbd201263d354fd83ec55b3c306ded2eb72a"
$hermesInstallerUrl = (
    "https://raw.githubusercontent.com/NousResearch/hermes-agent/" +
    "$hermesTag/scripts/install.ps1"
)
$hermesInstallerSha256 = "b5bdf0e959677de0168f8cfb5f9175c7b57adf5c4319a1c2fc9bec1f46fbdb6e"

$temporaryDirectory = Join-Path $env:TEMP ("soki-code-" + [Guid]::NewGuid().ToString("N"))
$hermesInstaller = Join-Path $temporaryDirectory "hermes-install.ps1"

function Find-SokiCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [string[]] $Candidates
    )
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }
    foreach ($candidate in $Candidates) {
        if (Test-Path $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Command,
        [Parameter(Mandatory = $true)]
        [string[]] $CommandArguments
    )
    & $Command @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE."
    }
}

function New-RuntimeKey {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

try {
    New-Item -ItemType Directory -Force -Path $temporaryDirectory | Out-Null
    New-Item -ItemType Directory -Force -Path $sokiRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $sokiBinDirectory | Out-Null
    New-Item -ItemType Directory -Force -Path $sokiDataDirectory | Out-Null

    Write-Host ""
    Write-Host "  S O K I   C O D E" -ForegroundColor Magenta
    Write-Host "  local automation - guarded trading"
    Write-Host ""
    Write-Host "Installing one product: Soki Code with its automation runtime."

    Write-Host "Downloading the verified Soki automation runtime..."
    Invoke-WebRequest -Uri $hermesInstallerUrl -OutFile $hermesInstaller -UseBasicParsing
    $actualSha256 = (
        Get-FileHash -Path $hermesInstaller -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $hermesInstallerSha256) {
        throw "Hermes installer checksum verification failed. Nothing was executed."
    }

    $env:HERMES_HOME = $hermesHome
    & $hermesInstaller `
        -Branch $hermesTag `
        -InstallDir $hermesDirectory `
        -HermesHome $hermesHome `
        -SkipSetup `
        -NonInteractive

    # Hermes intentionally points uv at its own venv while it installs. Since
    # PowerShell child scripts can leave environment variables in this process,
    # clear that internal build context before syncing the separate Soki app.
    Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue
    Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
    $gitCommand = Find-SokiCommand -Name "git" -Candidates @(
        (Join-Path $hermesHome "git\cmd\git.exe"),
        (Join-Path $hermesHome "git\bin\git.exe"),
        (Join-Path $hermesHome "bin\git.exe")
    )
    if (-not $gitCommand) {
        $gitCommand = Get-ChildItem `
            -Path $hermesHome `
            -Filter "git.exe" `
            -File `
            -Recurse `
            -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $gitCommand) {
        throw "The bundled runtime could not provide Git."
    }
    $installedHermesCommit = (
        & $gitCommand -C $hermesDirectory rev-parse HEAD
    ).Trim()
    if ($LASTEXITCODE -ne 0 -or $installedHermesCommit -ne $hermesCommit) {
        throw "The downloaded Hermes runtime did not match the pinned commit."
    }

    Write-Host "Installing Soki Code..."
    if (Test-Path (Join-Path $sokiAppDirectory ".git") -PathType Container) {
        Invoke-Checked -Command $gitCommand -CommandArguments @(
            "-C", $sokiAppDirectory, "fetch", "--depth", "1", "origin", $sokiRef
        )
        Invoke-Checked -Command $gitCommand -CommandArguments @(
            "-C", $sokiAppDirectory, "checkout", "-B", "soki-installed", "FETCH_HEAD"
        )
    }
    else {
        if (Test-Path $sokiAppDirectory) {
            throw "$sokiAppDirectory already exists but is not a Soki installation."
        }
        Invoke-Checked -Command $gitCommand -CommandArguments @(
            "clone", "--depth", "1", "--branch", $sokiRef,
            $sokiRepository, $sokiAppDirectory
        )
    }

    $uvCommand = Find-SokiCommand -Name "uv" -Candidates @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe"),
        (Join-Path $hermesHome "bin\uv.exe")
    )
    if (-not $uvCommand) {
        $uvCommand = Get-ChildItem `
            -Path $hermesHome `
            -Filter "uv.exe" `
            -File `
            -Recurse `
            -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $uvCommand) {
        throw "The bundled runtime could not provide uv."
    }

    $npmCommand = Find-SokiCommand -Name "npm.cmd" -Candidates @(
        (Join-Path $hermesHome "node\npm.cmd"),
        (Join-Path $hermesHome "nodejs\npm.cmd"),
        (Join-Path $hermesHome "bin\npm.cmd")
    )
    if (-not $npmCommand) {
        $npmCommand = Get-ChildItem `
            -Path $hermesHome `
            -Filter "npm.cmd" `
            -File `
            -Recurse `
            -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $npmCommand) {
        throw "The bundled runtime could not provide Node.js/npm."
    }

    $hermesCommand = @(
        (Join-Path $hermesDirectory "venv\Scripts\hermes.exe"),
        (Join-Path $hermesDirectory ".venv\Scripts\hermes.exe"),
        (Join-Path $hermesHome "bin\hermes.exe")
    ) |
        Where-Object { Test-Path $_ -PathType Leaf } |
        Select-Object -First 1
    if (-not $hermesCommand) {
        $hermesCommand = Get-ChildItem `
            -Path $hermesDirectory `
            -Filter "hermes.exe" `
            -File `
            -Recurse `
            -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $hermesCommand) {
        throw "The bundled Hermes executable was not found."
    }

    Push-Location $sokiAppDirectory
    try {
        Invoke-Checked -Command $uvCommand -CommandArguments @("sync")
        Invoke-Checked -Command $npmCommand -CommandArguments @(
            "ci", "--prefix", "apps/soki-code-web"
        )
    }
    finally {
        Pop-Location
    }

    $runtimeKey = $null
    $hermesEnvironment = Join-Path $hermesHome ".env"
    if (Test-Path $hermesEnvironment) {
        $keyLine = Get-Content $hermesEnvironment |
            Where-Object { $_ -match "^API_SERVER_KEY=" } |
            Select-Object -Last 1
        if ($keyLine) {
            $runtimeKey = ($keyLine -replace "^API_SERVER_KEY=", "").Trim("'`"")
        }
    }
    if (-not $runtimeKey) {
        $runtimeKey = New-RuntimeKey
    }

    Invoke-Checked -Command $hermesCommand -CommandArguments @(
        "config", "set", "API_SERVER_ENABLED", "true"
    )
    Invoke-Checked -Command $hermesCommand -CommandArguments @(
        "config", "set", "API_SERVER_HOST", "127.0.0.1"
    )
    Invoke-Checked -Command $hermesCommand -CommandArguments @(
        "config", "set", "API_SERVER_KEY", $runtimeKey
    )
    Invoke-Checked -Command $hermesCommand -CommandArguments @(
        "tools", "enable", "--platform", "api_server", "computer_use"
    )
    & $hermesCommand tools post-setup cua_driver
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Computer-control support will finish installing during Soki setup."
    }
    & $hermesCommand gateway restart
    if ($LASTEXITCODE -ne 0) {
        Invoke-Checked -Command $hermesCommand -CommandArguments @("gateway", "install")
        Invoke-Checked -Command $hermesCommand -CommandArguments @("gateway", "start")
    }

    $databasePath = (Join-Path $sokiDataDirectory "qforge.db").Replace("\", "/")
    $launcherPath = Join-Path $sokiBinDirectory "soki-code.cmd"
    $launcher = @(
        "@echo off",
        "set `"HERMES_HOME=$hermesHome`"",
        "set `"HERMES_BIN=$hermesCommand`"",
        "set `"QFORGE_DATABASE_URL=sqlite:///$databasePath`"",
        "set `"QFORGE_PROVIDER_CONFIG_PATH=$(Join-Path $sokiDataDirectory 'provider-config.json')`"",
        "set `"QFORGE_GATEWAY_CONFIG_PATH=$(Join-Path $sokiDataDirectory 'gateway-config.json')`"",
        "set `"QFORGE_MARKET_DATA_DIRECTORY=$(Join-Path $sokiDataDirectory 'market')`"",
        "set `"QFORGE_HERMES_CONFIG_PATH=$(Join-Path $sokiDataDirectory 'hermes-config.json')`"",
        "set `"QFORGE_ATTACHMENT_DIRECTORY=$(Join-Path $sokiDataDirectory 'attachments')`"",
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$sokiAppDirectory\soki.ps1`" %*"
    ) -join "`r`n"
    [IO.File]::WriteAllText(
        $launcherPath,
        $launcher + "`r`n",
        [Text.UTF8Encoding]::new($false)
    )
    Copy-Item -Force $launcherPath (Join-Path $sokiBinDirectory "soki-trade.cmd")

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $userEntries = @($userPath -split ";" | Where-Object { $_ })
    if ($userEntries -notcontains $sokiBinDirectory) {
        $newUserPath = if ([String]::IsNullOrWhiteSpace($userPath)) {
            $sokiBinDirectory
        }
        else {
            "$sokiBinDirectory;$userPath"
        }
        [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    }
    if (@($env:Path -split ";") -notcontains $sokiBinDirectory) {
        $env:Path = "$sokiBinDirectory;$env:Path"
    }

    Write-Host ""
    Write-Host "Soki Code installed successfully." -ForegroundColor Green
    Write-Host "Start it with:"
    Write-Host "  soki-code"
    Write-Host ""
    Write-Host "Open a new PowerShell window if this one does not recognize the command."
}
finally {
    if (Test-Path $temporaryDirectory) {
        Remove-Item -Recurse -Force $temporaryDirectory
    }
}
