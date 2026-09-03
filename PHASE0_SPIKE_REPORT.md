# Phase 0 Secondary-Monitor Spike

Status: passed on 2026-09-03

Target display: `MYS240` (1920×1080, device-pixel ratio 1.0)

The automated fixture spike rendered two horizontal Japanese lines on the physical secondary
display and captured the 700×300 region at `(100, 100)` through the Windows GDI provider.

- OCR: RapidOCR 3.9.2 / PP-OCRv6 small, CPU; 0.285 seconds.
- Translation: CTranslate2 OPUS-MT ja-en int8, revision `0770961`, CPU.
- `こんにちは` → `Hello.` (99.983% confidence, 0.090 seconds).
- `新しい世界` → `A new world.` (99.992% confidence, 0.073 seconds).
- Detected blocks: 2; rendered result-panel blocks: 2.
- Failure behavior verified separately by unit tests and model preflight.

Machine-readable measurements are generated at `build/phase0-spike.json`. The user-driven
workflow remains available through Select Region followed by Scan Once.
