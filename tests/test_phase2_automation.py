"""Phase 2 scrolling, reconciliation, caching, and history tests."""

import numpy as np

from manga_live_translator.config import CaptionRegion, SourceLanguage
from manga_live_translator.ocr import OcrResult, OcrTextBlock
from manga_live_translator.screen import (
    CapturedFrame,
    FrameFingerprint,
    VerticalScrollTracker,
    ViewportSettlingController,
    ViewportSnapshot,
    ViewportState,
    fingerprint_difference,
    fingerprint_frame,
)
from manga_live_translator.text_translation import TextTranslationError, TextTranslationResult
from manga_live_translator.ui.panel import TranslationPanel
from manga_live_translator.workers.scan import (
    BlockReconciler,
    ScanJob,
    ScanWorker,
    TranslatedBlock,
    ViewportTranslation,
)

REGION = CaptionRegion("Display", 100, 100, 1.0, 0, 0, 10, 10)


def frame(value: int, captured_at: float) -> CapturedFrame:
    return CapturedFrame(
        bytes([value, value, value, 255]) * 100,
        10,
        10,
        40,
        captured_at,
        REGION,
    )


def fingerprint(pixels: np.ndarray) -> FrameFingerprint:
    data = pixels.astype(np.uint8).tobytes()
    return FrameFingerprint(data, pixels.shape[1], pixels.shape[0], "fixture")


def test_vertical_scroll_tracker_follows_both_directions_and_rejects_unsafe_motion() -> None:
    random = np.random.default_rng(42)
    original = random.integers(0, 256, size=(32, 24), dtype=np.uint8)
    moved_up = np.empty_like(original)
    moved_up[:-3] = original[3:]
    moved_up[-3:] = random.integers(0, 256, size=(3, 24), dtype=np.uint8)
    tracker = VerticalScrollTracker()
    upward = tracker.estimate(fingerprint(original), fingerprint(moved_up), physical_height=640)
    assert upward.trackable and upward.physical_dy == -60
    downward = tracker.estimate(fingerprint(moved_up), fingerprint(original), physical_height=640)
    assert downward.trackable and downward.physical_dy == 60

    flat = fingerprint(np.full((32, 24), 127, dtype=np.uint8))
    assert not tracker.estimate(flat, flat, physical_height=640).trackable
    unrelated = fingerprint(random.integers(0, 256, size=(32, 24), dtype=np.uint8))
    assert not tracker.estimate(fingerprint(original), unrelated, physical_height=640).trackable
    resized = fingerprint(random.integers(0, 256, size=(30, 24), dtype=np.uint8))
    assert not tracker.estimate(fingerprint(original), resized, physical_height=640).trackable


def block(text: str, left: float, top: float) -> OcrTextBlock:
    return OcrTextBlock(
        text,
        0.9,
        ((left, top), (left + 3, top), (left + 3, top + 1), (left, top + 1)),
    )


def test_fingerprints_are_bounded_and_validate_buffers() -> None:
    first = fingerprint_frame(frame(0, 0), maximum_size=4)
    second = fingerprint_frame(frame(255, 1), maximum_size=4)
    assert (first.width, first.height, len(first.pixels)) == (4, 4, 16)
    assert fingerprint_difference(first, first) == 0
    assert fingerprint_difference(first, second) == 1
    malformed = CapturedFrame(b"bad", 10, 10, 40, 0, REGION)
    try:
        fingerprint_frame(malformed)
    except ValueError as exc:
        assert "invalid pixel buffer" in str(exc)
    else:
        raise AssertionError("malformed frame was accepted")


def test_settling_state_machine_accepts_once_and_resets_on_motion() -> None:
    controller = ViewportSettlingController(threshold=0.015, settle_seconds=0.4)
    assert controller.observe(frame(0, 0.0)) is None
    assert controller.state is ViewportState.MOVING
    assert controller.observe(frame(0, 0.2)) is None
    assert controller.state is ViewportState.SETTLING
    assert controller.observe(frame(0, 0.59)) is None
    accepted = controller.observe(frame(0, 0.6))
    assert accepted is not None
    assert controller.state is ViewportState.PROCESSING
    controller.mark_stable()
    assert controller.observe(frame(1, 0.8)) is None
    assert controller.state is ViewportState.STABLE
    assert controller.observe(frame(255, 1.0)) is None
    assert controller.state is ViewportState.MOVING
    assert controller.observe(frame(255, 1.2)) is None
    assert controller.observe(frame(255, 1.6)) is not None
    controller.reset()
    assert controller.state is ViewportState.MOVING


