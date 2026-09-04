"""Phase 0 manga-specific runtime and UI tests."""

import json
import time
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QGroupBox, QLabel

from manga_live_translator.config import (
    AppSettings,
    CaptionRegion,
    ReadingDirection,
    SettingsStore,
    SourceLanguage,
)
from manga_live_translator.ocr import OcrResult, OcrTextBlock
from manga_live_translator.screen import (
    CapturedFrame,
    ScreenDescriptor,
    ViewportSnapshot,
    fingerprint_frame,
)
from manga_live_translator.text_translation import TextTranslationResult
from manga_live_translator.ui.main_window import MainWindow
from manga_live_translator.ui.panel import TranslationPanel
from manga_live_translator.ui.region_selector import region_from_points
from manga_live_translator.workers.scan import TranslatedBlock, ViewportTranslation


def test_settings_round_trip_and_validation(tmp_path: Path) -> None:
    region = CaptionRegion("MYS240", 1920, 1080, 1.0, 100, 100, 800, 700)
    settings = AppSettings(caption_region=region, source_language=SourceLanguage.JAPANESE)
    store = SettingsStore(tmp_path / "settings.json")
    store.save(settings)
    assert store.load() == settings


def test_settings_migrates_phase0_chinese_value(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"source_language": "zh"}), encoding="utf-8")
    assert SettingsStore(path).load().source_language is SourceLanguage.SIMPLIFIED_CHINESE


def test_panel_adds_and_clears_multiple_results(qt_app: object) -> None:
    panel = TranslationPanel()
    box = ((1.0, 2.0), (30.0, 2.0), (30.0, 20.0), (1.0, 20.0))
    first = TranslatedBlock(OcrTextBlock("one", 0.9, box), "First", SourceLanguage.JAPANESE, 0.1)
    second = TranslatedBlock(
        OcrTextBlock("two", 0.8, box),
        "Second",
        SourceLanguage.SIMPLIFIED_CHINESE,
        0.2,
    )
    panel.set_results(ViewportTranslation((first, second), 0.2, 0.3), show_source=False)
    assert panel.blocks == [first, second]
    assert panel.results_layout.count() == 3
    failure = TranslatedBlock(
        OcrTextBlock("failed", 0.9, box),
        None,
        SourceLanguage.JAPANESE,
        0.0,
        "fixture error",
    )
    panel.set_results(ViewportTranslation((failure,), 0.1, 0.0))
    assert panel.blocks == [failure]
    label = panel.results_layout.itemAt(0).widget()
    assert isinstance(label, QLabel) and "fixture error" in label.text()
    panel.clear_results()
    assert panel.blocks == []


def test_main_window_exposes_phase1_controls_and_languages(qt_app: object, tmp_path: Path) -> None:
    window = MainWindow(SettingsStore(tmp_path / "settings.json"))
    assert window.start_button.text() == "Start"
    assert window.rescan_button.text() == "Rescan"
    assert window.pause_button.text() == "Pause"
    assert window.clear_button.text() == "Clear"
    assert not window.rescan_button.isEnabled()
    assert not window.pause_button.isEnabled()
    assert hasattr(window, "overlay")
    assert not hasattr(window, "panel_dock")
    assert window.overlay_toggle_button.text() == "Show / Hide Overlay"
    assert not window.overlay_toggle_button.isEnabled()
    assert {group.title() for group in window.findChildren(QGroupBox)} >= {
        "Reader",
        "Capture region",
        "Scanning",
        "Translation overlay",
    }
    assert [window.language.itemText(index) for index in range(window.language.count())] == [
        "Auto",
        "Japanese",
        "Simplified Chinese",
        "Traditional Chinese",
    ]
    window.language.setCurrentIndex(window.language.findData(SourceLanguage.TRADITIONAL_CHINESE))
    assert ReadingDirection(window.reading_direction.currentData()) is ReadingDirection.WEBTOON_LTR
    assert not window.reading_direction.isEnabled()
    window.language.setCurrentIndex(window.language.findData(SourceLanguage.JAPANESE))
    assert window.reading_direction.isEnabled()
    window.close()


