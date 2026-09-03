param([switch]$IncludeTranslation, [switch]$Force)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$modelRoot = Join-Path $projectRoot "models"
$ocrManifest = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot "ocr_models.json") | ConvertFrom-Json

New-Item -ItemType Directory -Force -Path (Join-Path $modelRoot "ocr") | Out-Null
foreach ($file in $ocrManifest.files) {
    $destination = Join-Path $modelRoot "ocr\$($file.name)"
    if ($Force -or -not (Test-Path -LiteralPath $destination)) {
        Invoke-WebRequest -Uri $file.url -OutFile $destination
    }
    $actual = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $file.sha256) { throw "SHA-256 mismatch for $destination" }
}

if ($IncludeTranslation) {
    foreach ($command in @("ct2-transformers-converter", "huggingface-cli")) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "Required translation conversion command is unavailable: $command"
        }
    }
    $manifest = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot "translation_models.json") | ConvertFrom-Json
    foreach ($model in $manifest.models) {
        $snapshot = Join-Path $projectRoot "build\model-source\$($model.language)-en"
        $destination = Join-Path $modelRoot "translation\$($model.language)-en"
        if ((Test-Path $destination) -and -not $Force) {
            Write-Output "Translation model already exists: $destination"
            continue
        }
        huggingface-cli download $model.source --revision $model.revision --local-dir $snapshot
        ct2-transformers-converter --model $snapshot --output_dir $destination --quantization int8 --force
    }
}

python (Join-Path $PSScriptRoot "model_preflight.py")
if ($LASTEXITCODE -ne 0) { throw "Model preflight failed" }
