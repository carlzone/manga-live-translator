"""OCR domain types and engine interface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from manga_live_translator.config import ReadingDirection

if TYPE_CHECKING:
    from manga_live_translator.screen import CapturedFrame

Point = tuple[float, float]
BoundingBox = tuple[Point, Point, Point, Point]


class BlockOrientation(StrEnum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class OcrError(RuntimeError):
    """A readable OCR configuration or inference failure."""


@dataclass(frozen=True, slots=True)
class OcrTextBlock:
    text: str
    confidence: float
    box: BoundingBox
    orientation: BlockOrientation = BlockOrientation.HORIZONTAL
    fragment_boxes: tuple[BoundingBox, ...] = ()


@dataclass(frozen=True, slots=True)
class OcrResult:
    blocks: tuple[OcrTextBlock, ...]
    text: str
    normalized_text: str
    confidence: float
    captured_at: float
    inference_seconds: float
    reading_direction: ReadingDirection = ReadingDirection.WEBTOON_LTR


class OcrEngine(Protocol):
    def load(self) -> None: ...

    def recognize(self, frame: CapturedFrame) -> OcrResult: ...

    def close(self) -> None: ...
