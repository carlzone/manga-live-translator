# MangaLiveTranslator

MangaLiveTranslator is an offline-first Windows desktop application for reading manga, manhwa,
and manhua in English. It captures a user-selected area of the screen, recognizes Japanese,
Simplified Chinese, or Traditional Chinese text, translates each detected block locally, and
places the English translation directly over the source text.

The translation layer is a transparent, always-on-top, click-through window with the same
position and dimensions as the selected capture region. Each successful translation is rendered
in an opaque white box centered on its OCR polygon. Boxes expand symmetrically where possible,
remain inside the capture region, and avoid other source and translation boxes when space allows.
The control window can move independently from the overlay.

No screen captures, recognized text, or translations are sent to a remote service. OCR and
translation models are external local assets and are deliberately excluded from source control
and packaged releases.

## Features

- Selected-region capture on Windows, including secondary monitors and negative monitor origins.
- Per-monitor DPI-aware coordinate conversion for mixed-scale displays.
- Japanese, Simplified Chinese, Traditional Chinese, and automatic source-language selection.
- Japanese right-to-left manga ordering and left-to-right webtoon/manhwa ordering.
- Chinese is always processed left-to-right, including migrated or invalid persisted settings.
- Automatic layout selection uses Japanese right-to-left order only when kana is detected;
  Han-only automatic results remain left-to-right.
- Coordinate-aligned, centered translation boxes with wrapping, padding, edge clamping,
  collision avoidance, and minimum-font fallback.
- Automatic scanning after the viewport settles and manual rescanning on demand.
- Live vertical scroll tracking that moves existing boxes with their source content and removes
  boxes after they leave the selected region.
- Overlay-safe capture: labels are hidden and clean frames are drained before OCR, preventing
  translations from being detected as page changes or OCR input.
- Stable block reconciliation and an in-memory translation cache for overlapping viewports.
- Click-through overlay, adjustable text size and box opacity, copy, clear, and show/hide actions.
- Privacy-safe diagnostics containing geometry, timing, reading-order, tracking, and capture-
  exclusion data without captured pixels or recognized/translated text.

## How it works

The capture worker samples the selected region at 5 FPS. A settling controller distinguishes a
stable page from scrolling or unrelated motion. Once the page has remained stable for 400 ms,
the visible labels are synchronously hidden and two newly composed frames are drained before the
latest clean frame is submitted to OCR.

RapidOCR performs detection and recognition with local ONNX models. The layout processor filters
and orders blocks according to the selected language and reading mode. CTranslate2 then runs local
int8 OPUS-MT models and returns one English result per block. Successful blocks are positioned in
the overlay; blank and failed translations leave the original content visible.

Windows display-affinity capture exclusion is enabled and verified when supported, but it is only
an optimization. Correctness does not depend on that API because the clean-capture handshake keeps
visible translations out of OCR.

## Using the application

1. Choose the source language. Japanese allows every reading mode; either Chinese option forces
   **Webtoon/manhwa** and disables the reading-order selector.
2. Select **Select Region**, then drag over the page area to monitor. Use **Preview Region** to
   confirm the selection.
3. Select **Start**. The models load once, the initial viewport is scanned, and later scans occur
   after scrolling settles.
4. Adjust **Text size** and **Box opacity** as needed. These values and the selected region persist
   between launches.
5. Use **Rescan** for a fresh scan, **Clear** to remove results, **Copy All** to copy translations
   in resolved reading order, **Show / Hide Overlay** to control visibility, and **Pause** to stop
   capture and release the runtime.

Keyboard shortcuts:

| Action | Shortcut |
| --- | --- |
| Start or pause | `Ctrl+Alt+S` |
| Rescan | `Ctrl+Alt+R` |
| Copy all translations | `Ctrl+Alt+C` |
| Clear translations | `Ctrl+Alt+X` |
| Show or hide overlay | `Ctrl+Alt+H` |

