$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$release = Join-Path $root "dist\release"

Set-Location $root
uv run pytest
uv run ruff check .
uv run mypy
uv run pyinstaller --clean --noconfirm MangaLiveTranslator.spec

New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item "dist\MangaLiveTranslator.exe" $release
Copy-Item README.md, RELEASE_NOTES.md, PRIVACY.md, THIRD_PARTY_NOTICES.md, WINDOWS_ACCEPTANCE_CHECKLIST.md $release
uv run python tools/verify_release.py $release --output "build\release-verification.json"

Write-Host "Release verified at $release. Model weights are intentionally excluded."

