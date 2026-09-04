import sys
import time
import types
from pathlib import Path

import pytest

from manga_live_translator.config import SourceLanguage
from manga_live_translator.text_translation import (
    CTranslate2TextEngine,
    TextTranslationError,
    TextTranslationResult,
    resolve_source_language,
)
from manga_live_translator.workers import TextTranslationWorker


def create_assets(path: Path) -> None:
    for language in ("ja-en", "zh-en"):
        directory = path / language
        directory.mkdir(parents=True)
        for name in ("model.bin", "config.json", "source.spm", "target.spm"):
            (directory / name).write_bytes(b"fixture")


def test_source_language_routing() -> None:
    assert (
        resolve_source_language("\u3053\u3093\u306b\u3061\u306f", SourceLanguage.AUTO)
        is SourceLanguage.JAPANESE
    )
    assert (
        resolve_source_language("\u30ab\u30bf\u30ab\u30ca", SourceLanguage.AUTO)
        is SourceLanguage.JAPANESE
    )
    assert (
        resolve_source_language("\u7e41\u9ad4\u4e2d\u6587", SourceLanguage.AUTO)
        is SourceLanguage.SIMPLIFIED_CHINESE
    )
    assert (
        resolve_source_language("\u65e5\u672c\u8a9e", SourceLanguage.AUTO)
        is SourceLanguage.SIMPLIFIED_CHINESE
    )
    assert (
        resolve_source_language("\u65e5\u672c\u8a9e", SourceLanguage.JAPANESE)
        is SourceLanguage.JAPANESE
    )
    with pytest.raises(TextTranslationError, match="detect"):
        resolve_source_language("... 123", SourceLanguage.AUTO)


def test_engine_validates_assets(tmp_path: Path) -> None:
    with pytest.raises(TextTranslationError, match="ja-en.*model.bin"):
        CTranslate2TextEngine(tmp_path).validate_assets()


def test_engine_loads_translates_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_assets(tmp_path)
    translators: list[object] = []

    class BatchResult:
        hypotheses = [["translated", "caption"]]

    class Translator:
        def __init__(self, path: str, **options: object) -> None:
            translators.append((path, options))

        def translate_batch(self, tokens: list[list[str]], **options: object) -> list[BatchResult]:
            assert tokens == [["source", "caption", "</s>"]]
            assert options["beam_size"] == 4
            return [BatchResult()]

    class SentencePieceProcessor:
        def __init__(self, *, model_file: str) -> None:
            self.target = model_file.endswith("target.spm")

        def encode(self, text: str, *, out_type: type[str]) -> list[str]:
            assert text == "å­—å¹•" and out_type is str
            return ["source", "caption"]

        def decode(self, tokens: list[str]) -> str:
            assert self.target and tokens == ["translated", "caption"]
            return "English caption"

    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(Translator=Translator))
    monkeypatch.setitem(
        sys.modules,
        "sentencepiece",
        types.SimpleNamespace(SentencePieceProcessor=SentencePieceProcessor),
    )
    engine = CTranslate2TextEngine(tmp_path)
    engine.load()
    result = engine.translate("å­—å¹•", SourceLanguage.TRADITIONAL_CHINESE)
    assert result.text == "English caption"
    assert result.source_language is SourceLanguage.TRADITIONAL_CHINESE
    assert len(translators) == 2
    engine.close()
    engine.close()
    with pytest.raises(TextTranslationError, match="not loaded"):
        engine.translate("å­—å¹•", SourceLanguage.SIMPLIFIED_CHINESE)


class FakeEngine:
    def __init__(self, delay: float = 0) -> None:
        self.delay = delay
        self.loaded = 0
        self.closed = 0
        self.seen: list[str] = []

    def validate_assets(self) -> None:
        return

    def load(self) -> None:
        self.loaded += 1

    def translate(
        self, text: str, source_language: SourceLanguage, target_language: str = "en"
    ) -> TextTranslationResult:
        time.sleep(self.delay)
        self.seen.append(text)
        return TextTranslationResult(f"EN:{text}", source_language, target_language, self.delay)

    def close(self) -> None:
        self.closed += 1


def test_worker_is_bounded_emits_and_closes(qt_app: object) -> None:
    engine = FakeEngine(0.02)
    worker = TextTranslationWorker(engine, SourceLanguage.JAPANESE)
    results: list[TextTranslationResult] = []
    worker.translation_ready.connect(results.append)
    worker.start_translation()
    worker.submit("first")
    worker.submit("second")
    worker.submit("third")
    deadline = time.monotonic() + 1
    while not results and time.monotonic() < deadline:
        qt_app.processEvents()  # type: ignore[attr-defined]
        time.sleep(0.01)
    worker.close()
    qt_app.processEvents()  # type: ignore[attr-defined]
    assert results
    assert engine.loaded == 1 and engine.closed >= 1
    assert worker.dropped_captions >= 1
    assert engine.seen[-1] == "third"
    assert worker.queue_depth == 0


def test_worker_ignores_empty_input() -> None:
    worker = TextTranslationWorker(FakeEngine(), SourceLanguage.SIMPLIFIED_CHINESE)
    assert not worker.submit("   ")
    assert worker.queue_depth == 0
