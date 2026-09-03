from pathlib import Path

from manga_live_translator import __version__
from manga_live_translator.config import AppSettings, SettingsStore
from manga_live_translator.paths import APP_NAME

ROOT = Path(__file__).resolve().parents[1]


def test_identity_and_independence(tmp_path: Path) -> None:
    assert __version__ == "0.1.0"
    assert APP_NAME == "MangaLiveTranslator"
    assert SettingsStore(tmp_path / "settings.json").load() == AppSettings()
    forbidden = ("video_live_translator", "pyaudiowpatch", "whisper", "silero")
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8-sig").casefold()
        assert not any(term in text for term in forbidden), path


def test_model_binaries_are_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.onnx" in ignored and "*.bin" in ignored and "*.spm" in ignored
