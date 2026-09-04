import json
import sys
import types
from pathlib import Path

from manga_live_translator.config import AppSettings, ReadingDirection, SourceLanguage
from manga_live_translator.ocr import BlockOrientation, OcrTextBlock, RapidOcrEngine
from manga_live_translator.ocr.processing import process_manga_layout
from manga_live_translator.screen import CapturedFrame


def block(
    text: str, left: float, top: float, right: float, bottom: float, confidence: float = 0.9
) -> OcrTextBlock:
    return OcrTextBlock(
        text, confidence, ((left, top), (right, top), (right, bottom), (left, bottom))
    )


def test_settings_migrate_layout_defaults_and_validate_values() -> None:
    assert AppSettings.from_dict({}).reading_direction is ReadingDirection.AUTOMATIC
    assert not AppSettings.from_dict({}).experimental_vertical_ocr
    invalid = AppSettings.from_dict(
        {"reading_direction": "sideways", "experimental_vertical_ocr": "yes"}
    )
    assert invalid.reading_direction is ReadingDirection.AUTOMATIC
    assert not invalid.experimental_vertical_ocr
    selected = AppSettings.from_dict(
        {"reading_direction": "manga_rtl", "experimental_vertical_ocr": True}
    )
    assert selected.reading_direction is ReadingDirection.MANGA_RTL
    assert selected.experimental_vertical_ocr


def test_rtl_webtoon_and_auto_orders_are_deterministic() -> None:
    blocks = (
        block("左", 10, 10, 30, 20),
        block("右下", 70, 40, 90, 50),
        block("右上", 70, 5, 90, 15),
    )
    manga = process_manga_layout(
        blocks, reading_direction=ReadingDirection.MANGA_RTL, language=SourceLanguage.JAPANESE
    )
    assert [item.text for item in manga.blocks] == ["右上", "右下", "左"]
    webtoon = process_manga_layout(blocks, reading_direction=ReadingDirection.WEBTOON_LTR)
    assert [item.text for item in webtoon.blocks] == ["右上", "左", "右下"]
    automatic = process_manga_layout(
        blocks, reading_direction=ReadingDirection.AUTOMATIC, language=SourceLanguage.JAPANESE
    )
    assert automatic.reading_direction is ReadingDirection.MANGA_RTL
    chinese = process_manga_layout(
        blocks,
        reading_direction=ReadingDirection.AUTOMATIC,
        language=SourceLanguage.SIMPLIFIED_CHINESE,
    )
    assert chinese.reading_direction is ReadingDirection.WEBTOON_LTR
    forced_chinese = process_manga_layout(
        blocks,
        reading_direction=ReadingDirection.MANGA_RTL,
        language=SourceLanguage.TRADITIONAL_CHINESE,
    )
    assert forced_chinese.reading_direction is ReadingDirection.WEBTOON_LTR
    han_only_auto = process_manga_layout(
        blocks,
        reading_direction=ReadingDirection.MANGA_RTL,
        language=SourceLanguage.AUTO,
    )
    assert han_only_auto.reading_direction is ReadingDirection.WEBTOON_LTR


def test_grouping_joins_cjk_and_rejects_incompatible_or_distant_fragments() -> None:
    blocks = (
        block("こん", 10, 10, 40, 20),
        block("にちは", 12, 22, 42, 32),
        block("Latin", 12, 34, 42, 44),
        block("遠い", 70, 80, 95, 90),
    )
    result = process_manga_layout(blocks)
    assert [item.text for item in result.blocks] == ["こんにちは", "Latin", "遠い"]
    assert len(result.blocks[0].fragment_boxes) == 2
    assert result.blocks[0].confidence == 0.9


def test_vertical_filter_preserves_polygon_and_orientation() -> None:
    box = ((5.0, 2.0), (15.0, 2.0), (15.0, 52.0), (5.0, 52.0))
    candidate = OcrTextBlock("縦", 0.95, box)
    assert not process_manga_layout((candidate,)).blocks
    accepted = process_manga_layout((candidate,), allow_vertical=True)
    assert accepted.blocks[0].box is box
    assert accepted.blocks[0].orientation is BlockOrientation.VERTICAL


def test_vertical_retry_is_enabled_for_chinese_source_languages() -> None:
    simplified = RapidOcrEngine(
        source_language=SourceLanguage.SIMPLIFIED_CHINESE,
        experimental_vertical_ocr=True,
    )
    traditional = RapidOcrEngine(
        source_language=SourceLanguage.TRADITIONAL_CHINESE,
        experimental_vertical_ocr=True,
    )
    assert simplified.experimental_vertical_ocr
    assert traditional.experimental_vertical_ocr


def test_vertical_crop_tries_both_rotations_and_isolates_failure(monkeypatch: object) -> None:
    calls = 0

    class Output:
        txts = ("元",)
        scores = (0.8,)
        boxes = (((1, 1), (5, 1), (5, 18), (1, 18)),)

    class CropOutput:
        boxes = ()

        def __init__(self, text: str, score: float) -> None:
            self.txts = (text,)
            self.scores = (score,)

    class FakeRapidOcr:
        def __init__(self, *, params: dict[str, object]) -> None:
            del params

        def __call__(self, image: object, *, use_cls: bool) -> object:
            nonlocal calls
            del image, use_cls
            calls += 1
            if calls == 1:
                return Output()
            if calls == 2:
                raise RuntimeError("one rotation failed")
            return CropOutput("縦書き", 0.96)

    monkeypatch.setitem(
        sys.modules,
        "rapidocr",
        types.SimpleNamespace(
            RapidOCR=FakeRapidOcr, EngineType=types.SimpleNamespace(ONNXRUNTIME="onnx")
        ),
    )  # type: ignore[attr-defined]
    model_dir = Path("tests/fixtures/fake-models")
    engine = RapidOcrEngine(
        model_dir, source_language=SourceLanguage.JAPANESE, experimental_vertical_ocr=True
    )
    engine._engine = FakeRapidOcr(params={})
    pixels = bytes([0, 0, 0, 255]) * 400
    region = __import__("manga_live_translator.config", fromlist=["CaptionRegion"]).CaptionRegion(
        "x", 20, 20, 1, 0, 0, 20, 20
    )
    result = engine.recognize(CapturedFrame(pixels, 20, 20, 80, 0, region))
    assert result.blocks[0].text == "縦書き"
    assert result.blocks[0].box == Output.boxes[0]
    assert calls == 3


def test_phase3_manifest_is_complete_and_project_created() -> None:
    root = Path(__file__).parent / "fixtures" / "phase3"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert "project-created" in manifest["license"]
    names = {item["name"] for item in manifest["fixtures"]}
    assert {
        "japanese-rtl-columns",
        "webtoon-rows",
        "fragmented-bubble",
        "repeated-dialogue-separate",
        "mixed-orientation",
        "automatic-japanese-columns",
    } <= names
