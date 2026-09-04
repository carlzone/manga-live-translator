"""Qt application entry point."""

import sys
from collections.abc import Sequence
from contextlib import suppress

from PySide6.QtWidgets import QApplication

from manga_live_translator.logging_config import configure_logging
from manga_live_translator.ui.main_window import MainWindow


def enable_windows_dpi_awareness() -> None:
    """Select per-monitor-v2 DPI awareness before Qt creates native windows."""
    if sys.platform != "win32":
        return
    try:  # pragma: no cover - native Windows startup
        import ctypes

        if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        # Older Windows versions lack the per-monitor-v2 call.
        with suppress(AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    enable_windows_dpi_awareness()
    application = QApplication(list(argv) if argv is not None else sys.argv)
    application.setApplicationName("MangaLiveTranslator")
    application.setOrganizationName("MangaLiveTranslator")
    window = MainWindow()
    window.show()
    return application.exec()
