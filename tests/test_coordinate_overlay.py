from PySide6.QtCore import Qt

from manga_live_translator.config import CaptionRegion, SourceLanguage
from manga_live_translator.ocr import BlockOrientation, OcrTextBlock
from manga_live_translator.screen import ScreenDescriptor
from manga_live_translator.ui.overlay import (
    OverlayBlock,
    TranslationOverlay,
    configure_capture_exclusion,
    layout_translation_boxes,
    scale_polygon_bounds,
)
from manga_live_translator.workers.scan import TranslatedBlock, ViewportTranslation


def polygon(left: float, top: float, right: float, bottom: float):  # type: ignore[no-untyped-def]
    return ((left, top), (right, top), (right, bottom), (left, bottom))


def measure(text: str, font_size: int, wrap_width: int) -> tuple[int, int]:
    characters_per_line = max(1, wrap_width // max(1, font_size // 2))
    lines = (len(text) + characters_per_line - 1) // characters_per_line
    return min(wrap_width, len(text) * max(1, font_size // 2)), lines * font_size


def test_polygon_scaling_handles_all_dpi_ratios_and_clamps() -> None:
    source = polygon(100, 50, 300, 150)
    for ratio in (1.0, 1.25, 1.5, 2.0):
        width, height = round(800 * ratio), round(600 * ratio)
        rect = scale_polygon_bounds(
            source,
            frame_width=width,
            frame_height=height,
            overlay_width=800,
            overlay_height=600,
        )
        assert rect.x == round(100 / ratio)
        assert rect.y == round(50 / ratio)
    clamped = scale_polygon_bounds(
        polygon(-10, -20, 900, 700),
        frame_width=800,
        frame_height=600,
        overlay_width=800,
        overlay_height=600,
    )
    assert (clamped.x, clamped.y, clamped.right, clamped.bottom) == (0, 0, 800, 600)


def test_layout_covers_source_expands_and_avoids_collisions() -> None:
    blocks = (
        OverlayBlock(
            "one",
            "A longer translation",
            polygon(10, 10, 40, 25),
            BlockOrientation.HORIZONTAL,
            0,
        ),
        OverlayBlock(
            "two",
            "Second translation",
            polygon(10, 45, 40, 60),
            BlockOrientation.HORIZONTAL,
            1,
        ),
    )
    result = layout_translation_boxes(
        blocks,
        frame_size=(100, 100),
        overlay_size=(100, 100),
        font_size=16,
        minimum_font_size=10,
        measure=measure,
    )
    assert result[0].rect.x <= 10 and result[0].rect.y <= 10
    assert result[0].rect.right >= 40 and result[0].rect.bottom >= 25
    assert not result[0].rect.intersects(result[1].rect)
    assert any(item.collision_adjusted for item in result)


def test_layout_expands_around_source_center_when_unconstrained() -> None:
    source = polygon(80, 80, 120, 100)
    result = layout_translation_boxes(
        (
            OverlayBlock(
                "centered",
                "A translation that needs a larger box",
                source,
                BlockOrientation.HORIZONTAL,
                0,
            ),
        ),
        frame_size=(200, 200),
        overlay_size=(200, 200),
        font_size=16,
        minimum_font_size=10,
        measure=measure,
    )
    rect = result[0].rect
    assert rect.width > 40 or rect.height > 20
    assert abs((rect.x * 2 + rect.width) - 200) <= 1
    assert abs((rect.y * 2 + rect.height) - 180) <= 1


def test_overlay_alignment_reconciliation_copy_and_flags(qt_app: object) -> None:
    overlay = TranslationOverlay()
    region = CaptionRegion("Secondary", 1920, 1080, 1.5, 100, 200, 400, 300)
    screen = ScreenDescriptor("Secondary", -1920, 100, 1920, 1080, 1.5)
    overlay.align_to_region(region, screen)
    assert overlay.geometry().getRect() == (-1820, 300, 400, 300)
    assert overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert overlay.windowFlags() & Qt.WindowType.Tool
    first = TranslatedBlock(
        OcrTextBlock("source", 0.9, polygon(15, 20, 90, 50)),
        "English",
        SourceLanguage.JAPANESE,
        0.1,
        stable_id="stable-one",
    )
    failed = TranslatedBlock(
        OcrTextBlock("bad", 0.9, polygon(15, 80, 90, 110)),
        None,
        SourceLanguage.JAPANESE,
        0.0,
        error="failure",
        stable_id="failed",
    )
    overlay.reconcile_results(ViewportTranslation((first, failed), 0.1, 0.1, 1, 600, 450))
    assert overlay.rendered_box_count == 1
    assert overlay.copy_all() == "English"
    replacement = TranslatedBlock(
        OcrTextBlock("new", 0.9, polygon(100, 120, 180, 150)),
        "Replacement",
        SourceLanguage.JAPANESE,
        0.1,
        stable_id="stable-two",
    )
    overlay.reconcile_results(ViewportTranslation((replacement,), 0.1, 0.1, 2, 600, 450))
    assert set(overlay._labels) == {"stable-two"}
    assert overlay.copy_all() == "Replacement"
    label = overlay._labels["stable-two"]
    original_y = label.y()
    assert overlay.translate_vertical(-20.5) == 0
    assert label.y() == original_y - 20
    assert overlay.translate_vertical(-1000) == 1
    assert overlay.rendered_box_count == 0
    overlay.clear_results()
    assert overlay.rendered_box_count == 0


def test_capture_exclusion_is_typed_verified_and_falls_back() -> None:
    import ctypes
    from ctypes import wintypes

    class Function:
        def __init__(self, callback):  # type: ignore[no-untyped-def]
            self.callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):  # type: ignore[no-untyped-def]
            return self.callback(*args)

    class User32:
        def __init__(self, *, fail_exclude: bool = False, mismatch: bool = False) -> None:
            self.value = 0

            def set_affinity(hwnd, value):  # type: ignore[no-untyped-def]
                assert isinstance(hwnd, wintypes.HWND)
                requested = int(value.value)
                if fail_exclude and requested == 0x11:
                    return 0
                self.value = requested
                return 1

            def get_affinity(_hwnd, output):  # type: ignore[no-untyped-def]
                actual = 0 if mismatch else self.value
                ctypes.cast(output, ctypes.POINTER(wintypes.DWORD)).contents.value = actual
                return 1

            self.SetWindowDisplayAffinity = Function(set_affinity)
            self.GetWindowDisplayAffinity = Function(get_affinity)

    excluded = configure_capture_exclusion(0x123456789, User32())
    assert excluded.mode == "exclude" and excluded.verified
    fallback = configure_capture_exclusion(0x123456789, User32(fail_exclude=True))
    assert fallback.mode == "monitor" and fallback.verified
    failed = configure_capture_exclusion(0x123456789, User32(mismatch=True))
    assert failed.mode == "failed" and not failed.verified
