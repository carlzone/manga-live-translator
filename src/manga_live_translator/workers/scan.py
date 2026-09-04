"""Capacity-one viewport OCR and translation runtime."""

from __future__ import annotations

import queue
import statistics
import threading
import uuid
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from manga_live_translator.config import CaptionRegion, ReadingDirection, SourceLanguage
from manga_live_translator.ocr import OcrResult, OcrTextBlock, RapidOcrEngine
from manga_live_translator.ocr.processing import comparison_key
from manga_live_translator.screen import (
    ScreenDescriptor,
    ViewportSnapshot,
    WindowsGdiCaptureProvider,
    fingerprint_frame,
)
from manga_live_translator.text_translation import CTranslate2TextEngine, TextTranslationError
from manga_live_translator.workers.messages import RuntimeStatus


@dataclass(frozen=True, slots=True)
class NormalizedGeometry:
    center_x: float
    center_y: float
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class TranslatedBlock:
    source: OcrTextBlock
    translation: str | None
    source_language: SourceLanguage
    inference_seconds: float
    error: str | None = None
    stable_id: str = ""
    comparison_key: str = ""
    geometry: NormalizedGeometry | None = None


@dataclass(frozen=True, slots=True)
class ViewportTranslation:
    blocks: tuple[TranslatedBlock, ...]
    ocr_seconds: float
    translation_seconds: float
    generation: int = 0
    frame_width: int = 0
    frame_height: int = 0
    fingerprint: str = ""
    reading_direction: ReadingDirection = ReadingDirection.WEBTOON_LTR


@dataclass(frozen=True, slots=True)
class ScanJob:
    generation: int
    snapshot: ViewportSnapshot


class _LegacyScan:
    pass


def normalized_geometry(block: OcrTextBlock, width: int, height: int) -> NormalizedGeometry:
    xs = [point[0] for point in block.box]
    ys = [point[1] for point in block.box]
    return NormalizedGeometry(
        ((min(xs) + max(xs)) / 2) / width,
        ((min(ys) + max(ys)) / 2) / height,
        (max(xs) - min(xs)) / width,
        (max(ys) - min(ys)) / height,
    )


def _geometry_matches(
    old: NormalizedGeometry, new: NormalizedGeometry, *, vertical_shift: float = 0.0
) -> bool:
    return (
        abs(old.center_x - new.center_x) <= 0.05
        and abs((old.center_y + vertical_shift) - new.center_y) <= 0.08
        and abs(old.width - new.width) <= 0.05
        and abs(old.height - new.height) <= 0.05
    )


class BlockReconciler:
    """Assign stable identities across overlapping vertically scrolled viewports."""

    def __init__(self, *, identity_prefix: str = "block") -> None:
        self._previous: tuple[TranslatedBlock, ...] = ()
        self._next_id = 1
        self._identity_prefix = identity_prefix

    def clear(self) -> None:
        self._previous = ()
        self._next_id = 1

    def reconcile(
        self, blocks: tuple[OcrTextBlock, ...], width: int, height: int
    ) -> tuple[tuple[str, str, NormalizedGeometry], ...]:
        incoming = tuple(
            (comparison_key(block.text), normalized_geometry(block, width, height))
            for block in blocks
        )
        shift = self._estimate_vertical_shift(incoming)
        unused = set(range(len(self._previous)))
        identities: list[tuple[str, str, NormalizedGeometry]] = []
        for key, geometry in incoming:
            match = self._find_match(key, geometry, unused)
            if match is None and shift is not None:
                match = self._find_match(key, geometry, unused, vertical_shift=shift)
            if match is None:
                stable_id = f"{self._identity_prefix}-{self._next_id}"
                self._next_id += 1
            else:
                stable_id = self._previous[match].stable_id
                unused.remove(match)
            identities.append((stable_id, key, geometry))
        return tuple(identities)

    def commit(self, blocks: tuple[TranslatedBlock, ...]) -> None:
        self._previous = blocks

    def _find_match(
        self,
        key: str,
        geometry: NormalizedGeometry,
        unused: set[int],
        *,
        vertical_shift: float = 0.0,
    ) -> int | None:
        candidates: list[int] = []
        for index in unused:
            previous = self._previous[index]
            if (
                previous.comparison_key == key
                and previous.geometry is not None
                and _geometry_matches(previous.geometry, geometry, vertical_shift=vertical_shift)
            ):
                candidates.append(index)
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda index: abs(
                (self._previous[index].geometry.center_y + vertical_shift) - geometry.center_y  # type: ignore[union-attr]
            ),
        )

    def _estimate_vertical_shift(
        self, incoming: tuple[tuple[str, NormalizedGeometry], ...]
    ) -> float | None:
        old_by_key: dict[str, list[NormalizedGeometry]] = {}
        new_by_key: dict[str, list[NormalizedGeometry]] = {}
        for block in self._previous:
            if block.geometry is not None:
                old_by_key.setdefault(block.comparison_key, []).append(block.geometry)
        for key, geometry in incoming:
            new_by_key.setdefault(key, []).append(geometry)
        offsets: list[float] = []
        for key, old_values in old_by_key.items():
            new_values = new_by_key.get(key, [])
            if key and len(old_values) == len(new_values) == 1:
                old, new = old_values[0], new_values[0]
                if (
                    abs(old.center_x - new.center_x) <= 0.05
                    and abs(old.width - new.width) <= 0.05
                    and abs(old.height - new.height) <= 0.05
                ):
                    offsets.append(new.center_y - old.center_y)
        return statistics.median(offsets) if offsets else None


