"""Manga-only Phase 0 application window."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from manga_live_translator.config import SettingsStore, SourceLanguage
from manga_live_translator.screen import QtScreenProvider, validate_caption_region
from manga_live_translator.ui.panel import TranslationPanel
from manga_live_translator.ui.region_preview import RegionPreviewDialog
from manga_live_translator.ui.region_selector import RegionSelector
from manga_live_translator.workers import RuntimeStatus
from manga_live_translator.workers.scan import ScanWorker, TranslatedBlock


class MainWindow(QMainWindow):
    def __init__(self, settings_store: SettingsStore | None = None) -> None:
        super().__init__()
        self.store = settings_store or SettingsStore()
        self.settings = self.store.load()
        self.screen_provider = QtScreenProvider()
        self.selector: RegionSelector | None = None
        self.preview: RegionPreviewDialog | None = None
        self.worker: ScanWorker | None = None
        self.setWindowTitle("MangaLiveTranslator")
        self.resize(620, 720)

        root = QWidget()
        layout = QVBoxLayout(root)
        controls = QHBoxLayout()
        self.language = QComboBox()
        for label, value in (
            ("Auto", SourceLanguage.AUTO),
            ("Japanese", SourceLanguage.JAPANESE),
            ("Chinese", SourceLanguage.CHINESE),
        ):
            self.language.addItem(label, value)
        self.language.setCurrentIndex(max(0, self.language.findData(self.settings.source_language)))
        self.select_button = QPushButton("Select Region")
        self.preview_button = QPushButton("Preview Region")
        self.scan_button = QPushButton("Scan Once")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        for widget in (
            self.language,
            self.select_button,
            self.preview_button,
            self.scan_button,
            self.stop_button,
        ):
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.region_label = QLabel(self._region_text())
        self.region_label.setWordWrap(True)
        layout.addWidget(self.region_label)
        self.panel = TranslationPanel()
        layout.addWidget(self.panel, 1)
        self.status = QLabel(RuntimeStatus.IDLE.value)
        layout.addWidget(self.status)
        self.setCentralWidget(root)

        self.select_button.clicked.connect(self._select_region)
        self.preview_button.clicked.connect(self._preview_region)
        self.scan_button.clicked.connect(self._start_scan)
        self.stop_button.clicked.connect(self._stop_scan)

    def _region_text(self) -> str:
        region = self.settings.caption_region
        return (
            "No reader region selected"
            if region is None
            else f"{region.screen_name}: {region.width}×{region.height} at ({region.x}, {region.y})"
        )

    def _select_region(self) -> None:
        self.selector = RegionSelector(self.screen_provider.screens())
        self.selector.region_selected.connect(self._save_region)
        self.selector.show()

    def _save_region(self, region: object) -> None:
        self.settings = replace(self.settings, caption_region=region)  # type: ignore[arg-type]
        self.store.save(self.settings)
        self.region_label.setText(self._region_text())

    def _validated_region(self) -> tuple[object, object] | None:
        screen, error = validate_caption_region(
            self.settings.caption_region, self.screen_provider.screens()
        )
        if error or screen is None or self.settings.caption_region is None:
            QMessageBox.warning(self, "Reader region", error or "Select a reader region")
            return None
        return self.settings.caption_region, screen

    def _preview_region(self) -> None:
        validated = self._validated_region()
        if validated is None:
            return
        region, screen = validated
        self.preview = RegionPreviewDialog(region, screen, self)  # type: ignore[arg-type]
        self.preview.show()

    def _start_scan(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        validated = self._validated_region()
        if validated is None:
            return
        region, screen = validated
        language = SourceLanguage(self.language.currentData())
        self.settings = replace(self.settings, source_language=language)
        self.store.save(self.settings)
        self.panel.clear_results()
        worker = ScanWorker(region, screen, language)  # type: ignore[arg-type]
        worker.status_changed.connect(self._set_status)
        worker.block_translated.connect(self._add_result)
        worker.error.connect(lambda detail: QMessageBox.critical(self, "Scan failed", detail))
        worker.finished.connect(self._scan_stopped)
        self.worker = worker
        self.scan_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        worker.start()

    def _add_result(self, result: TranslatedBlock) -> None:
        if self.sender() is self.worker:
            self.panel.add_result(result, show_source=self.settings.show_original_text)

    def _set_status(self, status: RuntimeStatus, detail: str | None) -> None:
        if self.sender() is self.worker:
            self.status.setText(status.value + (f" — {detail}" if detail else ""))

    def _stop_scan(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        self._scan_stopped()

    def _scan_stopped(self) -> None:
        self.scan_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if self.worker is not None and not self.worker.isRunning():
            self.worker.deleteLater()
            self.worker = None

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._stop_scan()
        event.accept()
