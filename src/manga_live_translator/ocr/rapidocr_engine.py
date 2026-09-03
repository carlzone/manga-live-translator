"""RapidOCR ONNX Runtime adapter using explicit external model assets."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from manga_live_translator.ocr.engine import OcrError, OcrResult, OcrTextBlock
from manga_live_translator.ocr.processing import normalize_ocr_text, order_blocks
from manga_live_translator.paths import runtime_path

if TYPE_CHECKING:
    from manga_live_translator.screen import CapturedFrame

DETECTION_MODEL = "PP-OCRv6_det_small.onnx"
RECOGNITION_MODEL = "PP-OCRv6_rec_small.onnx"
RECOGNITION_DICTIONARY = "ppocrv6_dict.txt"
ORIENTATION_MODEL = "ch_ppocr_mobile_v2.0_cls_mobile.onnx"


class RapidOcrEngine:
    def __init__(self, model_dir: Path | None = None, *, use_orientation: bool = False) -> None:
        self.model_dir = model_dir or runtime_path("models", "ocr")
        self.use_orientation = use_orientation
        self._engine: Any | None = None

    def _required_assets(self) -> tuple[Path, ...]:
        return (
            self.model_dir / DETECTION_MODEL,
            self.model_dir / RECOGNITION_MODEL,
            self.model_dir / RECOGNITION_DICTIONARY,
            self.model_dir / ORIENTATION_MODEL,
        )

    def load(self) -> None:
        missing = [path for path in self._required_assets() if not path.is_file()]
        if missing:
            raise OcrError("Missing OCR asset: " + str(missing[0]))
        try:
            from rapidocr import EngineType, RapidOCR
        except ImportError as exc:
            raise OcrError("RapidOCR is not installed; run 'uv sync'") from exc
        params: dict[str, object] = {
            "Global.use_det": True,
            "Global.use_cls": self.use_orientation,
            "Global.use_rec": True,
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Det.model_path": str(self.model_dir / DETECTION_MODEL),
            "Det.limit_type": "max",
            "Det.limit_side_len": 960,
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.model_path": str(self.model_dir / RECOGNITION_MODEL),
            "Rec.rec_keys_path": str(self.model_dir / RECOGNITION_DICTIONARY),
            "Cls.engine_type": EngineType.ONNXRUNTIME,
            "Cls.model_path": str(self.model_dir / ORIENTATION_MODEL),
        }
        try:
            self._engine = RapidOCR(params=params)
        except Exception as exc:
            raise OcrError(f"Could not load OCR models from {self.model_dir}: {exc}") from exc

    @staticmethod
    def frame_to_bgr(frame: CapturedFrame) -> np.ndarray[tuple[int, ...], np.dtype[np.uint8]]:
        pixels = np.frombuffer(frame.pixels, dtype=np.uint8)
        if pixels.size != frame.height * frame.stride:
            raise OcrError("Captured frame has an invalid pixel buffer")
        rows = pixels.reshape(frame.height, frame.stride)[:, : frame.width * 4]
        return rows.reshape(frame.height, frame.width, 4)[:, :, :3].copy()

    def recognize(self, frame: CapturedFrame) -> OcrResult:
        if self._engine is None:
            raise OcrError("OCR engine is not loaded")
        started = time.perf_counter()
        try:
            output = self._engine(self.frame_to_bgr(frame), use_cls=self.use_orientation)
            output_texts = getattr(output, "txts", None)
            output_scores = getattr(output, "scores", None)
            output_boxes = getattr(output, "boxes", None)
            texts = tuple(output_texts) if output_texts is not None else ()
            scores = tuple(output_scores) if output_scores is not None else ()
            boxes = tuple(output_boxes) if output_boxes is not None else ()
        except Exception as exc:
            raise OcrError(f"OCR inference failed: {exc}") from exc
        blocks: list[OcrTextBlock] = []
        for text, score, box in zip(texts, scores, boxes, strict=False):
            points = tuple((float(point[0]), float(point[1])) for point in box)
            if len(points) != 4:
                continue
            blocks.append(OcrTextBlock(str(text), float(score), points))
        filtered = tuple(
            block
            for block in order_blocks(tuple(blocks))
            if block.confidence >= 0.75 and block.text.strip()
        )
        text = "\n".join(block.text.strip() for block in filtered)
        confidence = min((block.confidence for block in filtered), default=0.0)
        return OcrResult(
            filtered,
            text,
            normalize_ocr_text(text),
            confidence,
            frame.captured_at,
            time.perf_counter() - started,
        )

    def close(self) -> None:
        self._engine = None
