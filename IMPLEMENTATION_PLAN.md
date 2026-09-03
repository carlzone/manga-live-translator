# MangaLiveTranslator Implementation Plan

## 1. Product goal

Build an offline-first Windows desktop application that continuously translates Japanese,
Simplified Chinese, or Traditional Chinese text visible inside a user-selected manga/manhwa
reader region. The first target is browser-based scrolling readers such as Page2X.

The user selects the reading viewport once. While the user scrolls, the application detects
when the visible content has settled, captures the selected region, recognizes all useful text,
translates it to English, and displays the results in a readable always-on-top panel.

MangaLiveTranslator will reuse proven components from `F:\Projects\MangaLiveTranslator`, but
will be maintained as a separate application and Python package.

## 2. First-release scope

### Included

- Windows 10/11, 64-bit.
- Rectangular region selection on any connected monitor.
- Saved and previewable capture region with DPI/resolution validation.
- Continuous capture of a vertically scrolling browser reader.
- Scroll/motion detection followed by a short settle interval before OCR.
- Japanese, Simplified Chinese, and Traditional Chinese OCR.
- Horizontal Chinese and Japanese text for the baseline release.
- Experimental vertical Japanese text handling.
- Translation to English using local CTranslate2 models.
- Translation of multiple visible text blocks per settled viewport.
- Japanese manga and manhwa/webtoon reading-order modes.
- Duplicate suppression across overlapping scroll positions.
- Fixed translation panel below, beside, or independently positioned from the reader.
- Manual rescan, pause/resume, clear, and copy controls.
- Local processing with no captured images or text uploaded by default.

### Deferred

- Replacing text inside speech bubbles.
- Perfectly anchoring English text beneath every bubble.
- Cloud translation providers.
- Mobile platforms and browser extensions.
- OCR of handwritten or highly stylized sound effects with guaranteed accuracy.

## 3. Reuse strategy

Copy source files into the new repository, preserve their applicable notices/history in
documentation, rename the package to `manga_live_translator`, and then adapt them. Do not make
MangaLiveTranslator import runtime code directly from the MangaLiveTranslator working tree.

### Reuse with small changes

| Existing area | Source | Planned use |
|---|---|---|
| Application shell | `src/manga_live_translator/app.py` | Startup, Qt lifecycle, error handling |
| Settings | `src/manga_live_translator/config/` | New manga settings and migration-safe persistence |
| Region selection | `src/manga_live_translator/ui/region_selector.py` | Select the reader viewport |
| Region preview | `src/manga_live_translator/ui/region_preview.py` | Preview crop and OCR blocks |
| Screen capture | `src/manga_live_translator/screen/` | DPI-aware repeated viewport capture |
| OCR types/runtime | `src/manga_live_translator/ocr/engine.py`, `rapidocr_engine.py` | Preserve text boxes, confidence, and inference; replace subtitle selection in `ocr/processing.py` |
| Text translation | `src/manga_live_translator/text_translation/engine.py`, `ctranslate2_engine.py` | Local ja-en and zh-en translation; retain asset validation and Auto script routing |
| Workers/messages | `src/manga_live_translator/workers/` | Non-blocking bounded OCR/translation jobs |
| Overlay foundation | `src/manga_live_translator/ui/overlay.py` (`SubtitleOverlay`) | Basis for the translation panel and click-through behavior |
| Packaging/tooling | `pyproject.toml`, build scripts, model tools | Rename and remove audio-only dependencies |

### Exclude from the initial fork

- System-audio capture and device selection.
- VAD, Whisper, speech segmentation, and audio translation workers.
- Hybrid audio/OCR arbitration.
- Build output, virtual environments, caches, logs, and downloaded model binaries.

## 4. Key architectural changes

The existing OCR path is subtitle-oriented: it selects the lowest centered OCR group and joins
it into one caption. Manga mode must retain every accepted OCR block and its bounding box.

```text
Selected reader region
        -> low-cost frame comparison
        -> scrolling / stable state machine
        -> settled-frame snapshot
        -> OCR and text-block filtering
        -> orientation and reading-order classification
        -> per-block or grouped translation jobs
        -> cross-frame duplicate reconciliation
        -> ordered translation panel
```

Introduce these domain objects:

- `MangaTextBlock`: source text, confidence, polygon, orientation, stable block ID.
- `ViewportSnapshot`: pixels, capture time, region metadata, visual fingerprint.
- `TranslatedBlock`: source block plus translated English and translation status.
- `ReadingDirection`: `manga_rtl`, `webtoon_ltr`, and `automatic`.
- `ViewportState`: `moving`, `settling`, `processing`, and `stable`.

