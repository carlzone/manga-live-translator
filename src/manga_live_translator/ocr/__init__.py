"""Local OCR abstraction and subtitle stabilization."""

from manga_live_translator.ocr.engine import (
    BlockOrientation,
    OcrEngine,
    OcrError,
    OcrResult,
    OcrTextBlock,
)
from manga_live_translator.ocr.processing import LayoutResult, process_manga_layout
from manga_live_translator.ocr.rapidocr_engine import RapidOcrEngine
from manga_live_translator.ocr.stabilizer import OcrStabilizer

__all__ = [
    "BlockOrientation",
    "OcrEngine",
    "OcrError",
    "OcrResult",
    "OcrStabilizer",
    "OcrTextBlock",
    "LayoutResult",
    "process_manga_layout",
    "RapidOcrEngine",
]
