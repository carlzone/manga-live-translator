$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$modelRoot = Join-Path $root "models"
$stage = Join-Path $root "build\model-bundle"
$archive = Join-Path $root "dist\MangaLiveTranslator-0.1.0-models.zip"

Set-Location $root
uv run python tools/model_preflight.py --model-dir $modelRoot
if ($LASTEXITCODE -ne 0) { throw "Model preflight failed" }

$resolvedRoot = [System.IO.Path]::GetFullPath($root).TrimEnd('\')
$resolvedStage = [System.IO.Path]::GetFullPath($stage)
if (-not $resolvedStage.StartsWith("$resolvedRoot\", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Invalid model bundle staging path"
}
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $stage "models") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage "manifests") | Out-Null

Copy-Item -LiteralPath (Join-Path $modelRoot "ocr") -Destination (Join-Path $stage "models") -Recurse
Copy-Item -LiteralPath (Join-Path $modelRoot "translation") -Destination (Join-Path $stage "models") -Recurse
Copy-Item -LiteralPath "EXTERNAL_MODEL_NOTICES.md" -Destination $stage
Copy-Item -LiteralPath "HOW_TO_INSTALL.md" -Destination $stage
Copy-Item -LiteralPath "docs\MODEL_PREPARATION.md" -Destination $stage
Copy-Item -LiteralPath "tools\ocr_models.json" -Destination (Join-Path $stage "manifests")
Copy-Item -LiteralPath "tools\translation_models.json" -Destination (Join-Path $stage "manifests")

uv run python tools/model_preflight.py --model-dir (Join-Path $stage "models") --output (Join-Path $stage "MODEL_HASHES.json")
if ($LASTEXITCODE -ne 0) { throw "Staged model verification failed" }

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $archive) | Out-Null
if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
Compress-Archive -Path "$stage\*" -DestinationPath $archive -CompressionLevel Optimal

$hash = Get-FileHash -LiteralPath $archive -Algorithm SHA256
Write-Host "External model bundle created at $archive"
Write-Host "SHA-256: $($hash.Hash.ToLowerInvariant())"
