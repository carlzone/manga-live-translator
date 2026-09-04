"""Coordinate-aligned, click-through translation overlay and pure box layout."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication, QShowEvent
from PySide6.QtWidgets import QLabel, QWidget

from manga_live_translator.config import CaptionRegion
from manga_live_translator.ocr import BlockOrientation
from manga_live_translator.ocr.engine import BoundingBox
from manga_live_translator.screen import ScreenDescriptor
from manga_live_translator.workers.scan import ViewportTranslation

TextMeasure = Callable[[str, int, int], tuple[int, int]]


@dataclass(frozen=True, slots=True)
class OverlayBlock:
    stable_id: str
    translation: str
    source_polygon: BoundingBox
    orientation: BlockOrientation
    reading_order: int


@dataclass(frozen=True, slots=True)
class OverlayRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def intersects(self, other: OverlayRect) -> bool:
        return not (
            self.right <= other.x
            or other.right <= self.x
            or self.bottom <= other.y
            or other.bottom <= self.y
        )


@dataclass(frozen=True, slots=True)
class PositionedOverlayBlock:
    block: OverlayBlock
    rect: OverlayRect
    font_size: int
    collision_adjusted: bool


@dataclass(frozen=True, slots=True)
class CaptureExclusionStatus:
    mode: str = "not_attempted"
    verified: bool = False
    error_code: int = 0


def configure_capture_exclusion(hwnd: int, user32: Any = None) -> CaptureExclusionStatus:
    """Apply and verify the strongest available Windows display affinity."""
    if sys.platform != "win32" and user32 is None:
        return CaptureExclusionStatus("unsupported")
    import ctypes
    from ctypes import wintypes

    library = user32 or ctypes.WinDLL("user32", use_last_error=True)
    set_affinity = library.SetWindowDisplayAffinity
    get_affinity = library.GetWindowDisplayAffinity
    set_affinity.argtypes = (wintypes.HWND, wintypes.DWORD)
    set_affinity.restype = wintypes.BOOL
    get_affinity.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    get_affinity.restype = wintypes.BOOL
    last_error = 0
    for value, mode in ((0x11, "exclude"), (0x01, "monitor")):
        ctypes.set_last_error(0)
        if not set_affinity(wintypes.HWND(hwnd), wintypes.DWORD(value)):
            last_error = ctypes.get_last_error()
            continue
        actual = wintypes.DWORD()
        if get_affinity(wintypes.HWND(hwnd), ctypes.byref(actual)) and actual.value == value:
            return CaptureExclusionStatus(mode, True, 0)
        last_error = ctypes.get_last_error()
    return CaptureExclusionStatus("failed", False, last_error)


def scale_polygon_bounds(
    polygon: BoundingBox,
    *,
    frame_width: int,
    frame_height: int,
    overlay_width: int,
    overlay_height: int,
) -> OverlayRect:
    """Map a physical-frame polygon into logical overlay coordinates."""
    if min(frame_width, frame_height, overlay_width, overlay_height) <= 0:
        raise ValueError("frame and overlay dimensions must be positive")
    scale_x = overlay_width / frame_width
    scale_y = overlay_height / frame_height
    xs = [point[0] * scale_x for point in polygon]
    ys = [point[1] * scale_y for point in polygon]
    left = max(0, min(overlay_width - 1, round(min(xs))))
    top = max(0, min(overlay_height - 1, round(min(ys))))
    right = max(left + 1, min(overlay_width, round(max(xs))))
    bottom = max(top + 1, min(overlay_height, round(max(ys))))
    return OverlayRect(left, top, right - left, bottom - top)


def _clamped_rect(x: int, y: int, width: int, height: int, bounds: tuple[int, int]) -> OverlayRect:
    bound_width, bound_height = bounds
    width = min(max(1, width), bound_width)
    height = min(max(1, height), bound_height)
    return OverlayRect(
        min(max(0, x), bound_width - width),
        min(max(0, y), bound_height - height),
        width,
        height,
    )


def layout_translation_boxes(
    blocks: tuple[OverlayBlock, ...],
    *,
    frame_size: tuple[int, int],
    overlay_size: tuple[int, int],
    font_size: int,
    minimum_font_size: int = 10,
    padding: int = 6,
    measure: TextMeasure,
) -> tuple[PositionedOverlayBlock, ...]:
    """Lay out source-covering boxes, preferring symmetric expansion from the source."""
    if minimum_font_size <= 0 or font_size < minimum_font_size or padding < 0:
        raise ValueError("invalid font size or padding")
    frame_width, frame_height = frame_size
    overlay_width, overlay_height = overlay_size
    ordered_blocks = sorted(blocks, key=lambda item: item.reading_order)
    source_rects = tuple(
        scale_polygon_bounds(
            block.source_polygon,
            frame_width=frame_width,
            frame_height=frame_height,
            overlay_width=overlay_width,
            overlay_height=overlay_height,
        )
        for block in ordered_blocks
    )
    placed: list[PositionedOverlayBlock] = []
    occupied: list[OverlayRect] = []
    for block_index, (block, source) in enumerate(zip(ordered_blocks, source_rects, strict=True)):
        selected: OverlayRect | None = None
        selected_font = minimum_font_size
        adjusted = False
        for candidate_font in range(font_size, minimum_font_size - 1, -1):
            wrap_width = max(
                1, min(overlay_width - padding * 2, max(source.width, candidate_font * 8))
            )
            measured_width, measured_height = measure(block.translation, candidate_font, wrap_width)
            width = max(source.width, measured_width + padding * 2)
            height = max(source.height, measured_height + padding * 2)
            centered_x = source.x - (width - source.width) // 2
            centered_y = source.y - (height - source.height) // 2
            candidates = (
                _clamped_rect(centered_x, centered_y, width, height, overlay_size),
                _clamped_rect(centered_x, source.y, width, height, overlay_size),
                _clamped_rect(centered_x, source.bottom - height, width, height, overlay_size),
                _clamped_rect(source.x, centered_y, width, height, overlay_size),
                _clamped_rect(source.right - width, centered_y, width, height, overlay_size),
            )
            collision_free = next(
                (
                    candidate
                    for candidate in candidates
                    if not any(candidate.intersects(old) for old in occupied)
                    and not any(
                        candidate.intersects(other_source)
                        for index, other_source in enumerate(source_rects)
                        if index != block_index
                    )
                ),
                None,
            )
            if collision_free is not None:
                selected = collision_free
                selected_font = candidate_font
                adjusted = collision_free != candidates[0] or candidate_font != font_size
                break
            selected = candidates[0]
            selected_font = candidate_font
        assert selected is not None
        if any(selected.intersects(old) for old in occupied):
            adjusted = True
        occupied.append(selected)
        placed.append(PositionedOverlayBlock(block, selected, selected_font, adjusted))
    return tuple(placed)


class TranslationOverlay(QWidget):
    """A transparent region-sized window containing opaque translated-text labels."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("TranslationOverlay { background: transparent; }")
        self._labels: dict[str, QLabel] = {}
        self._ordered_blocks: tuple[OverlayBlock, ...] = ()
        self.font_size = 18
        self.opacity = 0.9
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.collision_adjustments = 0
        self._fractional_dy = 0.0
        self.capture_exclusion = CaptureExclusionStatus()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._exclude_from_capture()

    def _exclude_from_capture(self) -> None:
        """Keep the visible overlay out of GDI screen captures on Windows."""
        self.capture_exclusion = configure_capture_exclusion(int(self.winId()))

    @property
    def rendered_box_count(self) -> int:
        return len(self._labels)

    def align_to_region(self, region: CaptionRegion, screen: ScreenDescriptor) -> None:
        self.setGeometry(screen.x + region.x, screen.y + region.y, region.width, region.height)

    def set_appearance(self, *, font_size: int, opacity: float) -> None:
        self.font_size = font_size
        self.opacity = opacity

    @staticmethod
    def _measure(text: str, font_size: int, wrap_width: int) -> tuple[int, int]:
        font = QFont()
        font.setPixelSize(font_size)
        bounds = QFontMetrics(font).boundingRect(
            QRect(0, 0, max(1, wrap_width), 10000),
            Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter,
            text,
        )
        return bounds.width(), bounds.height()

    def reconcile_results(self, viewport: ViewportTranslation) -> None:
        if viewport.frame_width <= 0 or viewport.frame_height <= 0:
            self.clear_results()
            return
        blocks = tuple(
            OverlayBlock(
                result.stable_id or f"generation-{viewport.generation}-{index}",
                result.translation,
                result.source.box,
                result.source.orientation,
                index,
            )
            for index, result in enumerate(viewport.blocks)
            if result.translation and result.translation.strip()
        )
        positioned = layout_translation_boxes(
            blocks,
            frame_size=(viewport.frame_width, viewport.frame_height),
            overlay_size=(self.width(), self.height()),
            font_size=self.font_size,
            measure=self._measure,
        )
        active_ids = {item.block.stable_id for item in positioned}
        for stable_id in set(self._labels) - active_ids:
            self._labels.pop(stable_id).deleteLater()
        alpha = round(self.opacity * 255)
        for item in positioned:
            label = self._labels.get(item.block.stable_id)
            if label is None:
                label = QLabel(self)
                label.setWordWrap(True)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._labels[item.block.stable_id] = label
            label.setText(item.block.translation)
            font = label.font()
            font.setPixelSize(item.font_size)
            label.setFont(font)
            label.setStyleSheet(
                f"QLabel {{ color: #111; background-color: rgba(255, 255, 255, {alpha}); "
                "border: 1px solid #888; border-radius: 4px; padding: 2px; }}"
            )
            rect = item.rect
            label.setGeometry(rect.x, rect.y, rect.width, rect.height)
            label.show()
        self._ordered_blocks = blocks
        self.scale_x = self.width() / viewport.frame_width
        self.scale_y = self.height() / viewport.frame_height
        self.collision_adjustments = sum(item.collision_adjusted for item in positioned)
        self._fractional_dy = 0.0

    def translate_vertical(self, logical_dy: float) -> int:
        """Move visible boxes with scrolling and remove boxes fully outside the region."""
        total = logical_dy + self._fractional_dy
        pixel_dy = round(total)
        self._fractional_dy = total - pixel_dy
        if pixel_dy == 0:
            return 0
        removed: set[str] = set()
        for stable_id, label in self._labels.items():
            label.move(label.x(), label.y() + pixel_dy)
            if label.geometry().bottom() < 0 or label.y() >= self.height():
                label.deleteLater()
                removed.add(stable_id)
        for stable_id in removed:
            self._labels.pop(stable_id)
        if removed:
            self._ordered_blocks = tuple(
                block for block in self._ordered_blocks if block.stable_id not in removed
            )
        return len(removed)

    def clear_results(self) -> None:
        for label in self._labels.values():
            label.hide()
            label.deleteLater()
        self._labels.clear()
        self._ordered_blocks = ()
        self.collision_adjustments = 0
        self._fractional_dy = 0.0

    def copy_all(self) -> str:
        text = "\n\n".join(block.translation for block in self._ordered_blocks)
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        return text
