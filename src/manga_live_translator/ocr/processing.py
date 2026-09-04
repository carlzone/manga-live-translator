"""Manga OCR filtering, grouping, ordering, and text normalization."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from manga_live_translator.config import ReadingDirection, SourceLanguage
from manga_live_translator.ocr.engine import BlockOrientation, BoundingBox, OcrTextBlock

_WHITESPACE = re.compile(r"\s+")
_CJK_WHITESPACE = re.compile(
    r"(?<=[\u3040-\u30ff\u3400-\u9fff])\s+(?=[\u3040-\u30ff\u3400-\u9fff])"
)


@dataclass(frozen=True, slots=True)
class LayoutResult:
    blocks: tuple[OcrTextBlock, ...]
    reading_direction: ReadingDirection


def normalize_ocr_text(text: str) -> str:
    normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()
    return _CJK_WHITESPACE.sub("", normalized)


def comparison_key(text: str) -> str:
    normalized = normalize_ocr_text(text).casefold()
    return "".join(
        char
        for char in normalized
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def _bounds(block: OcrTextBlock) -> tuple[float, float, float, float]:
    xs = [point[0] for point in block.box]
    ys = [point[1] for point in block.box]
    return min(xs), min(ys), max(xs), max(ys)


def classify_orientation(block: OcrTextBlock, *, vertical_ratio: float = 1.4) -> BlockOrientation:
    left, top, right, bottom = _bounds(block)
    if bottom - top >= max(1.0, right - left) * vertical_ratio:
        return BlockOrientation.VERTICAL
    return BlockOrientation.HORIZONTAL


def _script(text: str) -> str:
    cjk = any("\u3040" <= c <= "\u30ff" or "\u3400" <= c <= "\u9fff" for c in text)
    latin = any(c.isascii() and c.isalpha() for c in text)
    return "cjk" if cjk and not latin else "latin" if latin and not cjk else "mixed"


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _can_group(first: OcrTextBlock, second: OcrTextBlock) -> bool:
    if first.orientation is not second.orientation or _script(first.text) != _script(second.text):
        return False
    ax0, ay0, ax1, ay1 = _bounds(first)
    bx0, by0, bx1, by1 = _bounds(second)
    aw, ah, bw, bh = ax1 - ax0, ay1 - ay0, bx1 - bx0, by1 - by0
    if first.orientation is BlockOrientation.HORIZONTAL:
        gap = max(0.0, max(ay0, by0) - min(ay1, by1))
        return gap <= max(ah, bh) * 0.8 and _overlap(ax0, ax1, bx0, bx1) >= min(aw, bw) * 0.45
    gap = max(0.0, max(ax0, bx0) - min(ax1, bx1))
    return gap <= max(aw, bw) * 0.8 and _overlap(ay0, ay1, by0, by1) >= min(ah, bh) * 0.45


def _enclosing_box(blocks: list[OcrTextBlock]) -> BoundingBox:
    bounds = [_bounds(block) for block in blocks]
    left, top = min(b[0] for b in bounds), min(b[1] for b in bounds)
    right, bottom = max(b[2] for b in bounds), max(b[3] for b in bounds)
    return ((left, top), (right, top), (right, bottom), (left, bottom))


def group_fragments(blocks: tuple[OcrTextBlock, ...]) -> tuple[OcrTextBlock, ...]:
    groups: list[list[OcrTextBlock]] = []
    for block in sorted(blocks, key=lambda item: (_bounds(item)[1], _bounds(item)[0])):
        target = next(
            (group for group in groups if any(_can_group(item, block) for item in group)), None
        )
        if target is None:
            groups.append([block])
        else:
            target.append(block)
    merged: list[OcrTextBlock] = []
    for group in groups:
        if len(group) == 1:
            merged.append(group[0])
            continue
        orientation = group[0].orientation
        ordered = sorted(
            group,
            key=(
                (lambda item: (_bounds(item)[1], _bounds(item)[0]))
                if orientation is BlockOrientation.HORIZONTAL
                else (lambda item: (-_bounds(item)[0], _bounds(item)[1]))
            ),
        )
        separator = "" if all(_script(item.text) == "cjk" for item in ordered) else " "
        fragments = tuple(box for item in ordered for box in (item.fragment_boxes or (item.box,)))
        merged.append(
            OcrTextBlock(
                separator.join(item.text for item in ordered),
                min(item.confidence for item in ordered),
                _enclosing_box(ordered),
                orientation,
                fragments,
            )
        )
    return tuple(merged)


def _webtoon_order(blocks: tuple[OcrTextBlock, ...]) -> tuple[OcrTextBlock, ...]:
    heights = sorted(_bounds(block)[3] - _bounds(block)[1] for block in blocks)
    row = max(1.0, heights[len(heights) // 2] * 0.5) if heights else 1.0
    return tuple(
        sorted(blocks, key=lambda block: (round(_bounds(block)[1] / row), _bounds(block)[0]))
    )


def _manga_order(blocks: tuple[OcrTextBlock, ...]) -> tuple[OcrTextBlock, ...]:
    columns: list[list[OcrTextBlock]] = []
    for block in sorted(blocks, key=lambda item: -((_bounds(item)[0] + _bounds(item)[2]) / 2)):
        x0, _, x1, _ = _bounds(block)
        column = next(
            (
                group
                for group in columns
                if any(
                    _overlap(x0, x1, _bounds(item)[0], _bounds(item)[2])
                    >= min(x1 - x0, _bounds(item)[2] - _bounds(item)[0]) * 0.35
                    for item in group
                )
            ),
            None,
        )
        if column is None:
            columns.append([block])
        else:
            column.append(block)
    columns.sort(
        key=lambda group: -sum((_bounds(i)[0] + _bounds(i)[2]) / 2 for i in group) / len(group)
    )
    return tuple(
        item for group in columns for item in sorted(group, key=lambda block: _bounds(block)[1])
    )


def choose_reading_direction(
    blocks: tuple[OcrTextBlock, ...], language: SourceLanguage
) -> ReadingDirection:
    if language in (SourceLanguage.SIMPLIFIED_CHINESE, SourceLanguage.TRADITIONAL_CHINESE):
        return ReadingDirection.WEBTOON_LTR
    japanese = language is SourceLanguage.JAPANESE or _contains_japanese_kana(blocks)
    centers = {round((_bounds(block)[0] + _bounds(block)[2]) / 2, 1) for block in blocks}
    return (
        ReadingDirection.MANGA_RTL
        if japanese and len(centers) >= 2
        else ReadingDirection.WEBTOON_LTR
    )


def _contains_japanese_kana(blocks: tuple[OcrTextBlock, ...]) -> bool:
    return any(
        any("\u3040" <= char <= "\u30ff" for char in block.text) for block in blocks
    )


def resolve_reading_direction(
    requested: ReadingDirection,
    blocks: tuple[OcrTextBlock, ...],
    language: SourceLanguage,
) -> ReadingDirection:
    """Enforce that right-to-left ordering is used only for Japanese text."""
    if language in (SourceLanguage.SIMPLIFIED_CHINESE, SourceLanguage.TRADITIONAL_CHINESE):
        return ReadingDirection.WEBTOON_LTR
    if requested is ReadingDirection.AUTOMATIC:
        return choose_reading_direction(blocks, language)
    if requested is ReadingDirection.MANGA_RTL and language is SourceLanguage.AUTO:
        return (
            ReadingDirection.MANGA_RTL
            if _contains_japanese_kana(blocks)
            else ReadingDirection.WEBTOON_LTR
        )
    return requested


def process_manga_layout(
    blocks: tuple[OcrTextBlock, ...],
    *,
    reading_direction: ReadingDirection = ReadingDirection.WEBTOON_LTR,
    language: SourceLanguage = SourceLanguage.AUTO,
    minimum_confidence: float = 0.75,
    allow_vertical: bool = False,
) -> LayoutResult:
    accepted: list[OcrTextBlock] = []
    for block in blocks:
        text = normalize_ocr_text(block.text)
        orientation = classify_orientation(block)
        if (
            text
            and block.confidence >= minimum_confidence
            and (allow_vertical or orientation is BlockOrientation.HORIZONTAL)
        ):
            accepted.append(
                OcrTextBlock(text, block.confidence, block.box, orientation, block.fragment_boxes)
            )
    grouped = group_fragments(tuple(accepted))
    selected = resolve_reading_direction(reading_direction, grouped, language)
    ordered = (
        _manga_order(grouped) if selected is ReadingDirection.MANGA_RTL else _webtoon_order(grouped)
    )
    return LayoutResult(ordered, selected)


def order_blocks(blocks: tuple[OcrTextBlock, ...]) -> tuple[OcrTextBlock, ...]:
    return _webtoon_order(blocks)


def select_horizontal_manga_blocks(
    blocks: tuple[OcrTextBlock, ...], *, minimum_confidence: float = 0.75
) -> tuple[OcrTextBlock, ...]:
    return process_manga_layout(blocks, minimum_confidence=minimum_confidence).blocks