def test_region_point_conversion() -> None:
    screen = ScreenDescriptor("MYS240", 1920, 0, 1920, 1080, 1.0)
    region = region_from_points(screen, QPoint(500, 700), QPoint(100, 100))
    assert region == CaptionRegion("MYS240", 1920, 1080, 1.0, 100, 100, 400, 600)


def test_new_snapshot_clears_previous_overlay_before_worker_submission(
    qt_app: object, tmp_path: Path
) -> None:
    del qt_app
    window = MainWindow(SettingsStore(tmp_path / "settings.json"))
    box = ((1.0, 2.0), (30.0, 2.0), (30.0, 20.0), (1.0, 20.0))
    translated = TranslatedBlock(
        OcrTextBlock("one", 0.9, box),
        "First",
        SourceLanguage.JAPANESE,
        0.1,
        stable_id="one",
    )
    window.overlay.resize(100, 100)
    window.overlay.reconcile_results(ViewportTranslation((translated,), 0.1, 0.1, 1, 100, 100))

    class Worker:
        submitted = False

        def clear_pending(self) -> None:
            pass

        def submit(self, _job: object) -> bool:
            self.submitted = True
            return True

    worker = Worker()
    window.worker = worker  # type: ignore[assignment]
    class CaptureWorker:
        requested = False

        def request_capture(self) -> None:
            self.requested = True

    capture_worker = CaptureWorker()
    window.capture_worker = capture_worker  # type: ignore[assignment]
    region = CaptionRegion("Display", 100, 100, 1.0, 0, 0, 10, 10)
    captured = CapturedFrame(bytes(400), 10, 10, 40, 1.0, region)
    window._submit_snapshot(ViewportSnapshot(captured, fingerprint_frame(captured)))
    assert window.overlay.rendered_box_count == 0
    assert capture_worker.requested
    assert not worker.submitted
    assert window.clean_capture_request is not None
    hidden_at = window.clean_capture_request.hidden_at
    first_clean = CapturedFrame(bytes(400), 10, 10, 40, hidden_at + 0.2, region)
    second_clean = CapturedFrame(bytes(400), 10, 10, 40, hidden_at + 0.4, region)
    window._consume_clean_capture(first_clean)
    assert not worker.submitted
    window._consume_clean_capture(second_clean)
    assert worker.submitted
    window.worker = None
    window.capture_worker = None
    window.close()


