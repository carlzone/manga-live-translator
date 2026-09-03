# Windows Phase 0 Acceptance Checklist

- [ ] Launches on Windows 10/11 with no VideoLiveTranslator path on `PYTHONPATH`.
- [ ] Both displays are enumerated and a region can be selected on `MYS240`.
- [ ] Preview matches the selected physical pixels at the saved DPI.
- [ ] Model preflight validates all OCR and translation assets.
- [ ] One scan recognizes at least two horizontal Japanese or Chinese blocks.
- [ ] Each block is translated offline and rendered with confidence and coordinates.
- [ ] Stop closes the worker and the application exits without a hanging thread.
- [ ] Results and measurements are recorded in `PHASE0_SPIKE_REPORT.md`.
