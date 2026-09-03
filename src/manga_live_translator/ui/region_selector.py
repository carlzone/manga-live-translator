"""Translucent per-display reader-region selection surfaces."""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from manga_live_translator.config import CaptionRegion
from manga_live_translator.screen import ScreenDescriptor

MINIMUM_REGION_SIZE = 8


def region_from_points(
    screen: ScreenDescriptor, start: QPoint, end: QPoint
) -> CaptionRegion | None:
    start_x = min(max(start.x(), 0), screen.width)
    start_y = min(max(start.y(), 0), screen.height)
    end_x = min(max(end.x(), 0), screen.width)
    end_y = min(max(end.y(), 0), screen.height)
    left, top = min(start_x, end_x), min(start_y, end_y)
    width, height = abs(end_x - start_x), abs(end_y - start_y)
    if width < MINIMUM_REGION_SIZE or height < MINIMUM_REGION_SIZE:
        return None
    return CaptionRegion(
        screen_name=screen.name,
        screen_width=screen.width,
        screen_height=screen.height,
        device_pixel_ratio=screen.device_pixel_ratio,
        x=left,
        y=top,
        width=width,
        height=height,
    )


class RegionSelectionSurface(QWidget):
    selected = Signal(object)
    cancelled = Signal()

    def __init__(self, screen: ScreenDescriptor) -> None:
        super().__init__(None)
        self.screen_descriptor = screen
        self._start: QPoint | None = None
        self._end: QPoint | None = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.x, screen.y, screen.width, screen.height)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() is Qt.MouseButton.LeftButton:
            self._start = event.position().toPoint()
            self._end = self._start
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._start is not None:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() is not Qt.MouseButton.LeftButton or self._start is None:
            return
        self._end = event.position().toPoint()
        region = region_from_points(self.screen_descriptor, self._start, self._end)
        self._start = None
        if region is not None:
            self.selected.emit(region)
        else:
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 105))
        if self._start is not None and self._end is not None:
            rectangle = QRect(self._start, self._end).normalized().intersected(self.rect())
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rectangle, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(80, 180, 255), 2))
            painter.drawRect(rectangle)


class RegionSelector(QObject):
    region_selected = Signal(object)
    cancelled = Signal()

    def __init__(self, screens: list[ScreenDescriptor]) -> None:
        super().__init__()
        self.surfaces = [RegionSelectionSurface(screen) for screen in screens]
        for surface in self.surfaces:
            surface.selected.connect(self._complete)
            surface.cancelled.connect(self.cancel)

    def show(self) -> None:
        for surface in self.surfaces:
            surface.show()
        if self.surfaces:
            self.surfaces[0].activateWindow()
            self.surfaces[0].setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _complete(self, region: CaptionRegion) -> None:
        self._close_surfaces()
        self.region_selected.emit(region)

    def cancel(self) -> None:
        self._close_surfaces()
        self.cancelled.emit()

    def _close_surfaces(self) -> None:
        for surface in self.surfaces:
            surface.close()
        QApplication.restoreOverrideCursor()
