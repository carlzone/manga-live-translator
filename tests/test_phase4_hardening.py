import runpy
from pathlib import Path

from manga_live_translator.config import CaptionRegion, ReadingDirection
from manga_live_translator.diagnostics import RuntimeDiagnostics

TOOL = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tools" / "verify_release.py"))
REQUIRED_DOCUMENTS = TOOL["REQUIRED_DOCUMENTS"]
verify = TOOL["verify"]


def test_diagnostics_are_bounded_and_exclude_content() -> None:
    diagnostics = RuntimeDiagnostics(maximum_samples=2)
    for value in (0.1, 0.2, 0.3):
        diagnostics.record_viewport(
            ocr_seconds=value,
            translation_seconds=value / 2,
            completion_seconds=value * 2,
            translated_blocks=2,
            failed_blocks=1,
        )
    region = CaptionRegion("Display", 1920, 1080, 1.5, 0, 0, 100, 200)
    report = diagnostics.report(
        region=region,
        reading_direction=ReadingDirection.MANGA_RTL,
        state="Ready",
        overlay_geometry=(-100, 50, 100, 200),
        overlay_scale=(2 / 3, 2 / 3),
        rendered_boxes=2,
        collision_adjustments=1,
    )
    assert len(diagnostics._ocr_seconds) == 2
    assert "logical 100x200" in report and "physical 150x300" in report
    assert "manga_rtl" in report and "failed blocks: 3" in report
    assert "boxes 2; collision adjustments 1" in report
    assert "captured pixels, recognized text, or translations" in report


def test_scroll_diagnostics_record_motion_and_safe_clears() -> None:
    diagnostics = RuntimeDiagnostics()
    diagnostics.record_scroll(physical_dy=-30, logical_dy=-20, confidence=0.8)
    diagnostics.record_scroll(physical_dy=0, logical_dy=0, confidence=0.1, cleared=True)
    diagnostics.record_clean_frame_drain()
    diagnostics.record_post_render_rebase()
    report = diagnostics.report(
        region=None, reading_direction=ReadingDirection.WEBTOON_LTR, state="Moving"
    )
    assert "cumulative -20.0px" in report
    assert "low-confidence clears 1" in report
    assert "drained frames 1; prevented feedback scans 1" in report


def test_release_verifier_rejects_weights_and_accepts_documented_build(tmp_path: Path) -> None:
    (tmp_path / "MangaLiveTranslator.exe").write_bytes(b"executable")
    for name in REQUIRED_DOCUMENTS:
        (tmp_path / name).write_text(name, encoding="utf-8")
    report, errors = verify(tmp_path)
    assert not errors and report["valid"]
    (tmp_path / "accidental-model.onnx").write_bytes(b"weights")
    report, errors = verify(tmp_path)
    assert errors and not report["valid"]
