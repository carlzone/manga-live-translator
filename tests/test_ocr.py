import re
import sys
import time
import types
from pathlib import Path

import pytest

from manga_live_translator.config import CaptionRegion
from manga_live_translator.ocr import (
    OcrError,
    OcrResult,
    OcrStabilizer,
    OcrTextBlock,
    RapidOcrEngine,
)
from manga_live_translator.ocr.processing import (
    comparison_key,
    normalize_ocr_text,
    order_blocks,
)
from manga_live_translator.screen import CapturedFrame
from manga_live_translator.workers import OcrWorker

REGION = CaptionRegion("Display 1", 100, 100, 1.0, 0, 0, 4, 2)
BOX = ((0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0))


def frame(value: int = 10, captured_at: float = 1.0) -> CapturedFrame:
    return CapturedFrame(
        bytes([value, value + 1, value + 2, 255]) * 8,
        4,
        2,
        16,
        captured_at,
        REGION,
    )


def result(text: str, confidence: float) -> OcrResult:
    blocks = (OcrTextBlock(text, confidence, BOX),) if text else ()
    return OcrResult(blocks, text, normalize_ocr_text(text), confidence, 1.0, 0.01)


def test_text_normalization_preserves_chinese_variant_and_ignores_punctuation() -> None:
    assert normalize_ocr_text("  \u81fa\u7063\n  \u4e2d\u6587  ") == "\u81fa\u7063\u4e2d\u6587"
    assert normalize_ocr_text("\u53f0\u6e7e") == "\u53f0\u6e7e"
    assert comparison_key("\u300c\u3053\u3093\u306b\u3061\u306f\uff01\u300d") == comparison_key(
        "\u3053\u3093\u306b\u3061\u306f"
    )


def test_manga_order_preserves_every_block_top_to_bottom() -> None:
    top = OcrTextBlock("menu", 0.99, ((0, 0), (20, 0), (20, 10), (0, 10)))
    lower = OcrTextBlock("å­—å¹•", 0.95, ((20, 70), (80, 70), (80, 85), (20, 85)))
    assert order_blocks((lower, top)) == (top, lower)


def test_stabilizer_filters_commits_and_deduplicates() -> None:
    stabilizer = OcrStabilizer()
    assert stabilizer.observe(result("", 0.99)) is None
    assert stabilizer.observe(result("\u4f4e\u3044", 0.70)) is None
    assert stabilizer.observe(result("\u3053\u3093\u306b\u3061\u306f\u3002", 0.80)) is None
    committed = stabilizer.observe(result("\u3053\u3093\u306b\u3061\u306f!", 0.85))
    assert committed is not None and committed.text == "\u3053\u3093\u306b\u3061\u306f!"
    assert stabilizer.observe(result("\u300c\u3053\u3093\u306b\u3061\u306f\u300d", 0.95)) is None
    assert stabilizer.observe(result("\u65b0\u3057\u3044\u5b57\u5e55", 0.90)) is not None


def test_frame_conversion_handles_stride_and_rejects_invalid_buffer() -> None:
    image = RapidOcrEngine.frame_to_bgr(frame())
    assert image.shape == (2, 4, 3)
    assert image[0, 0].tolist() == [10, 11, 12]
    invalid = CapturedFrame(b"bad", 4, 2, 16, 1.0, REGION)
    with pytest.raises(OcrError, match="invalid pixel buffer"):
        RapidOcrEngine.frame_to_bgr(invalid)


def test_rapidocr_requires_explicit_external_assets(tmp_path: Path) -> None:
    with pytest.raises(OcrError, match=re.escape(str(tmp_path))):
        RapidOcrEngine(tmp_path).load()


def test_rapidocr_loads_explicit_assets_and_maps_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "PP-OCRv6_det_small.onnx",
        "PP-OCRv6_rec_small.onnx",
        "ppocrv6_dict.txt",
        "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    ):
        (tmp_path / name).write_bytes(b"fixture")
    constructed: list[dict[str, object]] = []

    class Output:
        txts = ("menu", "å­—å¹•")
        scores = (0.99, 0.95)
        boxes = (
            ((0, 0), (4, 0), (4, 10), (0, 10)),
            ((0, 80), (4, 80), (4, 90), (0, 90)),
        )

    class FakeRapidOcr:
        def __init__(self, *, params: dict[str, object]) -> None:
            constructed.append(params)

        def __call__(self, image: object, *, use_cls: bool) -> Output:
            del image, use_cls
            return Output()

    engine_type = types.SimpleNamespace(ONNXRUNTIME="onnxruntime")
    rapidocr_module = types.SimpleNamespace(RapidOCR=FakeRapidOcr, EngineType=engine_type)
    monkeypatch.setitem(sys.modules, "rapidocr", rapidocr_module)
    engine = RapidOcrEngine(tmp_path)
    engine.load()
    recognized = engine.recognize(frame())
    assert constructed[0]["Det.model_path"] == str(tmp_path / "PP-OCRv6_det_small.onnx")
    assert recognized.text.splitlines() == ["menu", Output.txts[1]]
    assert recognized.confidence == 0.95
    engine.close()
    with pytest.raises(OcrError, match="not loaded"):
        engine.recognize(frame())


class FakeEngine:
    def __init__(self, delay: float = 0) -> None:
        self.delay = delay
        self.loaded = 0
        self.closed = 0
        self.seen: list[float] = []

    def load(self) -> None:
        self.loaded += 1

    def recognize(self, captured: CapturedFrame) -> OcrResult:
        time.sleep(self.delay)
        self.seen.append(captured.captured_at)
        return result("å­—å¹•", 0.95)

    def close(self) -> None:
        self.closed += 1


def test_ocr_worker_is_bounded_emits_and_closes(qt_app: object) -> None:
    engine = FakeEngine(0.02)
    worker = OcrWorker(engine)
    observations: list[OcrResult] = []
    captions: list[OcrResult] = []
    worker.observation_ready.connect(observations.append)
    worker.caption_ready.connect(captions.append)
    worker.start_ocr()
    worker.submit(frame(captured_at=1))
    worker.submit(frame(captured_at=2))
    worker.submit(frame(captured_at=3))
    deadline = time.monotonic() + 1
    while not observations and time.monotonic() < deadline:
        qt_app.processEvents()  # type: ignore[attr-defined]
        time.sleep(0.01)
    worker.close()
    qt_app.processEvents()  # type: ignore[attr-defined]
    assert observations and captions
    assert engine.loaded == 1
    assert engine.closed >= 1
    assert worker.dropped_frames >= 1
    assert engine.seen[-1] == 3
    assert worker.queue_depth == 0
