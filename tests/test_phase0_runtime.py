"""Phase 0 manga-specific runtime and UI tests."""

from pathlib import Path

from PySide6.QtCore import QPoint

from manga_live_translator.config import AppSettings, CaptionRegion, SettingsStore, SourceLanguage
from manga_live_translator.ocr import OcrResult, OcrTextBlock
from manga_live_translator.screen import CapturedFrame, ScreenDescriptor
from manga_live_translator.text_translation import TextTranslationResult
from manga_live_translator.ui.panel import TranslationPanel
from manga_live_translator.ui.region_selector import region_from_points
from manga_live_translator.workers.scan import TranslatedBlock


def test_settings_round_trip_and_validation(tmp_path: Path) -> None:
    region = CaptionRegion("MYS240", 1920, 1080, 1.0, 100, 100, 800, 700)
    settings = AppSettings(caption_region=region, source_language=SourceLanguage.JAPANESE)
    store = SettingsStore(tmp_path / "settings.json")
    store.save(settings)
    assert store.load() == settings


def test_panel_adds_and_clears_multiple_results(qt_app: object) -> None:
    panel = TranslationPanel()
    box = ((1.0, 2.0), (30.0, 2.0), (30.0, 20.0), (1.0, 20.0))
    first = TranslatedBlock(OcrTextBlock("one", 0.9, box), "First", SourceLanguage.JAPANESE, 0.1)
    second = TranslatedBlock(OcrTextBlock("two", 0.8, box), "Second", SourceLanguage.CHINESE, 0.2)
    panel.add_result(first)
    panel.add_result(second, show_source=False)
    assert panel.blocks == [first, second]
    assert panel.results_layout.count() == 3
    panel.clear_results()
    assert panel.blocks == []


def test_region_point_conversion() -> None:
    screen = ScreenDescriptor("MYS240", 1920, 0, 1920, 1080, 1.0)
    region = region_from_points(screen, QPoint(500, 700), QPoint(100, 100))
    assert region == CaptionRegion("MYS240", 1920, 1080, 1.0, 100, 100, 400, 600)


def test_scan_worker_translates_every_block(monkeypatch: object) -> None:
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
    translated: list[TranslatedBlock] = []
    finished: list[tuple[int, float, float]] = []
    worker.block_translated.connect(translated.append)
    worker.scan_finished.connect(
        lambda count, ocr, translation: finished.append((count, ocr, translation))
    )
    worker.run()
    assert [item.translation for item in translated] == ["EN:first", "EN:second"]
    assert finished == [(2, 0.2, 0.2)]