### 4.1 Proven baseline contracts

The fork is based on the current MangaLiveTranslator implementation, not a hypothetical
interface. Preserve these contracts unless a manga-specific test requires a change:

- Python 3.12, PySide6, RapidOCR 3.9 through ONNX Runtime, and CTranslate2 4.x.
- `CapturedFrame` contains BGRA pixels, width, height, stride, capture time, and the saved
  `CaptionRegion`; coordinates are logical screen-relative values and are converted using the
  selected display's device-pixel ratio.
- `RapidOcrEngine` validates four external OCR assets before loading and returns
  `OcrTextBlock` values with four-point boxes and confidence scores. Manga processing must
  replace `select_subtitle_blocks`, not alter the capture or model adapter contract.
- `CTranslate2TextEngine` expects `models/translation/ja-en/` and `zh-en/`, loads both models
  once per session, uses CPU int8 inference, and routes Han-only Auto text to Chinese.
- Capture, OCR, and translation workers use bounded capacity-one queues that replace stale
  work. Manga generation IDs must extend this behavior so stale results cannot update the UI.
- Stop order is producer before consumer, followed by queue clearing and model close. Every
  start/stop path must remain restartable and must not leave worker threads running.

### 4.2 Required technical decisions

These decisions are part of the implementation contract:

- **Model inventory:** use the existing RapidOCR PP-OCRv6 small assets and the existing pinned
  OPUS-MT `ja-en` and `zh-en` CTranslate2 assets. Copy their manifests, model cards, hashes,
  and preparation scripts into the new repository; do not download at runtime. Traditional
  Chinese uses the existing `zh-en` model in the first release, with no claim of separate
  Traditional-Chinese model quality.
- **Capture:** retain the Windows GDI provider and Qt logical-coordinate validation initially.
  The application must set one explicit DPI-awareness mode at startup, record logical and
  physical dimensions in diagnostics, and reject a saved region when monitor identity,
  resolution, or scale changes.
- **Sampling:** capture at 5 FPS by default. A frame is `moving` when the downscaled grayscale
  difference is at least `0.015`; it enters `settling` after the first low-difference sample and
  becomes eligible for OCR after 400 ms of uninterrupted low-difference samples. Any changed
  sample resets the timer. Only one OCR submission may be active per generation.
- **Generation:** increment the generation on every accepted settled snapshot and on manual
  rescan. OCR and translation messages carry the generation and are ignored unless it is still
  current. Pause and stop invalidate the current generation before clearing queues.
- **Block identity:** store polygon coordinates normalized to the captured frame dimensions.
  Match an incoming block first by comparison key plus normalized center/size tolerance, then by
  estimated vertical scroll displacement. A repeated comparison key is a new instance when no
  geometry match exists. Translation cache keys are `(source_language, comparison_key)` and are
  not the identity of a visible block.
- **Layout baseline:** Phase 1 accepts horizontal blocks only. Vertical Japanese detection and
  rotated-crop recognition are opt-in experimental behavior in Phase 3, not a baseline release
  guarantee. Reading mode controls ordering; automatic mode must expose its selected result in
  diagnostics.
- **Failure behavior:** a missing or invalid model, capture failure, OCR failure, or translation
  failure produces an actionable status while preserving the ability to stop and restart. A
  failed block must not prevent other blocks in the same viewport from being displayed.

### 4.3 Phase 0 model and repository deliverables

Phase 0 is complete only when the new repository contains the executable preparation and
verification path, not just copied Python modules:

- A manga-specific `pyproject.toml`, entry point, package metadata, and lock file with audio,
  VAD, Whisper, and PyAudio dependencies removed.
- A `models/` layout and manifests for the four RapidOCR assets and both CTranslate2 model
  directories, including pinned upstream revisions, licenses, model cards, and SHA-256 output.
- Ported downloader/conversion/verification tooling that never runs from the application and
  never downloads assets at runtime.
- A model preflight command and readable UI errors for missing or invalid OCR and translation
  assets. Unit tests must use fake assets or mocked runtimes; real model benchmarks are a
  separate opt-in check.
- A minimal end-to-end spike: select a real region on a secondary monitor, capture one frame,
  recognize at least two horizontal blocks, translate them offline, and render them in the panel.
  Record dimensions, DPI, model revisions, latency, and failure behavior. If this spike cannot
  pass on CPU-only Windows hardware, revise the model or viewport assumptions before Phase 1.

## 5. Functional requirements

