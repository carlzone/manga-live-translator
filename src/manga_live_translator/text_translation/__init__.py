"""Offline text translation for stable OCR captions."""

from manga_live_translator.text_translation.ctranslate2_engine import (
    CTranslate2TextEngine,
    resolve_source_language,
)
from manga_live_translator.text_translation.engine import (
    TextTranslationEngine,
    TextTranslationError,
    TextTranslationResult,
)

__all__ = [
    "CTranslate2TextEngine",
    "TextTranslationEngine",
    "TextTranslationError",
    "TextTranslationResult",
    "resolve_source_language",
]
