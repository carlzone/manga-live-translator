"""Subtitle-oriented OCR ordering and text normalization."""

from __future__ import annotations

import re
import unicodedata

from manga_live_translator.ocr.engine import OcrTextBlock

_WHITESPACE = re.compile(r"\s+")
_CJK_WHITESPACE = re.compile(
    r"(?<=[\u3040-\u30ff\u3400-\u9fff])\s+(?=[\u3040-\u30ff\u3400-\u9fff])"
)


def normalize_ocr_text(text: str) -> str:
    """Normalize compatibility characters and whitespace without script conversion."""
    normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()
    return _CJK_WHITESPACE.sub("", normalized)


def comparison_key(text: str) -> str:
    """Return a key that ignores whitespace and punctuation-only OCR jitter."""
    normalized = normalize_ocr_text(text).casefold()
    return "".join(
        character
        for character in normalized
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    )


def order_blocks(blocks: tuple[OcrTextBlock, ...]) -> tuple[OcrTextBlock, ...]:
    return tuple(
        sorted(
            blocks,
            key=lambda block: (
                sum(point[1] for point in block.box) / 4,
                sum(point[0] for point in block.box) / 4,
            ),
        )
    )


def select_subtitle_blocks(
    blocks: tuple[OcrTextBlock, ...], frame_width: int
) -> tuple[OcrTextBlock, ...]:
    """Prefer the lowest centered line/group when unrelated text is also visible."""
    if len(blocks) <= 1:
        return blocks
    centered = [
        block
        for block in blocks
        if abs(sum(point[0] for point in block.box) / 4 - frame_width / 2) <= frame_width * 0.4
    ]
    candidates = centered or list(blocks)
    lowest = max(sum(point[1] for point in block.box) / 4 for block in candidates)
    heights = [
        max(point[1] for point in block.box) - min(point[1] for point in block.box)
        for block in candidates
    ]
    tolerance = max(12.0, max(heights, default=0.0) * 1.75)
    selected = tuple(
        block
        for block in candidates
        if lowest - sum(point[1] for point in block.box) / 4 <= tolerance
    )
    return order_blocks(selected)
