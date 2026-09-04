# MangaLiveTranslator

MangaLiveTranslator is an offline-first Windows desktop application that captures a selected
reader region, recognizes Japanese or Chinese text, and translates each detected block to
English. Translations appear in white boxes directly over their source text inside a transparent,
click-through overlay matching the selected region. Scanning waits for scrolling to settle and
preserves duplicate suppression across overlapping viewports.

## Reader workflow

1. Select and preview the reader region.
2. Choose the source language and Auto, Japanese manga, or Webtoon/manhwa layout. Auto selects
   manga ordering for Japanese multi-column geometry and webtoon ordering otherwise. Both
   Chinese choices use the same first-release `zh-en` model and always use left-to-right webtoon
   ordering; right-to-left ordering is restricted to Japanese text.
3. Select **Start** to load the local models and begin monitoring at 5 FPS. The initial viewport
   and each later scroll are processed after 400 ms of visual stability.
4. Use **Rescan** to process the latest frame immediately, **Clear** to remove displayed boxes,
   **Copy All** to copy English results, and **Pause** to stop monitoring and release the runtime.

Box font size and opacity persist between launches. Keyboard shortcuts are `Ctrl+Alt+S`
start/pause, `Ctrl+Alt+R` rescan, `Ctrl+Alt+C` copy, `Ctrl+Alt+X` clear, and `Ctrl+Alt+H`
show/hide overlay. Diagnostics exclude captured content and text.

Every accepted viewport replaces the visible overlay boxes. Boxes cover the recognized source
polygon, expand within the selected region for longer English text, and avoid other source and
translation boxes where space permits. Failed translations do not cover their source. Overlapping
dialogue is matched by normalized text and geometry, and successful translations are cached for
the application session. Vertical CJK recognition remains experimental and disabled by default.
During confidently detected vertical scrolling, visible boxes follow their source content and are
removed after leaving the selected region. Ambiguous or non-vertical motion clears them rather
than leaving translations at incorrect positions. Boxes are also cleared as soon as the next
settled scan or a manual rescan begins.
Before OCR, the app hides all boxes and waits for freshly composed screen captures, preventing the
overlay from being recognized as page movement or translated as part of the manga. Windows capture
exclusion is verified when supported, but scanning remains safe if it is unavailable.

## Development

Requires Python 3.12 and `uv`.

```powershell
uv sync
uv run python tools/model_preflight.py
uv run manga-live-translator
uv run pytest
uv run ruff check .
uv run mypy
./tools/build-release.ps1
```

Models are external and are never downloaded by the application. See
[`docs/MODEL_PREPARATION.md`](docs/MODEL_PREPARATION.md). Run
`uv run python tools/benchmark_phase3_layout.py` for the offline layout acceptance benchmark.
The build workflow packages without model weights and records an executable checksum. Validate an
optional bundle independently with `uv run python tools/model_preflight.py --model-dir <bundle>`.
Use `uv run python tools/benchmark_session.py` for the 10-minute bounded-session gate (or pass a
shorter `--duration` during development); live OCR/translation timings are available in Diagnostics.

## Privacy

Screen pixels, recognized text, and translations remain local. The application performs no
network requests. The explicit model preparation script is the only download path.
See [`PRIVACY.md`](PRIVACY.md) for details.