def test_manual_snapshot_is_immediate() -> None:
    controller = ViewportSettlingController()
    snapshot = controller.manual_snapshot(frame(10, 1.0))
    assert snapshot.frame.captured_at == 1.0
    assert controller.state is ViewportState.PROCESSING


def test_post_render_frame_can_be_adopted_without_triggering_a_feedback_scan() -> None:
    controller = ViewportSettlingController(threshold=0.015, settle_seconds=0.4)
    overlay_frame = frame(220, 1.0)
    controller.adopt_stable(overlay_frame)
    assert controller.state is ViewportState.STABLE
    assert controller.observe(frame(220, 1.2)) is None
    assert controller.observe(frame(220, 2.0)) is None
    assert controller.state is ViewportState.STABLE
    assert controller.observe(frame(0, 2.2)) is None
    assert controller.state is ViewportState.MOVING


def translated(source: OcrTextBlock, stable_id: str, key: str) -> TranslatedBlock:
    return TranslatedBlock(
        source,
        f"EN:{source.text}",
        SourceLanguage.JAPANESE,
        0.1,
        stable_id=stable_id,
        comparison_key=key,
    )


def test_reconciler_handles_direct_shifted_and_repeated_dialogue() -> None:
    reconciler = BlockReconciler()
    original = (block("same", 1, 6), block("anchor", 5, 7))
    identities = reconciler.reconcile(original, 10, 10)
    committed = tuple(
        TranslatedBlock(
            item,
            f"EN:{item.text}",
            SourceLanguage.JAPANESE,
            0.1,
            stable_id=identity[0],
            comparison_key=identity[1],
            geometry=identity[2],
        )
        for item, identity in zip(original, identities, strict=True)
    )
    reconciler.commit(committed)
    shifted = (block("same", 1, 2), block("anchor", 5, 3), block("same", 6, 8))
    next_identities = reconciler.reconcile(shifted, 10, 10)
    assert next_identities[0][0] == identities[0][0]
    assert next_identities[1][0] == identities[1][0]
    assert next_identities[2][0] not in {identities[0][0], identities[1][0]}
    reconciler.clear()
    assert reconciler.reconcile((block("same", 1, 2),), 10, 10)[0][0] == "block-1"


class Translator:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def translate(self, text: str, language: SourceLanguage) -> TextTranslationResult:
        self.calls.append(text)
        if text == "bad":
            raise TextTranslationError("failure")
        return TextTranslationResult(f"EN:{text}", language, "en", 0.1)


def test_scan_jobs_replace_stale_and_translation_cache_skips_successes(qt_app: object) -> None:
    from manga_live_translator.screen import ScreenDescriptor

    screen = ScreenDescriptor("Display", 0, 0, 100, 100, 1.0)
    worker = ScanWorker(REGION, screen, SourceLanguage.JAPANESE)
    snapshot = ViewportSnapshot(frame(0, 0), fingerprint_frame(frame(0, 0)))
    assert worker.submit(ScanJob(1, snapshot))
    assert not worker.submit(ScanJob(2, snapshot))
    queued = worker._jobs.get_nowait()
    assert isinstance(queued, ScanJob) and queued.generation == 2

    translator = Translator()
    results: list[ViewportTranslation] = []
    worker.viewport_ready.connect(results.append)
    ocr_result = OcrResult(
        (block("cached", 1, 1), block("bad", 1, 3)),
        "cached bad",
        "cached bad",
        0.9,
        0,
        0.2,
    )
    worker._translate_result(ScanJob(3, snapshot), ocr_result, translator)  # type: ignore[arg-type]
    worker._translate_result(ScanJob(4, snapshot), ocr_result, translator)  # type: ignore[arg-type]
    assert translator.calls == ["cached", "bad", "bad"]
    assert results[1].blocks[0].inference_seconds == 0
    assert results[1].generation == 4


def test_panel_reconciles_and_evicts_oldest(qt_app: object) -> None:
    panel = TranslationPanel(maximum_history=2)
    first = translated(block("one", 1, 1), "one", "one")
    second = translated(block("two", 1, 2), "two", "two")
    updated = translated(block("one updated", 1, 1), "one", "one")
    third = translated(block("three", 1, 3), "three", "three")
    panel.reconcile_results(ViewportTranslation((first, second), 0, 0))
    panel.reconcile_results(ViewportTranslation((updated, third), 0, 0))
    assert [item.stable_id for item in panel.blocks] == ["two", "three"]
    panel.clear_results()
    assert panel.blocks == []
