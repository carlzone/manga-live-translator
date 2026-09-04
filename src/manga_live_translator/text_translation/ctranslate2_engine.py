"""CTranslate2 adapter for external OPUS-MT caption models."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from manga_live_translator.config import SourceLanguage
from manga_live_translator.paths import runtime_path
from manga_live_translator.text_translation.engine import (
    TextTranslationError,
    TextTranslationResult,
)

MODEL_DIRECTORIES = {
    SourceLanguage.JAPANESE: "ja-en",
    SourceLanguage.SIMPLIFIED_CHINESE: "zh-en",
}
REQUIRED_MODEL_FILES = ("model.bin", "config.json", "source.spm", "target.spm")


def resolve_source_language(text: str, requested: SourceLanguage) -> SourceLanguage:
    """Resolve Auto using script detection; Han-only captions intentionally route to Chinese."""
    requested = SourceLanguage(requested)
    if requested is not SourceLanguage.AUTO:
        return requested
    if any("\u3040" <= character <= "\u30ff" for character in text):
        return SourceLanguage.JAPANESE
    if any("\u3400" <= character <= "\u9fff" for character in text):
        return SourceLanguage.SIMPLIFIED_CHINESE
    raise TextTranslationError("Could not detect Japanese or Chinese text in the caption")


class CTranslate2TextEngine:
    """Persistent CPU-only CTranslate2 translators and SentencePiece tokenizers."""

    def __init__(self, model_dir: Path | None = None) -> None:
        self.model_dir = model_dir or runtime_path("models", "translation")
        self._translators: dict[SourceLanguage, Any] = {}
        self._source_tokenizers: dict[SourceLanguage, Any] = {}
        self._target_tokenizers: dict[SourceLanguage, Any] = {}

    def validate_assets(self) -> None:
        for directory in MODEL_DIRECTORIES.values():
            path = self.model_dir / directory
            for filename in REQUIRED_MODEL_FILES:
                asset = path / filename
                if not asset.is_file():
                    raise TextTranslationError(f"Missing text translation asset: {asset}")

    def load(self) -> None:
        if self._translators:
            return
        self.validate_assets()
        try:
            import ctranslate2  # type: ignore[import-untyped]
            import sentencepiece
        except ImportError as exc:
            raise TextTranslationError(
                "Text translation runtime is not installed; run 'uv sync'"
            ) from exc
        try:
            for language, directory in MODEL_DIRECTORIES.items():
                path = self.model_dir / directory
                self._translators[language] = ctranslate2.Translator(
                    str(path), device="cpu", compute_type="int8"
                )
                self._source_tokenizers[language] = sentencepiece.SentencePieceProcessor(
                    model_file=str(path / "source.spm")
                )
                self._target_tokenizers[language] = sentencepiece.SentencePieceProcessor(
                    model_file=str(path / "target.spm")
                )
        except Exception as exc:
            self.close()
            raise TextTranslationError(
                f"Could not load text translation models from {self.model_dir}: {exc}"
            ) from exc

    def translate(
        self,
        text: str,
        source_language: SourceLanguage,
        target_language: str = "en",
    ) -> TextTranslationResult:
        caption = text.strip()
        if not caption:
            raise TextTranslationError("Caption text cannot be empty")
        if target_language != "en":
            raise TextTranslationError("Only English text translation is supported")
        language = resolve_source_language(caption, source_language)
        model_language = (
            SourceLanguage.SIMPLIFIED_CHINESE
            if language is SourceLanguage.TRADITIONAL_CHINESE
            else language
        )
        if not self._translators:
            raise TextTranslationError("Text translation engine is not loaded")
        started = time.perf_counter()
        try:
            tokens = self._source_tokenizers[model_language].encode(caption, out_type=str)
            # Marian tokenizers append EOS to every encoder input. CTranslate2's
            # converted model does not add it automatically (add_source_eos=false).
            tokens.append("</s>")
            batches = self._translators[model_language].translate_batch(
                [tokens], beam_size=4, max_decoding_length=128
            )
            hypotheses = batches[0].hypotheses if batches else []
            if not hypotheses:
                raise ValueError("model returned no translation")
            translated = self._target_tokenizers[model_language].decode(hypotheses[0]).strip()
            if not translated:
                raise ValueError("model returned an empty translation")
        except Exception as exc:
            raise TextTranslationError(f"Text translation inference failed: {exc}") from exc
        return TextTranslationResult(
            translated,
            language,
            target_language,
            time.perf_counter() - started,
        )

    def close(self) -> None:
        self._translators.clear()
        self._source_tokenizers.clear()
        self._target_tokenizers.clear()
