"""Qt application entry point."""

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from manga_live_translator.logging_config import configure_logging
from manga_live_translator.ui.main_window import MainWindow


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    application = QApplication(list(argv) if argv is not None else sys.argv)
    application.setApplicationName("MangaLiveTranslator")
    application.setOrganizationName("MangaLiveTranslator")
    window = MainWindow()
    window.show()
    return application.exec()