def test_scan_worker_translates_every_block(monkeypatch: object, qt_app: object) -> None:
    import manga_live_translator.workers.scan as scan_module

    region = CaptionRegion("MYS240", 1920, 1080, 1.0, 0, 0, 10, 10)
    screen = ScreenDescriptor("MYS240", 1920, 0, 1920, 1080, 1.0)
    box1 = ((0.0, 0.0), (5.0, 0.0), (5.0, 2.0), (0.0, 2.0))
    box2 = ((0.0, 5.0), (5.0, 5.0), (5.0, 7.0), (0.0, 7.0))
    blocks = (OcrTextBlock("first", 0.9, box1), OcrTextBlock("second", 0.8, box2))

    class Capture:
        def capture(
            self, selected: CaptionRegion, selected_screen: ScreenDescriptor
        ) -> CapturedFrame:
            assert (selected, selected_screen) == (region, screen)
            return CapturedFrame(bytes(400), 10, 10, 40, 1.0, region)

        def close(self) -> None:
            pass

    class Ocr:
        def load(self) -> None:
            pass

        def recognize(self, frame: CapturedFrame) -> OcrResult:
            return OcrResult(blocks, "first\nsecond", "first second", 0.8, frame.captured_at, 0.2)

        def close(self) -> None:
            pass

    class Translator:
        def load(self) -> None:
            pass

        def translate(self, text: str, language: SourceLanguage) -> TextTranslationResult:
            return TextTranslationResult(f"EN:{text}", language, "en", 0.1)

        def close(self) -> None:
            pass

    monkeypatch.setattr(scan_module, "WindowsGdiCaptureProvider", Capture)  # type: ignore[attr-defined]
    monkeypatch.setattr(scan_module, "RapidOcrEngine", Ocr)  # type: ignore[attr-defined]
    monkeypatch.setattr(scan_module, "CTranslate2TextEngine", Translator)  # type: ignore[attr-defined]
    worker = scan_module.ScanWorker(region, screen, SourceLanguage.JAPANESE)
    viewports: list[ViewportTranslation] = []
    worker.viewport_ready.connect(viewports.append)
    worker._scan_viewport(Capture(), Ocr(), Translator())
    assert [item.translation for item in viewports[0].blocks] == ["EN:first", "EN:second"]
    assert (viewports[0].ocr_seconds, viewports[0].translation_seconds) == (0.2, 0.2)

    # Exercise the persistent session loop synchronously so coverage observes the QThread body.
    class SynchronousWorker(scan_module.ScanWorker):
        stopped = False

        def isInterruptionRequested(self) -> bool:  # noqa: N802
            return self.stopped

    session_worker = SynchronousWorker(region, screen, SourceLanguage.JAPANESE)
    session_viewports: list[ViewportTranslation] = []
    session_worker.viewport_ready.connect(session_viewports.append)
    session_worker.viewport_ready.connect(lambda _result: setattr(session_worker, "stopped", True))
    assert session_worker.request_scan()
    session_worker.run()
    assert len(session_viewports) == 1

    running_worker = scan_module.ScanWorker(region, screen, SourceLanguage.JAPANESE)
    running_viewports: list[ViewportTranslation] = []
    running_worker.viewport_ready.connect(running_viewports.append)
    assert running_worker.request_scan()
    assert not running_worker.request_scan()
    running_worker.start()
    deadline = time.monotonic() + 1
    while not running_viewports and time.monotonic() < deadline:
        qt_app.processEvents()  # type: ignore[attr-defined]
        time.sleep(0.01)
    running_worker.stop()
    qt_app.processEvents()  # type: ignore[attr-defined]
    assert [item.translation for item in running_viewports[0].blocks] == ["EN:first", "EN:second"]
    assert not running_worker.isRunning()


def test_scan_worker_keeps_other_blocks_when_one_translation_fails() -> None:
    import manga_live_translator.workers.scan as scan_module

    region = CaptionRegion("MYS240", 1920, 1080, 1.0, 0, 0, 10, 10)
    screen = ScreenDescriptor("MYS240", 1920, 0, 1920, 1080, 1.0)
    box = ((0.0, 0.0), (5.0, 0.0), (5.0, 2.0), (0.0, 2.0))

    class Capture:
        def capture(
            self, selected: CaptionRegion, selected_screen: ScreenDescriptor
        ) -> CapturedFrame:
            del selected_screen
            return CapturedFrame(bytes(400), 10, 10, 40, 1.0, selected)

    class Ocr:
        def recognize(self, frame: CapturedFrame) -> OcrResult:
            blocks = (OcrTextBlock("good", 0.9, box), OcrTextBlock("bad", 0.9, box))
            return OcrResult(blocks, "good\nbad", "good bad", 0.9, frame.captured_at, 0.2)

    class Translator:
        def translate(self, text: str, language: SourceLanguage) -> TextTranslationResult:
            if text == "bad":
                raise scan_module.TextTranslationError("fixture failure")
            return TextTranslationResult("Good", language, "en", 0.1)

    worker = scan_module.ScanWorker(region, screen, SourceLanguage.JAPANESE)
    viewports: list[ViewportTranslation] = []
    worker.viewport_ready.connect(viewports.append)
    worker._scan_viewport(Capture(), Ocr(), Translator())  # type: ignore[arg-type]
    assert viewports[0].blocks[0].translation == "Good"
    assert viewports[0].blocks[1].translation is None
    assert viewports[0].blocks[1].error == "fixture failure"