Vertical CJK recognition is experimental and disabled by default. During confidently detected
vertical scrolling, boxes follow their source content. Ambiguous, horizontal, excessive, or
low-confidence motion clears the boxes to avoid leaving translations in incorrect locations.

## Requirements

- Windows 10 or Windows 11, 64-bit.
- Python 3.12 (the project requires `>=3.12,<3.13`).
- [uv](https://docs.astral.sh/uv/) for dependency and virtual-environment management.
- PowerShell for the model and release scripts.
- Sufficient disk space for the virtual environment, external models, and the self-contained
  PyInstaller build.

The application requires local OCR and translation assets to perform real scans. Unit tests do
not require those assets because inference boundaries are mocked.

## Developer setup

From a PowerShell terminal in the repository root:

```powershell
uv sync
```

This creates `.venv`, installs the locked runtime and development dependencies from `uv.lock`, and
installs the project entry point. Confirm the environment with:

```powershell
uv run python --version
uv run manga-live-translator
```

The application can also be started through the repository entry module:

```powershell
uv run python app.py
```

Running without valid external models opens the control UI, but starting a scan reports the
missing model assets.

## Model setup

Download and verify the pinned OCR assets:

```powershell
.\tools\download-models.ps1
```

To also download and convert the pinned Japanese-to-English and Chinese-to-English translation
models, install the Hugging Face CLI and the Transformers dependencies required by
`ct2-transformers-converter`, ensure both commands are on `PATH`, then run:

```powershell
.\tools\download-models.ps1 -IncludeTranslation
```

The script verifies OCR SHA-256 hashes and performs a model preflight. Existing files are retained
unless `-Force` is supplied. Models can also be prepared manually using the pinned repositories,
revisions, licenses, and conversion settings in `tools/ocr_models.json` and
`tools/translation_models.json`.

Expected runtime layout:

```text
models/
  ocr/
    PP-OCRv6_det_small.onnx
    PP-OCRv6_rec_small.onnx
    ppocrv6_dict.txt
    ch_ppocr_mobile_v2.0_cls_mobile.onnx
  translation/
    ja-en/
      model.bin
      config.json
      source.spm
      target.spm
    zh-en/
      model.bin
      config.json
      source.spm
      target.spm
```

Validate prepared assets and optionally save the report:

```powershell
uv run python tools/model_preflight.py
uv run python tools/model_preflight.py --output build/model-preflight.json
uv run python tools/verify_translation_models.py
```

For more detail, see [Model Preparation](docs/MODEL_PREPARATION.md) and
[Source Provenance](SOURCE_PROVENANCE.md).

## Tests and quality checks

Run the complete unit and integration suite:

```powershell
uv run pytest
```

Pytest automatically measures `manga_live_translator` coverage and fails below 85%. The suite uses
Qt's offscreen platform and mocks OCR/translation inference, so it can run on a development machine
without downloading model weights.

Run an individual file or test while developing:

```powershell
uv run pytest tests/test_coordinate_overlay.py
uv run pytest tests/test_coordinate_overlay.py::test_layout_expands_around_source_center_when_unconstrained
```

If Windows has left an inaccessible pytest temporary directory, use a project-local temporary
base and disable pytest's cache provider:

```powershell
uv run pytest -p no:cacheprovider --basetemp .test-tmp
```

Run static checks independently:

```powershell
uv run ruff check .
uv run mypy
```

`mypy` runs in strict mode against the application package. Ruff checks Python 3.12 code for
style, import, modernization, and bug-prone patterns.

The recommended pre-release sequence is:

```powershell
uv run pytest
uv run ruff check .
uv run mypy
```

## Model-dependent acceptance benchmarks

After model preflight succeeds, run the real inference benchmarks:

```powershell
uv run python tools/benchmark_ocr.py
uv run python tools/benchmark_translation.py
```

The OCR benchmark requires a supported CJK Windows font and writes
`build/ocr-benchmark.json`. The translation benchmark writes
`build/translation-benchmark.json`. Both return a nonzero exit code when their acceptance criteria
are not met.

The layout benchmark is offline and does not require model weights:

```powershell
uv run python tools/benchmark_phase3_layout.py --output build/layout-benchmark.json
```

Run the bounded long-session diagnostic gate for ten minutes, or use a shorter duration during
development:

```powershell
uv run python tools/benchmark_session.py
uv run python tools/benchmark_session.py --duration 30
```

Manual Windows and mixed-DPI acceptance checks are documented in
[WINDOWS_ACCEPTANCE_CHECKLIST.md](WINDOWS_ACCEPTANCE_CHECKLIST.md).

## Building and verifying a release

The release script runs pytest, Ruff, strict mypy, PyInstaller, and release verification:

```powershell
.\tools\build-release.ps1
```

Create the Windows installer after installing Inno Setup 6:

```powershell
.\tools\build-installer.ps1
```

That command builds and verifies a fresh release before compiling the installer. When the release
has already been built, use `.\tools\build-installer.ps1 -SkipRelease`.

Outputs:

- `dist/MangaLiveTranslator.exe` — the PyInstaller executable.
- `dist/release/` — the executable plus release, privacy, license, and acceptance documents.
- `dist/MangaLiveTranslator-0.1.0-portable.zip` — the portable, model-free release.
- `dist/installer/MangaLiveTranslator-0.1.0-setup.exe` — the per-user Windows installer.
- `build/release-verification.json` — executable size, SHA-256 checksum, model-exclusion result,
  and any validation errors.

Model weights must remain external and are intentionally not copied into the release. To use the
packaged executable, place the `models` directory beside `MangaLiveTranslator.exe`. The installer
creates the expected empty model directories under the installation folder and adds Start Menu
and optional desktop shortcuts. Verify a release directory independently with:

```powershell
uv run python tools/verify_release.py dist/release
```

Build the separately distributed external-model archive after preparing the models:

```powershell
.\tools\build-model-bundle.ps1
```

This produces `dist/MangaLiveTranslator-0.1.0-models.zip`, including the required folder layout,
hash report, source manifests, and attribution notice. For a portable installation, extract the
portable application ZIP and model ZIP into the same directory. For the standard installer,
install the application first and extract the model ZIP into:

```text
%LOCALAPPDATA%\Programs\MangaLiveTranslator
```

After extraction, `MangaLiveTranslator.exe` and the `models` directory must be immediate siblings.
See [How to Install](HOW_TO_INSTALL.md) for step-by-step portable and installer instructions.

## Project structure

```text
src/manga_live_translator/
  config/             Persisted settings and validation
  ocr/                RapidOCR adapter and manga layout processing
  screen/             Display discovery, capture, settling, and scroll tracking
  text_translation/   CTranslate2 translation adapter
  ui/                 Control window, region tools, and translation overlay
  workers/            Persistent scan worker and generation-aware messages
tests/                 Unit, integration, UI, lifecycle, and hardening tests
tools/                 Model, benchmark, build, and release-verification utilities
```

User settings and rotating logs are stored in the platform-specific local application-data
directory named `MangaLiveTranslator`. Logs rotate at 2 MiB with three backups and do not include
captured images or recognized/translated text.

## Privacy and limitations

Screen pixels, recognized text, and translations stay on the local machine. The running
application performs no network requests; only the explicit model-download script accesses the
network. See [PRIVACY.md](PRIVACY.md) for the complete policy.

The first release positions rectangular boxes from OCR geometry rather than detecting speech-
bubble contours. A long English translation can therefore cover nearby artwork. Vertical tracking
only models vertical movement, and uncertain motion intentionally clears results. Translation
quality and resource usage depend on the external models and the host CPU.

License and bundled dependency notices are documented in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
