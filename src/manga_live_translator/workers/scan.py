"""One-shot capture, multi-block OCR, and translation worker."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from manga_live_translator.config import CaptionRegion, SourceLanguage
from manga_live_translator.ocr import OcrTextBlock, RapidOcrEngine
from manga_live_translator.screen import ScreenDescriptor, WindowsGdiCaptureProvider
from manga_live_translator.text_translation import CTranslate2TextEngine
from manga_live_translator.workers.messages import RuntimeStatus


@dataclass(frozen=True, slots=True)
class TranslatedBlock:
    source: OcrTextBlock
    translation: str
    source_language: SourceLanguage
    inference_seconds: float


class ScanWorker(QThread):
    status_changed = Signal(object, object)
    block_observed = Signal(object)
    block_translated = Signal(object)
    scan_finished = Signal(int, float, float)
    error = Signal(str)

    def __init__(
        self, region: CaptionRegion, screen: ScreenDescriptor, language: SourceLanguage
    ) -> None:
        super().__init__()
        self.region = region
        self.screen = screen
        self.language = SourceLanguage(language)

    def run(self) -> None:
        capture = WindowsGdiCaptureProvider()
        ocr = RapidOcrEngine()
        translator = CTranslate2TextEngine()
        try:
            self.status_changed.emit(RuntimeStatus.CAPTURING, self.region.screen_name)
            frame = capture.capture(self.region, self.screen)
            if self.isInterruptionRequested():
                return
            self.status_changed.emit(RuntimeStatus.READING, None)
            ocr.load()
            result = ocr.recognize(frame)
            translator.load()
            translation_seconds = 0.0
            translated_count = 0
            for block in result.blocks:
                if self.isInterruptionRequested():
                    return
                self.block_observed.emit(block)
                self.status_changed.emit(RuntimeStatus.TRANSLATING, block.text)
                translated = translator.translate(block.text, self.language)
                translation_seconds += translated.inference_seconds
                translated_count += 1
                self.block_translated.emit(
                    TranslatedBlock(
                        block,
                        translated.text,
                        translated.source_language,
                        translated.inference_seconds,
                    )
                )
            self.status_changed.emit(RuntimeStatus.READY, f"Translated {translated_count} block(s)")
            self.scan_finished.emit(translated_count, result.inference_seconds, translation_seconds)
        except Exception as exc:
            detail = f"Scan failed: {exc}"
            self.error.emit(detail)
            self.status_changed.emit(RuntimeStatus.ERROR, detail)
        finally:
            capture.close()
            ocr.close()
            translator.close()

    def stop(self) -> None:
        self.requestInterruption()
        if self.isRunning() and not self.wait(5000):
            self.error.emit("Scan worker did not stop within five seconds")
