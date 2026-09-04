param([switch]$SkipRelease)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $SkipRelease) {
    & (Join-Path $PSScriptRoot "build-release.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Release build failed" }
}

$compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($null -eq $compiler) {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    $compilerPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
} else {
    $compilerPath = $compiler.Source
}

if (-not $compilerPath) {
    throw "Inno Setup 6 was not found. Install it with: winget install --id JRSoftware.InnoSetup --exact"
}

& $compilerPath (Join-Path $root "installer\MangaLiveTranslator.iss")
if ($LASTEXITCODE -ne 0) { throw "Installer compilation failed" }

$installer = Join-Path $root "dist\installer\MangaLiveTranslator-0.1.0-setup.exe"
if (-not (Test-Path -LiteralPath $installer)) { throw "Installer output was not created" }
$hash = Get-FileHash -LiteralPath $installer -Algorithm SHA256
Write-Host "Installer created at $installer"
Write-Host "SHA-256: $($hash.Hash.ToLowerInvariant())"
