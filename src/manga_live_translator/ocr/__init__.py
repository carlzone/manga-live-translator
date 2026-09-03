"""Local OCR abstraction and subtitle stabilization."""

from manga_live_translator.ocr.engine import OcrEngine, OcrError, OcrResult, OcrTextBlock
from manga_live_translator.ocr.rapidocr_engine import RapidOcrEngine
from manga_live_translator.ocr.stabilizer import OcrStabilizer

__all__ = ["OcrEngine", "OcrError", "OcrResult", "OcrStabilizer", "OcrTextBlock", "RapidOcrEngine"]
