# MangaLiveTranslator 0.1.0

This is the first public release of MangaLiveTranslator, an offline Windows application that
recognizes Japanese and Chinese text in a selected manga, manhwa, or manhua reader region and
places English translations directly over the source text.

## Highlights

- Local Japanese, Simplified Chinese, and Traditional Chinese OCR and English translation.
- Coordinate-aligned white translation boxes centered over detected source text.
- Symmetric box expansion, text wrapping, edge clamping, collision avoidance, and font fallback.
- Japanese right-to-left manga ordering and left-to-right webtoon/manhwa ordering.
- Chinese always uses left-to-right ordering; automatic mode uses right-to-left only when
  Japanese kana is detected.
- Automatic rescanning after scrolling settles, with manual rescan support.
- Live vertical tracking moves visible translations with the page during confident scrolling.
- Overlay-safe capture prevents displayed translations from triggering rescans or entering OCR.
- Click-through, always-on-top overlay that supports mixed-DPI and multi-monitor configurations.
- Adjustable font size and box opacity, copy, clear, pause, and show/hide controls.
- Privacy-safe diagnostics for capture, OCR, translation, layout, and scroll tracking.

## Downloads

Two archives are required for portable use:

1. `MangaLiveTranslator-0.1.0-portable.zip` contains the Windows application and documentation.
2. `MangaLiveTranslator-0.1.0-models.zip` contains the external OCR and translation models.

Extract both archives into the same directory. `MangaLiveTranslator.exe` and the `models`
directory must be immediate siblings. See `HOW_TO_INSTALL.md` inside either archive for complete
instructions.

The optional `MangaLiveTranslator-0.1.0-setup.exe` provides a per-user Windows installation, but
the separate model archive is still required. The installer is unsigned, so Windows SmartScreen
may display a warning.

## Privacy and model distribution

The application performs OCR and translation locally. It does not upload screen captures,
recognized text, or translations. Model weights are distributed separately to preserve their
manifests, hashes, licenses, and attribution notices.

## Known limitations

- Translation boxes are based on OCR rectangles rather than speech-bubble contours, so long
  translations may cover nearby artwork.
- Vertical OCR remains experimental and is disabled by default.
- Scroll tracking models vertical movement only; ambiguous or horizontal motion clears boxes.
- Translation quality and processing speed depend on the supplied models and host CPU.
- The application and installer are currently unsigned.

## Verification

This release passed 53 automated tests with 91.13% coverage, Ruff checks, strict mypy checks,
PyInstaller packaging, model preflight, and model-exclusion verification for the application
archive.
