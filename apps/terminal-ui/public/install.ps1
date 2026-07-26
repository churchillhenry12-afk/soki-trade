$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$releaseUrl = (
    "https://github.com/churchillhenry12-afk/soki-trade/" +
    "releases/download/v0.1.0/soki-trade-0.1.0.tar.gz"
)
$releaseSha256 = "887cd40d0b67a3e9362072ade97cff8617b90d51bf2b30cdf4470c701a749f53"
$publicOrigin = "https://soki-trade-agent.vercel.app"
$installDirectory = if ($env:SOKI_INSTALL_DIR) {
    $env:SOKI_INSTALL_DIR
}
else {
    Join-Path $env:LOCALAPPDATA "SokiTrade"
}
$binDirectory = if ($env:SOKI_BIN_DIR) {
    $env:SOKI_BIN_DIR
}
else {
    Join-Path $env:USERPROFILE ".local\bin"
}
$temporaryDirectory = Join-Path $env:TEMP ("soki-trade-" + [Guid]::NewGuid().ToString("N"))
$archivePath = Join-Path $temporaryDirectory "soki-trade.tar.gz"

try {
    New-Item -ItemType Directory -Force -Path $temporaryDirectory | Out-Null
    New-Item -ItemType Directory -Force -Path $installDirectory | Out-Null
    New-Item -ItemType Directory -Force -Path $binDirectory | Out-Null

    $tarCommand = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($null -eq $tarCommand) {
        throw "Windows tar.exe is required. Install current Windows updates and retry."
    }

    Write-Host "Downloading Soki Trade..."
    Invoke-WebRequest -Uri $releaseUrl -OutFile $archivePath -UseBasicParsing

    $actualSha256 = (Get-FileHash -Path $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $releaseSha256) {
        throw "Release checksum verification failed. Nothing was installed."
    }

    & $tarCommand.Source -xzf $archivePath -C $installDirectory --strip-components 1
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to unpack the verified Soki Trade release."
    }

    $environmentFile = Join-Path $installDirectory ".env"
    if (-not (Test-Path $environmentFile)) {
        New-Item -ItemType File -Path $environmentFile | Out-Null
    }
    $environmentContent = Get-Content -Path $environmentFile -Raw -ErrorAction SilentlyContinue
    if ($environmentContent -notmatch "(?m)^QFORGE_CORS_ORIGINS=") {
        $corsLine = (
            "QFORGE_CORS_ORIGINS=http://127.0.0.1:5173," +
            "http://localhost:5173,$publicOrigin"
        )
        [IO.File]::AppendAllText(
            $environmentFile,
            $corsLine + [Environment]::NewLine,
            [System.Text.UTF8Encoding]::new($false)
        )
    }

    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($null -eq $uvCommand) {
        Write-Host "Installing the uv Python runtime manager from Astral..."
        Invoke-RestMethod "https://astral.sh/uv/install.ps1" | Invoke-Expression
        $env:Path = (
            (Join-Path $env:USERPROFILE ".local\bin") + ";" +
            (Join-Path $env:USERPROFILE ".cargo\bin") + ";" +
            $env:Path
        )
        $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    }
    if ($null -eq $uvCommand) {
        throw "uv was installed but could not be found. Open a new PowerShell window and retry."
    }

    Write-Host "Preparing the Soki Trade runtime..."
    Push-Location $installDirectory
    try {
        & $uvCommand.Source sync
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to prepare the Soki Trade Python environment."
        }
    }
    finally {
        Pop-Location
    }

    $launcherPath = Join-Path $binDirectory "soki-trade.cmd"
    $powershellLauncher = (
        "@echo off`r`n" +
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " +
        "`"$installDirectory\soki.ps1`" %*`r`n"
    )
    [IO.File]::WriteAllText(
        $launcherPath,
        $powershellLauncher,
        [System.Text.UTF8Encoding]::new($false)
    )

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $userPathEntries = @($userPath -split ";" | Where-Object { $_ })
    if ($userPathEntries -notcontains $binDirectory) {
        $newUserPath = if ([String]::IsNullOrWhiteSpace($userPath)) {
            $binDirectory
        }
        else {
            "$binDirectory;$userPath"
        }
        [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    }
    if (@($env:Path -split ";") -notcontains $binDirectory) {
        $env:Path = "$binDirectory;$env:Path"
    }

    Write-Host ""
    Write-Host "Soki Trade installed successfully." -ForegroundColor Green
    Write-Host "Start it with:"
    Write-Host "  soki-trade"
    Write-Host ""
    Write-Host "If this window does not recognize the new command, open a new PowerShell window."
}
finally {
    if (Test-Path $temporaryDirectory) {
        Remove-Item -Recurse -Force $temporaryDirectory
    }
}
