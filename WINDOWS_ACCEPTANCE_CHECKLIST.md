# Windows Phase 4 Acceptance Checklist

Record Windows version, CPU, memory, displays/scales, viewport dimensions, model revisions, and
`build/release-verification.json` with each signed-off run.

## Automated gates

- [ ] Tests, Ruff, and strict mypy pass.
- [ ] `tools/build-release.ps1` produces and verifies `dist/release/MangaLiveTranslator.exe`.
- [ ] Release verification confirms all documents and zero bundled model weights.
- [ ] `tools/model_preflight.py --model-dir <bundle>` validates any optional bundle separately.
- [ ] The Phase 3 layout benchmark passes.

## Windows and Page2X

- [ ] Launches on supported 64-bit Windows 10 and 11 without a source checkout.
- [ ] Missing models show actionable errors and the runtime remains restartable.
- [ ] Select/preview works on each monitor; Diagnostics reports matching logical/physical size and DPI.
- [ ] A resolution or scale change invalidates the saved region.
- [ ] Japanese and both Chinese choices translate offline; Japanese supports each reading mode.
- [ ] Simplified and Traditional Chinese force and lock left-to-right ordering; Japanese retains
      explicit right-to-left ordering, while Han-only Auto text stays left-to-right.
- [ ] Scanning waits during motion and submits within 600 ms plus capture/queue delay after settling.
- [ ] Partial scrolls retain translations without false-merging repeated dialogue.
- [ ] During vertical scrolling, boxes follow content in both directions, disappear beyond the
      region, and clear immediately when tracking confidence is insufficient.
- [ ] Accepting a settled scan or requesting a manual rescan clears old boxes before processing.
- [ ] On a stationary page, translated boxes remain visible without periodic clearing,
      regeneration, or OCR of their own English text.
- [ ] Diagnostics reports capture-affinity verification, post-render rebases, clean-frame drains,
      and prevented feedback scans.
- [ ] Start/pause, rescan, copy, clear, and show/hide shortcuts work.
- [ ] The transparent overlay exactly matches the selected region on primary, secondary, and
      mixed-DPI displays, including negative global monitor coordinates.
- [ ] White boxes cover their OCR source, expand without leaving the region, and avoid source and
      translation collisions where geometry permits.
- [ ] The overlay is click-through, absent from the taskbar, and excluded from captured frames.
- [ ] Font size and box opacity restore after restart; show/hide does not affect scanning.
- [ ] Copy All contains the currently visible translations in reading order.
- [ ] One failed translation does not remove other successful blocks.

## Performance and stability

- [ ] At 1920x1080 and up to 12 blocks, record median/p95; median is below 3 seconds on reference CPU.
- [ ] `tools/benchmark_session.py` and a 10-minute real-reader sequence keep memory, UI
      responsiveness, and capacity-one queues bounded.
- [ ] Five start/stop cycles release workers/models; application close leaves no live workers.
- [ ] Diagnostics contains no pixels, source text, or translation text.
- [ ] No application network traffic occurs; only explicit model preparation accesses the network.