| ID | Requirement |
|---|---|
| MLT-001 | Select, preview, persist, and validate one screen rectangle. |
| MLT-002 | Capture only the selected rectangle without blocking the UI. |
| MLT-003 | Avoid OCR while the selected content is actively scrolling. |
| MLT-004 | Start OCR after the viewport remains sufficiently stable for a configurable interval. |
| MLT-005 | Preserve all useful OCR blocks rather than selecting a subtitle-like bottom line. |
| MLT-006 | Filter browser chrome and unrelated text by keeping capture strictly within the region. |
| MLT-007 | Order Japanese manga blocks top-to-bottom and right-to-left where appropriate. |
| MLT-008 | Order manhwa/webtoon blocks primarily top-to-bottom. |
| MLT-009 | Translate each block independently so one OCR error does not corrupt the page. |
| MLT-010 | Do not retranslate unchanged blocks retained after a partial scroll. |
| MLT-011 | Cancel or discard obsolete OCR/translation results after a newer viewport is accepted. |
| MLT-012 | Display source and English text in an ordered, scrollable translation panel. |
| MLT-013 | Retain recent translations while the reader moves, subject to a bounded history. |
| MLT-014 | Provide pause/resume, rescan, clear, copy, and show/hide hotkeys. |
| MLT-015 | Keep images, OCR text, and translations on the device by default. |

## 6. Scroll and duplicate handling

Use a two-stage comparison to keep CPU use bounded:

1. Downscale the selected region to grayscale and calculate a fast difference score.
2. When the score stays below the motion threshold for 400 ms, submit the latest full-resolution
  frame to OCR. The default comparison rate is 5 FPS, and a changed sample resets the settle
  timer.

Every submitted viewport receives a monotonically increasing generation number. Workers may
finish old jobs, but the UI discards results from obsolete generations.

For overlapping scroll positions, match blocks using normalized source text plus approximate
geometry or image-strip movement. Cache translations by normalized text and language. Identical
text at a plausible shifted position reuses its translation; repeated dialogue at clearly
different locations remains representable as a separate block.

The 5 FPS comparison rate and 400 ms settle interval are initial defaults, not promises of
reader-independent latency. Measure them on representative viewport sizes and retain at most one
full OCR pass per stable viewport.

## 7. OCR and reading order

Replace `select_subtitle_blocks` with manga-oriented processing:

- Reject empty and low-confidence blocks.
- Preserve polygons returned by RapidOCR.
- Detect likely horizontal versus vertical blocks from geometry and character layout.
- For experimental vertical text, rotate cropped candidates and compare OCR confidence.
- Merge fragments only when their proximity, alignment, orientation, and language are compatible.
- Apply configurable reading order after detection, without destroying original coordinates.

Automatic reading order can use language, column geometry, and layout, but the UI must allow the
user to choose Japanese manga (right-to-left) or webtoon/manhwa (top-to-bottom) explicitly.

## 8. User interface

The main window should provide:

- Source language: Auto, Japanese, Simplified Chinese, Traditional Chinese. Both Chinese options
  use the existing `zh-en` model in the first release and are retained as user intent/metadata;
  they do not imply separate model quality.
- Reading mode: Auto, Japanese manga, Webtoon/manhwa.
- Select Region and Preview Region.
- Start/Pause, Rescan, Clear History.
- Translation panel position, font size, opacity, and click-through settings.
- Status such as Waiting for scroll to stop, Reading, Translating, and Ready.

The translation panel should initially show ordered cards containing optional source text and
English translation. It should remain usable when many bubbles are visible and must not replace
all content every time a small scroll occurs.

## 9. Delivery phases

### Phase 0 - Repository bootstrap

- Create the `MangaLiveTranslator` package/repository structure.
- Copy only reusable source, tests, fixtures, notices, and model tooling.
- Rename package, entry point, application identifiers, paths, and release metadata.
- Remove audio dependencies and prove a clean launch with tests, Ruff, and strict mypy.
- Complete the model/repository deliverables and the secondary-monitor end-to-end spike defined
  in section 4.3.

Exit criterion: the renamed application launches and the baseline region/OCR/translation tests
pass independently of the MangaLiveTranslator source tree.

### Phase 1 - Selected-region reader MVP

- Adapt region selection, validation, preview, and capture.
- Add a translation panel capable of displaying multiple ordered blocks.
- Process all horizontal OCR blocks in a manually selected viewport.
- Add Start, Pause, Rescan, and Clear.

Exit criterion: a static Japanese or Chinese comic viewport can be selected and translated into
ordered English entries without audio components.

### Phase 2 - Scrolling automation

