$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$release = Join-Path $root "dist\release"

Set-Location $root
uv run pytest
if ($LASTEXITCODE -ne 0) { throw "Test suite failed" }
uv run ruff check .
if ($LASTEXITCODE -ne 0) { throw "Ruff failed" }
uv run mypy
if ($LASTEXITCODE -ne 0) { throw "mypy failed" }
uv run pyinstaller --clean --noconfirm MangaLiveTranslator.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item "dist\MangaLiveTranslator.exe" $release
Copy-Item README.md, HOW_TO_INSTALL.md, RELEASE_NOTES.md, PRIVACY.md, THIRD_PARTY_NOTICES.md, WINDOWS_ACCEPTANCE_CHECKLIST.md, SOURCE_PROVENANCE.md $release
New-Item -ItemType Directory -Force -Path (Join-Path $release "docs") | Out-Null
Copy-Item "docs\MODEL_PREPARATION.md" (Join-Path $release "docs")
uv run python tools/verify_release.py $release --output "build\release-verification.json"
if ($LASTEXITCODE -ne 0) { throw "Release verification failed" }

$portableArchive = Join-Path $root "dist\MangaLiveTranslator-0.1.0-portable.zip"
if (Test-Path -LiteralPath $portableArchive) { Remove-Item -LiteralPath $portableArchive -Force }
Compress-Archive -Path "$release\*" -DestinationPath $portableArchive -CompressionLevel Optimal

Write-Host "Release verified at $release and portable archive created at $portableArchive. Model weights are intentionally excluded."
