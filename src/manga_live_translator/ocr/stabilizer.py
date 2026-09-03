"""Confidence filtering and stable OCR caption commitment."""

from __future__ import annotations

from manga_live_translator.ocr.engine import OcrResult
from manga_live_translator.ocr.processing import comparison_key


class OcrStabilizer:
    def __init__(
        self, minimum_confidence: float = 0.75, immediate_confidence: float = 0.90
    ) -> None:
        if not 0 <= minimum_confidence <= immediate_confidence <= 1:
            raise ValueError(
                "OCR confidence thresholds must satisfy 0 <= minimum <= immediate <= 1"
            )
        self.minimum_confidence = minimum_confidence
        self.immediate_confidence = immediate_confidence
        self.reset()

    def reset(self) -> None:
        self._pending_key = ""
        self._pending: OcrResult | None = None
        self._observations = 0
        self._committed_key = ""

    def observe(self, result: OcrResult) -> OcrResult | None:
        key = comparison_key(result.normalized_text)
        if not key or result.confidence < self.minimum_confidence:
            self._pending_key = ""
            self._pending = None
            self._observations = 0
            return None
        if key == self._pending_key:
            self._observations += 1
            if self._pending is None or result.confidence > self._pending.confidence:
                self._pending = result
        else:
            self._pending_key = key
            self._pending = result
            self._observations = 1
        if key == self._committed_key:
            return None
        if result.confidence >= self.immediate_confidence or self._observations >= 2:
            self._committed_key = key
            return self._pending
        return None