- Implement frame fingerprints and the motion/settle state machine.
- Add generation-based stale-result rejection.
- Add normalized text translation caching and cross-scroll duplicate suppression.
- Preserve a bounded translation history.

Exit criterion: normal Page2X scrolling triggers one useful OCR cycle after each settled scroll
and does not repeatedly append the same visible dialogue.

### Phase 3 - Manga layout quality

- Implement Japanese right-to-left and webtoon ordering.
- Add block grouping and bubble-fragment heuristics.
- Add experimental vertical Japanese crop rotation and confidence selection.
- Build synthetic and permissively licensed fixture sets for representative layouts.

Exit criterion: benchmark fixtures meet agreed block detection, reading-order, and translation
quality thresholds.

### Phase 4 - UX and release hardening

- Add keyboard shortcuts, panel placement, copy actions, and clear diagnostics.
- Measure CPU, memory, settle latency, OCR latency, and long-session stability.
- Package the application without model weights; verify optional model bundles separately.
- Complete licensing, privacy, release notes, and Windows acceptance checks.

Exit criterion: a reproducible Windows build passes automated tests and a Page2X-focused manual
acceptance checklist.

## 10. Test plan

- Unit tests for frame-difference thresholds, state transitions, reading order, block grouping,
  normalization, cache keys, and duplicate reconciliation.
- Worker tests for bounded queues, cancellation, stale generations, restart, and shutdown.
- Integration sequences representing stationary pages, continuous scrolling, small scrolls with
  overlap, quick direction reversals, blank gutters, and browser overlays.
- OCR fixtures covering horizontal Japanese, vertical Japanese, Simplified Chinese, Traditional
  Chinese, multiple bubbles, and stylized fonts. Use only project-created or licensed assets.
- UI tests for saved regions, monitor changes, preview, panel history, hotkeys, and error states.
- Performance benchmarks on CPU-only hardware with recorded viewport dimensions.

### 10.1 Quantitative release gates

Record the fixture set, hardware, model revisions, and test command with every result. Initial
gates are deliberately modest and can be tightened after real-reader measurements:

- Horizontal fixture block recall is at least 90% at confidence threshold 0.75; no fixture may
  lose more than one accepted block solely because another block is present.
- Reading-order accuracy is at least 95% on labeled Japanese manga and webtoon fixture sets.
- Duplicate reconciliation produces zero false merges for repeated identical dialogue in separate
  locations and at most 5% duplicate entries on the partial-scroll integration sequence.
- After scrolling stops, the first OCR submission begins within 600 ms plus capture and queue
  delay; no more than one OCR pass is accepted for the same stable generation.
- The panel remains responsive while OCR and translation run; the bounded-queue test must show
  no unbounded growth across a 10-minute synthetic session.
- On the reference CPU-only machine, median settled-viewport completion is below 3 seconds for
  a 1920x1080 capture containing up to 12 horizontal blocks. Record p95 separately rather than
  hiding slow layouts behind the median.
- Five consecutive start/stop cycles release workers and model objects, and application close
  leaves no live worker threads or child processes.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Vertical or stylized Japanese OCR is weak | Crop/rotate candidates, expose source text, allow rescan, document limitations |
| Reading order is ambiguous | Provide explicit manga/webtoon modes and preserve coordinates |
| OCR runs continuously during scrolling | Cheap motion detection and settle debounce before full inference |
| Partial scrolling repeats translations | Geometry-aware reconciliation plus a normalized-text cache |
| A large viewport makes OCR slow | Bounded queues, stale generation rejection, optional viewport downscaling/tiling |
| Translation lacks dialogue context | Translate compatible grouped blocks and later add an optional context window |
| Overlay obstructs artwork | Default to a separate side/bottom panel with configurable opacity and click-through |

## 12. Initial acceptance scenario

1. Open a Japanese or Chinese Page2X title in a browser.
2. Launch MangaLiveTranslator and select only the visible reader column.
3. Choose the source language and manga/webtoon reading mode.
4. Start scanning and verify the initial settled viewport is translated.
5. Scroll by part of a page and stop.
6. Verify scanning waits during movement, translates newly visible blocks after settling, and
   does not duplicate blocks still visible from the previous viewport.
7. Pause, manually rescan, copy a translation, clear history, and stop cleanly.

## 13. Recommended first implementation task

Bootstrap the repository from the reusable screen/OCR/text-translation subset, remove all audio
code and dependencies, and establish passing renamed baseline tests. After that clean boundary is
in place, implement the multi-block data model and translation panel before adding automatic
scroll detection.

