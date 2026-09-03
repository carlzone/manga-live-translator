import time

from PySide6.QtCore import QPoint

from manga_live_translator.config import CaptionRegion
from manga_live_translator.screen import (
    CapturedFrame,
    FrameChangeDetector,
    LatestFrameQueue,
    RegionCaptureWorker,
    ScreenDescriptor,
    validate_caption_region,
)
from manga_live_translator.ui.region_selector import RegionSelector, region_from_points

SCREEN = ScreenDescriptor("Display 1", -100, 20, 200, 100, 1.25)
REGION = CaptionRegion("Display 1", 200, 100, 1.25, 20, 30, 80, 40)


def make_frame(value: int, *, captured_at: float = 1.0) -> CapturedFrame:
    return CapturedFrame(bytes([value, value, value, 255]) * 8, 4, 2, 16, captured_at, REGION)


def test_region_validation_checks_identity_resolution_dpi_and_bounds() -> None:
    assert validate_caption_region(REGION, [SCREEN]) == (SCREEN, None)
    assert "unavailable" in validate_caption_region(REGION, [])[1]  # type: ignore[operator]
    changed = ScreenDescriptor("Display 1", 0, 0, 200, 100, 1.5)
    assert "scaling" in validate_caption_region(REGION, [changed])[1]  # type: ignore[operator]
    assert "Select" in validate_caption_region(None, [SCREEN])[1]  # type: ignore[operator]


def test_reverse_drag_normalizes_and_clamps_to_one_screen() -> None:
    region = region_from_points(SCREEN, QPoint(180, 90), QPoint(20, 30))
    assert region == CaptionRegion("Display 1", 200, 100, 1.25, 20, 30, 160, 60)
    clamped = region_from_points(SCREEN, QPoint(-50, -20), QPoint(300, 200))
    assert clamped is not None
    assert (clamped.x, clamped.y, clamped.width, clamped.height) == (0, 0, 200, 100)
    assert region_from_points(SCREEN, QPoint(2, 2), QPoint(4, 4)) is None


def test_region_selector_coordinates_surfaces_and_completion(qt_app: object) -> None:
    selected: list[CaptionRegion] = []
    cancelled: list[bool] = []
    selector = RegionSelector([SCREEN])
    selector.region_selected.connect(selected.append)
    selector.show()
    assert selector.surfaces[0].isVisible()
    selector._complete(REGION)
    assert selected == [REGION]
    assert not selector.surfaces[0].isVisible()

    selector = RegionSelector([SCREEN])
    selector.cancelled.connect(lambda: cancelled.append(True))
    selector.show()
    selector.cancel()
    assert cancelled == [True]
    qt_app.processEvents()  # type: ignore[attr-defined]


def test_latest_frame_queue_replaces_stale_frames() -> None:
    queue = LatestFrameQueue()
    first, latest = make_frame(0), make_frame(255, captured_at=2)
    queue.put(first)
    queue.put(latest)
    assert queue.take() is latest
    assert queue.take() is None
    queue.put(first)
    queue.clear()
    assert queue.take() is None


def test_change_detector_emits_first_and_material_changes() -> None:
    detector = FrameChangeDetector(0.1)
    assert detector.changed(make_frame(0))
    assert not detector.changed(make_frame(5))
    assert detector.changed(make_frame(255))
    detector.reset()
    assert detector.changed(make_frame(255))


class FakeCaptureProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    def capture(self, region: CaptionRegion, screen: ScreenDescriptor) -> CapturedFrame:
        del screen
        self.calls += 1
        value = min(255, self.calls * 50)
        return CapturedFrame(
            bytes([value, value, value, 255]) * 8,
            4,
            2,
            16,
            time.monotonic(),
            region,
        )

    def close(self) -> None:
        self.closed = True


def test_region_worker_is_bounded_restartable_and_closes(qt_app: object) -> None:
    provider = FakeCaptureProvider()
    worker = RegionCaptureWorker(provider, REGION, SCREEN, frames_per_second=100)
    emitted: list[CapturedFrame] = []
    worker.frame_changed.connect(emitted.append)
    worker.start_capture()
    assert worker.wait(35) is False
    qt_app.processEvents()  # type: ignore[attr-defined]
    worker.stop_capture()
    first_run_calls = provider.calls
    assert first_run_calls >= 1
    assert emitted
    worker.start_capture()
    assert worker.wait(25) is False
    worker.close()
    assert provider.calls > first_run_calls
    assert provider.closed
    assert worker.frames.take() is None
