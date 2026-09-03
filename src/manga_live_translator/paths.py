"""Application data and installed runtime paths."""

import sys
from pathlib import Path

from platformdirs import user_data_path

APP_NAME = "MangaLiveTranslator"


def runtime_dir() -> Path:
    """Return the directory containing packaged runtime assets."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def runtime_path(*parts: str) -> Path:
    """Resolve an external asset first, then a PyInstaller-bundled asset."""
    external = runtime_dir().joinpath(*parts)
    if external.exists() or not getattr(sys, "frozen", False):
        return external
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir is not None:
        bundled = Path(bundle_dir).joinpath(*parts)
        if bundled.exists():
            return bundled
    return external


def app_data_dir() -> Path:
    """Return the per-user application data directory."""
    return Path(user_data_path(APP_NAME, appauthor=False, roaming=False))


def settings_path() -> Path:
    """Return the default settings file path."""
    return app_data_dir() / "settings.json"


def logs_dir() -> Path:
    """Return the default log directory."""
    return app_data_dir() / "logs"
