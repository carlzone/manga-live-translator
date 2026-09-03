"""Domain types and interface for offline caption text translation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from manga_live_translator.config import SourceLanguage


class TextTranslationError(RuntimeError):
    """A readable text-translation configuration or inference failure."""


@dataclass(frozen=True, slots=True)
class TextTranslationResult:
    text: str
    source_language: SourceLanguage
    target_language: str
    inference_seconds: float


class TextTranslationEngine(Protocol):
    def validate_assets(self) -> None: ...

    def load(self) -> None: ...

    def translate(
        self,
        text: str,
        source_language: SourceLanguage,
        target_language: str = "en",
    ) -> TextTranslationResult: ...

    def close(self) -> None: ...
