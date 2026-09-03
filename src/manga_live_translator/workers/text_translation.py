"""Bounded background translation for stable OCR captions."""

from __future__ import annotations

import logging
import queue

from PySide6.QtCore import QThread, Signal

from manga_live_translator.config import SourceLanguage
from manga_live_translator.ocr import OcrResult
from manga_live_translator.text_translation import TextTranslationEngine, TextTranslationError
from manga_live_translator.workers.messages import RuntimeStatus

LOGGER = logging.getLogger("manga_live_translator.workers.text_translation")


class TextTranslationWorker(QThread):
    translation_ready = Signal(object)
    status_changed = Signal(object, object)
    performance_measured = Signal(float)
    error = Signal(str)

    def __init__(
        self,
        engine: TextTranslationEngine,
        source_language: SourceLanguage,
        max_pending_captions: int = 1,
    ) -> None:
        super().__init__()
        if max_pending_captions <= 0:
            raise ValueError("max_pending_captions must be positive")
        self.engine = engine
        self.source_language = SourceLanguage(source_language)
        self._captions: queue.Queue[str] = queue.Queue(max_pending_captions)
        self._dropped_captions = 0

    def validate_assets(self) -> None:
        self.engine.validate_assets()

    def submit(self, caption: OcrResult | str) -> bool:
        text = caption.text if isinstance(caption, OcrResult) else str(caption)
        if not text.strip():
            return False
        dropped = 0
        while True:
            try:
                self._captions.put_nowait(text)
                break
            except queue.Full:
                try:
                    self._captions.get_nowait()
                    dropped += 1
                except queue.Empty:
                    continue
        self._dropped_captions += dropped
        if dropped:
            LOGGER.warning(
                "Text translation queue pressure; dropped=%d total_dropped=%d",
                dropped,
                self._dropped_captions,
            )
        return dropped == 0

    @property
    def queue_depth(self) -> int:
        return self._captions.qsize()

    @property
    def dropped_captions(self) -> int:
        return self._dropped_captions

    def clear_pending(self) -> None:
        while True:
            try:
                self._captions.get_nowait()
            except queue.Empty:
                return

    def start_translation(self) -> None:
        if self.isRunning():
            return
        self.clear_pending()
        self.start()

    def run(self) -> None:
        try:
            self.engine.load()
            self.status_changed.emit(RuntimeStatus.READING_CAPTIONS, "Text translation ready (CPU)")
            while not self.isInterruptionRequested():
                try:
                    text = self._captions.get(timeout=0.05)
                except queue.Empty:
                    continue
                self.status_changed.emit(RuntimeStatus.TRANSLATING, None)
                result = self.engine.translate(text, self.source_language)
                LOGGER.info(
                    "Text translation complete; source=%s inference=%.3fs",
                    result.source_language.value,
                    result.inference_seconds,
                )
                if self.isInterruptionRequested():
                    break
                self.performance_measured.emit(result.inference_seconds)
                self.translation_ready.emit(result)
                self.status_changed.emit(RuntimeStatus.READING_CAPTIONS, None)
        except (TextTranslationError, OSError, ValueError, RuntimeError) as exc:
            detail = f"Text translation failed: {exc}"
            LOGGER.exception(detail)
            self.error.emit(detail)
            self.status_changed.emit(RuntimeStatus.ERROR, detail)
        except Exception as exc:
            detail = f"Text translation failed unexpectedly: {exc}"
            LOGGER.exception(detail)
            self.error.emit(detail)
            self.status_changed.emit(RuntimeStatus.ERROR, detail)
        finally:
            self.engine.close()

    def stop_translation(self) -> None:
        self.requestInterruption()
        if self.isRunning() and not self.wait(3000):
            LOGGER.warning("Text translation worker did not stop within three seconds")
        self.clear_pending()
        if not self.isRunning():
            self.engine.close()

    def close(self) -> None:
        self.stop_translation()