class ScanWorker(QThread):
    """Load models once and service the latest generation-aware viewport job."""

    status_changed = Signal(object, object)
    viewport_ready = Signal(object)
    scan_failed = Signal(str)
    runtime_failed = Signal(str)
    scan_started = Signal()
    scan_completed = Signal()

    def __init__(
        self,
        region: CaptionRegion,
        screen: ScreenDescriptor,
        language: SourceLanguage,
        translation_cache: dict[tuple[SourceLanguage, str], tuple[str, SourceLanguage]]
        | None = None,
        reading_direction: ReadingDirection = ReadingDirection.WEBTOON_LTR,
        experimental_vertical_ocr: bool = False,
    ) -> None:
        super().__init__()
        self.region = region
        self.screen = screen
        self.language = SourceLanguage(language)
        self.reading_direction = ReadingDirection(reading_direction)
        self.experimental_vertical_ocr = experimental_vertical_ocr
        self._jobs: queue.Queue[ScanJob | _LegacyScan] = queue.Queue(1)
        self._active = False
        self._lock = threading.Lock()
        self._legacy_generation = 0
        self.active_generation = 0
        self._reconcile_epoch = 0
        self._translation_cache = translation_cache if translation_cache is not None else {}
        self._reconciler = BlockReconciler(identity_prefix=f"block-{uuid.uuid4().hex}")

    @property
    def scan_active(self) -> bool:
        with self._lock:
            return self._active or not self._jobs.empty()

    def submit(self, job: ScanJob) -> bool:
        return self._put_latest(job)

    def request_scan(self) -> bool:
        """Compatibility entry point for a manually captured Phase 1 scan."""
        if self.scan_active or self.isInterruptionRequested():
            return False
        return self._put_latest(_LegacyScan())

    def _put_latest(self, job: ScanJob | _LegacyScan) -> bool:
        dropped = False
        while True:
            try:
                self._jobs.put_nowait(job)
                return not dropped
            except queue.Full:
                try:
                    self._jobs.get_nowait()
                    dropped = True
                except queue.Empty:
                    continue

    def clear_pending(self) -> None:
        while True:
            try:
                self._jobs.get_nowait()
            except queue.Empty:
                return

    def clear_reconciliation(self) -> None:
        with self._lock:
            self._reconciler.clear()
            self._reconcile_epoch += 1

    def run(self) -> None:
        capture = WindowsGdiCaptureProvider()
        ocr = RapidOcrEngine()
        # Assignment keeps simple injected OCR fakes compatible while configuring the real adapter.
        if isinstance(ocr, RapidOcrEngine):
            ocr.reading_direction = self.reading_direction
            ocr.source_language = self.language
            ocr.experimental_vertical_ocr = self.experimental_vertical_ocr
        translator = CTranslate2TextEngine()
        try:
            self.status_changed.emit(RuntimeStatus.READING, "Loading local models")
            ocr.load()
            translator.load()
            self.status_changed.emit(RuntimeStatus.READY, "Monitoring for scrolling")
            while not self.isInterruptionRequested():
                try:
                    requested = self._jobs.get(timeout=0.05)
                except queue.Empty:
                    continue
                if isinstance(requested, _LegacyScan):
                    self._legacy_generation += 1
                    frame = capture.capture(self.region, self.screen)
                    requested = ScanJob(
                        self._legacy_generation,
                        ViewportSnapshot(frame, fingerprint_frame(frame)),
                    )
                with self._lock:
                    self._active = True
                    self.active_generation = requested.generation
                try:
                    self._process_job(requested, ocr, translator)
                finally:
                    with self._lock:
                        self._active = False
                    self.scan_completed.emit()
        except Exception as exc:
            detail = f"Could not start scan runtime: {exc}"
            self.runtime_failed.emit(detail)
            self.status_changed.emit(RuntimeStatus.ERROR, detail)
        finally:
            capture.close()
            ocr.close()
            translator.close()

    def _process_job(
        self, job: ScanJob, ocr: RapidOcrEngine, translator: CTranslate2TextEngine
    ) -> None:
        self.scan_started.emit()
        try:
            self.status_changed.emit(RuntimeStatus.READING, f"Generation {job.generation}")
            result = ocr.recognize(job.snapshot.frame)
        except Exception as exc:
            detail = f"Viewport scan failed: {exc}"
            self.scan_failed.emit(detail)
            self.status_changed.emit(RuntimeStatus.ERROR, detail)
            return
        if self.isInterruptionRequested():
            return
        self._translate_result(job, result, translator)

    def _translate_result(
        self, job: ScanJob, result: OcrResult, translator: CTranslate2TextEngine
    ) -> None:
        frame = job.snapshot.frame
        with self._lock:
            reconcile_epoch = self._reconcile_epoch
            identities = self._reconciler.reconcile(result.blocks, frame.width, frame.height)
        translated_blocks: list[TranslatedBlock] = []
        translation_seconds = 0.0
        for block, (stable_id, key, geometry) in zip(result.blocks, identities, strict=True):
            if self.isInterruptionRequested():
                return
            cached = self._translation_cache.get((self.language, key)) if key else None
            if cached is not None:
                translated_text, detected_language = cached
                translated_blocks.append(
                    TranslatedBlock(
                        block,
                        translated_text,
                        detected_language,
                        0.0,
                        None,
                        stable_id,
                        key,
                        geometry,
                    )
                )
                continue
            self.status_changed.emit(RuntimeStatus.TRANSLATING, block.text)
            try:
                translated = translator.translate(block.text, self.language)
            except (TextTranslationError, OSError, ValueError, RuntimeError) as exc:
                translated_blocks.append(
                    TranslatedBlock(
                        block, None, self.language, 0.0, str(exc), stable_id, key, geometry
                    )
                )
                continue
            translation_seconds += translated.inference_seconds
            if key:
                self._translation_cache[(self.language, key)] = (
                    translated.text,
                    translated.source_language,
                )
            translated_blocks.append(
                TranslatedBlock(
                    block,
                    translated.text,
                    translated.source_language,
                    translated.inference_seconds,
                    None,
                    stable_id,
                    key,
                    geometry,
                )
            )
        translated_tuple = tuple(translated_blocks)
        with self._lock:
            if reconcile_epoch == self._reconcile_epoch:
                self._reconciler.commit(translated_tuple)
        self.viewport_ready.emit(
            ViewportTranslation(
                translated_tuple,
                result.inference_seconds,
                translation_seconds,
                job.generation,
                frame.width,
                frame.height,
                job.snapshot.fingerprint.digest,
                result.reading_direction,
            )
        )
        self.status_changed.emit(
            RuntimeStatus.READY,
            f"Translated {len(result.blocks)} block(s); layout={result.reading_direction.value}",
        )

    def _scan_viewport(
        self,
        capture: WindowsGdiCaptureProvider,
        ocr: RapidOcrEngine,
        translator: CTranslate2TextEngine,
    ) -> None:
        """Synchronous compatibility helper used by Phase 1 tests."""
        self._legacy_generation += 1
        frame = capture.capture(self.region, self.screen)
        self._process_job(
            ScanJob(
                self._legacy_generation,
                ViewportSnapshot(frame, fingerprint_frame(frame)),
            ),
            ocr,
            translator,
        )

    def stop(self) -> None:
        self.requestInterruption()
        self.clear_pending()
        if self.isRunning() and not self.wait(5000):
            self.runtime_failed.emit("Scan runtime did not stop within five seconds")
