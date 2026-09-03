"""Bounded background OCR inference and caption stabilization."""

from __future__ import annotations

import logging
import queue
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal

from manga_live_translator.ocr import OcrEngine, OcrError, OcrStabilizer
from manga_live_translator.workers.messages import RuntimeStatus

if TYPE_CHECKING:
    from manga_live_translator.screen import CapturedFrame

LOGGER = logging.getLogger("manga_live_translator.workers.ocr")


class OcrWorker(QThread):
    observation_ready = Signal(object)
    caption_ready = Signal(object)
    status_changed = Signal(object, object)
    performance_measured = Signal(float)
    error = Signal(str)

    def __init__(self, engine: OcrEngine, max_pending_frames: int = 1) -> None:
        super().__init__()
        if max_pending_frames <= 0:
            raise ValueError("max_pending_frames must be positive")
        self.engine = engine
        self.stabilizer = OcrStabilizer()
        self._frames: queue.Queue[CapturedFrame] = queue.Queue(max_pending_frames)
        self._dropped_frames = 0

    def submit(self, frame: CapturedFrame) -> bool:
        dropped = 0
        while True:
            try:
                self._frames.put_nowait(frame)
                break
            except queue.Full:
                try:
                    self._frames.get_nowait()
                    dropped += 1
                except queue.Empty:
                    continue
        self._dropped_frames += dropped
        if dropped:
            LOGGER.debug("OCR queue replaced stale frame; total_dropped=%d", self._dropped_frames)
        return dropped == 0

    @property
    def queue_depth(self) -> int:
        return self._frames.qsize()

    @property
    def dropped_frames(self) -> int:
        return self._dropped_frames

    def clear_pending(self) -> None:
        while True:
            try:
                self._frames.get_nowait()
            except queue.Empty:
                return

    def start_ocr(self) -> None:
        if self.isRunning():
            return
        self.clear_pending()
        self.stabilizer.reset()
        self.start()

    def run(self) -> None:
        try:
            self.engine.load()
            self.status_changed.emit(RuntimeStatus.READING_CAPTIONS, "OCR ready (CPU)")
            while not self.isInterruptionRequested():
                try:
                    frame = self._frames.get(timeout=0.05)
                except queue.Empty:
                    continue
                result = self.engine.recognize(frame)
                LOGGER.info(
                    "OCR complete; inference=%.3fs confidence=%.3f blocks=%d",
                    result.inference_seconds,
                    result.confidence,
                    len(result.blocks),
                )
                self.observation_ready.emit(result)
                self.performance_measured.emit(result.inference_seconds)
                committed = self.stabilizer.observe(result)
                if committed is not None:
                    self.caption_ready.emit(committed)
        except (OcrError, OSError, ValueError, RuntimeError) as exc:
            detail = f"OCR failed: {exc}"
            LOGGER.exception(detail)
            self.error.emit(detail)
            self.status_changed.emit(RuntimeStatus.ERROR, detail)
        except Exception as exc:
            detail = f"OCR failed unexpectedly: {exc}"
            LOGGER.exception(detail)
            self.error.emit(detail)
            self.status_changed.emit(RuntimeStatus.ERROR, detail)
        finally:
            self.engine.close()

    def stop_ocr(self) -> None:
        self.requestInterruption()
        if self.isRunning() and not self.wait(3000):
            LOGGER.warning("OCR worker did not stop within three seconds")
        self.clear_pending()
        self.stabilizer.reset()
        if not self.isRunning():
            self.engine.close()

    def close(self) -> None:
        self.stop_ocr()
