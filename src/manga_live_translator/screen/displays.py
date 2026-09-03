"""Display discovery and saved caption-region validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PySide6.QtGui import QGuiApplication, QScreen

from manga_live_translator.config import CaptionRegion


@dataclass(frozen=True, slots=True)
class ScreenDescriptor:
    name: str
    x: int
    y: int
    width: int
    height: int
    device_pixel_ratio: float

    @classmethod
    def from_qscreen(cls, screen: QScreen) -> ScreenDescriptor:
        geometry = screen.geometry()
        return cls(
            name=screen.name(),
            x=geometry.x(),
            y=geometry.y(),
            width=geometry.width(),
            height=geometry.height(),
            device_pixel_ratio=float(screen.devicePixelRatio()),
        )


class ScreenProvider(Protocol):
    def screens(self) -> list[ScreenDescriptor]: ...


class QtScreenProvider:
    def screens(self) -> list[ScreenDescriptor]:
        return [ScreenDescriptor.from_qscreen(screen) for screen in QGuiApplication.screens()]


def validate_caption_region(
    region: CaptionRegion | None, screens: list[ScreenDescriptor]
) -> tuple[ScreenDescriptor | None, str | None]:
    """Resolve a saved region, rejecting changed or unavailable displays."""
    if region is None:
        return None, "Select a caption region before starting"
    screen = next((item for item in screens if item.name == region.screen_name), None)
    if screen is None:
        return None, "The saved display is unavailable; select the caption region again"
    metadata_matches = (
        screen.width == region.screen_width
        and screen.height == region.screen_height
        and abs(screen.device_pixel_ratio - region.device_pixel_ratio) < 0.01
    )
    if not metadata_matches:
        return None, "The saved display resolution or scaling changed; select the region again"
    if (
        region.x < 0
        or region.y < 0
        or region.x + region.width > screen.width
        or region.y + region.height > screen.height
    ):
        return None, "The saved caption region is outside the display; select it again"
    return screen, None
