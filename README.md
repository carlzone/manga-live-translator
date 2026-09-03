# MangaLiveTranslator

MangaLiveTranslator is an offline-first Windows desktop application that captures a selected
reader region, recognizes Japanese or Chinese text, and translates each detected block to
English. Phase 0 provides one-shot scanning and a minimal multi-block result panel.

## Development

Requires Python 3.12 and `uv`.

```powershell
uv sync
uv run python tools/model_preflight.py
uv run manga-live-translator
uv run pytest
uv run ruff check .
uv run mypy
```

Models are external and are never downloaded by the application. See
[`docs/MODEL_PREPARATION.md`](docs/MODEL_PREPARATION.md). Automatic scroll detection and manga
reading-order modes are planned after Phase 0.

## Privacy

Screen pixels, recognized text, and translations remain local. The application performs no
network requests. The explicit model preparation script is the only download path.
