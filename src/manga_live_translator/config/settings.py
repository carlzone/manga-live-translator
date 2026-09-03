"""Typed manga settings with resilient JSON persistence."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from manga_live_translator.paths import settings_path


class SourceLanguage(StrEnum):
    JAPANESE = "ja"
    CHINESE = "zh"
    AUTO = "auto"


class PanelPosition(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    BOTTOM = "bottom"


@dataclass(frozen=True, slots=True)
class CaptionRegion:
    screen_name: str
    screen_width: int
    screen_height: int
    device_pixel_ratio: float
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if not self.screen_name.strip():
            raise ValueError("screen_name cannot be empty")
        if self.screen_width <= 0 or self.screen_height <= 0 or self.device_pixel_ratio <= 0:
            raise ValueError("screen metadata must be positive")
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("region coordinates and dimensions are invalid")
        if self.x + self.width > self.screen_width or self.y + self.height > self.screen_height:
            raise ValueError("region must fit within the selected screen")

    @classmethod
    def from_dict(cls, raw: Any) -> CaptionRegion | None:
        if not isinstance(raw, dict):
            return None
        try:
            return cls(
                str(raw["screen_name"]),
                int(raw["screen_width"]),
                int(raw["screen_height"]),
                float(raw["device_pixel_ratio"]),
                int(raw["x"]),
                int(raw["y"]),
                int(raw["width"]),
                int(raw["height"]),
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class AppSettings:
    caption_region: CaptionRegion | None = None
    source_language: SourceLanguage = SourceLanguage.AUTO
    target_language: str = "en"
    panel_position: PanelPosition = PanelPosition.RIGHT
    font_size: int = 18
    overlay_opacity: float = 0.9
    show_original_text: bool = True
    click_through: bool = False

    def __post_init__(self) -> None:
        if self.target_language != "en":
            raise ValueError("target_language must be 'en'")
        if not 12 <= self.font_size <= 48:
            raise ValueError("font_size must be between 12 and 48")
        if not 0.1 <= self.overlay_opacity <= 1.0:
            raise ValueError("overlay_opacity must be between 0.1 and 1.0")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AppSettings:
        defaults = cls()
        region = CaptionRegion.from_dict(raw.get("caption_region"))
        try:
            language = SourceLanguage(raw.get("source_language", defaults.source_language))
        except (TypeError, ValueError):
            language = defaults.source_language
        try:
            position = PanelPosition(raw.get("panel_position", defaults.panel_position))
        except (TypeError, ValueError):
            position = defaults.panel_position
        font_size = raw.get("font_size", defaults.font_size)
        opacity = raw.get("overlay_opacity", defaults.overlay_opacity)
        show_original = raw.get("show_original_text")
        click_through = raw.get("click_through")
        return cls(
            caption_region=region,
            source_language=language,
            panel_position=position,
            font_size=font_size
            if type(font_size) is int and 12 <= font_size <= 48
            else defaults.font_size,
            overlay_opacity=float(opacity)
            if type(opacity) in (int, float) and 0.1 <= float(opacity) <= 1
            else defaults.overlay_opacity,
            show_original_text=show_original
            if isinstance(show_original, bool)
            else defaults.show_original_text,
            click_through=click_through
            if isinstance(click_through, bool)
            else defaults.click_through,
        )


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings_path()

    def load(self) -> AppSettings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return AppSettings.from_dict(raw) if isinstance(raw, dict) else AppSettings()
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as handle:
                json.dump(settings.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
