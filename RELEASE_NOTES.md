# MangaLiveTranslator 0.1.0 — Phase 4

- The translation display now exactly overlays the selected reader region and positions one
  opaque white English box over each successfully translated OCR polygon.
- Boxes expand below, above, or horizontally, clamp to the region, avoid collisions where
  possible, and shrink text only as a fallback.
- The overlay is frameless, always on top, click-through, and excluded from Windows capture.
- Existing boxes follow confidently detected vertical scrolling and clear on ambiguous motion or
  as soon as the next settled scan starts.
- Fixed an overlay feedback loop by rebasing the first post-render frame and draining clean
  captures for at least 400 ms after hiding boxes before every automatic or manual OCR scan.
- Windows display-affinity exclusion now uses typed 64-bit handles, verifies the applied mode,
  and reports failures without being required for correct scanning.
- Chinese selections now enforce left-to-right webtoon ordering; right-to-left is Japanese-only.
- Application-wide start/pause, rescan, copy, clear, and overlay visibility shortcuts.
- Privacy-safe CPU, memory, latency, display/DPI, failure, and stability diagnostics.
- Verified model-free PyInstaller workflow, privacy statement, and Page2X release checklist.
- Selectable Auto, Japanese manga right-to-left, and Webtoon/manhwa reading modes.
- Geometry-aware grouping with fragment provenance and compatible-script checks.
- Opt-in vertical Japanese and Chinese crop rotation with confidence-based candidate selection.
- Project-created layout fixtures and an offline quality-gate benchmark.

- Independent manga-only package derived from VideoLiveTranslator.
- DPI-aware multi-monitor reader-region selection and preview.
- Persistent Start/Pause runtime with immediate manual rescanning and Clear controls.
- Continuous 5 FPS viewport monitoring with motion detection and a 400 ms settle interval.
- Generation-aware latest-only inference that prevents obsolete results from changing the UI.
- Normalized-text translation caching and geometry-aware duplicate suppression across scrolling.
- Stable-ID reconciliation updates retained overlay boxes without displaying obsolete blocks.
- Horizontal multi-block Japanese, Simplified Chinese, and Traditional Chinese OCR with
  deterministic top-to-bottom/left-to-right ordering and offline English translation.
- Block-local translation errors that do not discard successful results from the viewport.
- Backward-compatible migration of Phase 0's generic Chinese setting.
- External, preflight-verified RapidOCR and CTranslate2 models.
- Audio capture, VAD, Whisper, and hybrid modes are intentionally absent.
