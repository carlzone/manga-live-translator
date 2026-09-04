"""Selected-region reader application window."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from manga_live_translator.config import (
    CaptionRegion,
    ReadingDirection,
    SettingsStore,
    SourceLanguage,
)
from manga_live_translator.diagnostics import RuntimeDiagnostics
from manga_live_translator.screen import (
    CapturedFrame,
    QtScreenProvider,
    RegionCaptureWorker,
    ScreenDescriptor,
    ScrollDisplacement,
    VerticalScrollTracker,
    ViewportSettlingController,
    ViewportSnapshot,
    ViewportState,
    WindowsGdiCaptureProvider,
    fingerprint_frame,
    validate_caption_region,
)
from manga_live_translator.ui.overlay import TranslationOverlay
from manga_live_translator.ui.region_preview import RegionPreviewDialog
from manga_live_translator.ui.region_selector import RegionSelector
from manga_live_translator.workers import RuntimeStatus
from manga_live_translator.workers.scan import ScanJob, ScanWorker, ViewportTranslation


@dataclass(slots=True)
class CleanCaptureRequest:
    generation: int
    manual: bool
    hidden_at: float
    remaining_samples: int = 2


class MainWindow(QMainWindow):
    def __init__(self, settings_store: SettingsStore | None = None) -> None:
        super().__init__()
        self.store = settings_store or SettingsStore()
        self.settings = self.store.load()
        self.screen_provider = QtScreenProvider()
        self.selector: RegionSelector | None = None
        self.preview: RegionPreviewDialog | None = None
        self.worker: ScanWorker | None = None
        self.capture_worker: RegionCaptureWorker | None = None
        self.settling = ViewportSettlingController()
        self.scroll_tracker = VerticalScrollTracker()
        self.latest_frame: CapturedFrame | None = None
        self.generation = 0
        self.clean_capture_request: CleanCaptureRequest | None = None
        self.post_render_rebase_pending = False
        self._submitted_at: dict[int, float] = {}
        self.diagnostics = RuntimeDiagnostics()
        self.last_reading_direction = self.settings.reading_direction
        self.translation_cache: dict[tuple[SourceLanguage, str], tuple[str, SourceLanguage]] = {}
        self.setWindowTitle("MangaLiveTranslator")
        self.resize(580, 500)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        reader_group = QGroupBox("Reader")
        reader_layout = QFormLayout(reader_group)
        self.language = QComboBox()
        for label, language_value in (
            ("Auto", SourceLanguage.AUTO),
            ("Japanese", SourceLanguage.JAPANESE),
            ("Simplified Chinese", SourceLanguage.SIMPLIFIED_CHINESE),
            ("Traditional Chinese", SourceLanguage.TRADITIONAL_CHINESE),
        ):
            self.language.addItem(label, language_value)
        self.language.setCurrentIndex(max(0, self.language.findData(self.settings.source_language)))
        self.reading_direction = QComboBox()
        for label, direction_value in (
            ("Auto layout", ReadingDirection.AUTOMATIC),
            ("Japanese manga", ReadingDirection.MANGA_RTL),
            ("Webtoon/manhwa", ReadingDirection.WEBTOON_LTR),
        ):
            self.reading_direction.addItem(label, direction_value)
        self.reading_direction.setCurrentIndex(
            max(0, self.reading_direction.findData(self.settings.reading_direction))
        )
        self.vertical_ocr = QCheckBox("Vertical CJK text (experimental)")
        self.vertical_ocr.setChecked(self.settings.experimental_vertical_ocr)
        reader_layout.addRow("Source language", self.language)
        reader_layout.addRow("Reading order", self.reading_direction)
        reader_layout.addRow("", self.vertical_ocr)
        layout.addWidget(reader_group)

        region_group = QGroupBox("Capture region")
        region_layout = QGridLayout(region_group)
        self.region_label = QLabel(self._region_text())
        self.region_label.setWordWrap(True)
        region_layout.addWidget(self.region_label, 0, 0, 1, 2)
        self.select_button = QPushButton("Select Region")
        self.preview_button = QPushButton("Preview Region")
        region_layout.addWidget(self.select_button, 1, 0)
        region_layout.addWidget(self.preview_button, 1, 1)
        layout.addWidget(region_group)

        scanning_group = QGroupBox("Scanning")
        scanning_layout = QGridLayout(scanning_group)
        self.start_button = QPushButton("Start")
        self.rescan_button = QPushButton("Rescan")
        self.pause_button = QPushButton("Pause")
        self.clear_button = QPushButton("Clear")
        self.rescan_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        scanning_layout.addWidget(self.start_button, 0, 0)
        scanning_layout.addWidget(self.pause_button, 0, 1)
        scanning_layout.addWidget(self.rescan_button, 1, 0)
        scanning_layout.addWidget(self.clear_button, 1, 1)
        layout.addWidget(scanning_group)

        overlay_group = QGroupBox("Translation overlay")
        overlay_layout = QGridLayout(overlay_group)
        self.font_size = QSpinBox()
        self.font_size.setRange(12, 48)
        self.font_size.setValue(self.settings.font_size)
        self.font_size.setSuffix(" px")
        self.overlay_opacity = QDoubleSpinBox()
        self.overlay_opacity.setRange(0.1, 1.0)
        self.overlay_opacity.setSingleStep(0.05)
        self.overlay_opacity.setValue(self.settings.overlay_opacity)
        self.copy_button = QPushButton("Copy All")
        self.overlay_toggle_button = QPushButton("Show / Hide Overlay")
        self.overlay_toggle_button.setEnabled(False)
        overlay_layout.addWidget(QLabel("Text size"), 0, 0)
        overlay_layout.addWidget(self.font_size, 0, 1)
        overlay_layout.addWidget(QLabel("Box opacity"), 1, 0)
        overlay_layout.addWidget(self.overlay_opacity, 1, 1)
        overlay_layout.addWidget(self.copy_button, 2, 0)
        overlay_layout.addWidget(self.overlay_toggle_button, 2, 1)
        layout.addWidget(overlay_group)

        self.overlay = TranslationOverlay()
        self.diagnostics_button = QPushButton("Diagnostics")
        self.status = QLabel(RuntimeStatus.IDLE.value)
        self.status.setWordWrap(True)
        status_layout = QGridLayout()
        status_layout.addWidget(QLabel("Status:"), 0, 0)
        status_layout.addWidget(self.status, 0, 1)
        status_layout.addWidget(self.diagnostics_button, 0, 2)
        layout.addLayout(status_layout)
        layout.addStretch()
        self.setCentralWidget(root)
        self.select_button.clicked.connect(self._select_region)
        self.preview_button.clicked.connect(self._preview_region)
        self.start_button.clicked.connect(self._start_scan)
        self.rescan_button.clicked.connect(self._request_scan)
        self.pause_button.clicked.connect(self._pause_scan)
        self.clear_button.clicked.connect(self._clear_history)
        self.copy_button.clicked.connect(self.overlay.copy_all)
        self.overlay_toggle_button.clicked.connect(self._toggle_panel)
        self.diagnostics_button.clicked.connect(self._show_diagnostics)
        self.font_size.valueChanged.connect(self._apply_overlay_settings)
        self.overlay_opacity.valueChanged.connect(self._apply_overlay_settings)
        self.language.currentIndexChanged.connect(self._language_changed)
        self.reading_direction.currentIndexChanged.connect(self._reading_direction_changed)
        self._shortcuts: list[QShortcut] = []
        for sequence, callback in (
            ("Ctrl+Alt+S", self._toggle_scan),
            ("Ctrl+Alt+R", self._request_scan),
            ("Ctrl+Alt+C", self.overlay.copy_all),
            ("Ctrl+Alt+X", self._clear_history),
            ("Ctrl+Alt+H", self._toggle_panel),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        self._apply_overlay_settings(save=False)
        self._language_changed(save=False)

    def _region_text(self) -> str:
        region = self.settings.caption_region
        return (
            "No reader region selected"
            if region is None
            else f"{region.screen_name}: {region.width}×{region.height} at ({region.x}, {region.y})"
        )

    def _apply_overlay_settings(self, _value: object = None, *, save: bool = True) -> None:
        self.overlay.set_appearance(
            font_size=self.font_size.value(), opacity=self.overlay_opacity.value()
        )
        self.settings = replace(
            self.settings,
            font_size=self.font_size.value(),
            overlay_opacity=self.overlay_opacity.value(),
            show_original_text=False,
            click_through=True,
        )
        if save:
            self.store.save(self.settings)

    def _language_changed(self, _value: object = None, *, save: bool = True) -> None:
        language = SourceLanguage(self.language.currentData())
        chinese = language in (
            SourceLanguage.SIMPLIFIED_CHINESE,
            SourceLanguage.TRADITIONAL_CHINESE,
        )
        if chinese:
            with QSignalBlocker(self.reading_direction):
                self.reading_direction.setCurrentIndex(
                    self.reading_direction.findData(ReadingDirection.WEBTOON_LTR)
                )
        runtime_active = self.worker is not None and self.worker.isRunning()
        self.reading_direction.setEnabled(not chinese and not runtime_active)
        if save:
            self._invalidate_visible_results()
        self.settings = replace(
            self.settings,
            source_language=language,
            reading_direction=ReadingDirection(self.reading_direction.currentData()),
        )
        if save:
            self.store.save(self.settings)

    def _reading_direction_changed(self, _value: object = None) -> None:
        self._invalidate_visible_results()
        self.settings = replace(
            self.settings,
            reading_direction=ReadingDirection(self.reading_direction.currentData()),
        )
        self.store.save(self.settings)

    def _invalidate_visible_results(self) -> None:
        self.generation += 1
        self._submitted_at.clear()
        self.overlay.clear_results()
        self.scroll_tracker.reset()
        self._reset_capture_handshake()
        if self.worker is not None:
            self.worker.clear_pending()
            self.worker.clear_reconciliation()

    def _toggle_scan(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self._pause_scan()
        else:
            self._start_scan()

    def _toggle_panel(self) -> None:
        if self.overlay.isVisible():
            self.overlay.hide()
        elif self.worker is not None and self.worker.isRunning():
            self.overlay.show()

    def _diagnostics_text(self) -> str:
        return self.diagnostics.report(
            region=self.settings.caption_region,
            reading_direction=self.last_reading_direction,
            state=self.status.text(),
            overlay_geometry=(
                self.overlay.x(),
                self.overlay.y(),
                self.overlay.width(),
                self.overlay.height(),
            ),
            overlay_scale=(self.overlay.scale_x, self.overlay.scale_y),
            rendered_boxes=self.overlay.rendered_box_count,
            collision_adjustments=self.overlay.collision_adjustments,
            capture_exclusion_mode=self.overlay.capture_exclusion.mode,
            capture_exclusion_verified=self.overlay.capture_exclusion.verified,
            capture_exclusion_error=self.overlay.capture_exclusion.error_code,
        )

    def _show_diagnostics(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Diagnostics")
        dialog.resize(680, 440)
        layout = QVBoxLayout(dialog)
        report = QPlainTextEdit(self._diagnostics_text())
        report.setReadOnly(True)
        layout.addWidget(report)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy_button = buttons.addButton("Copy diagnostics", QDialogButtonBox.ButtonRole.ActionRole)
        copy_button.clicked.connect(report.selectAll)
        copy_button.clicked.connect(report.copy)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _select_region(self) -> None:
        if self.worker is not None or self.capture_worker is not None:
            self._pause_scan()
        self.overlay.hide()
        self.selector = RegionSelector(self.screen_provider.screens())
        self.selector.region_selected.connect(self._save_region)
        self.selector.show()

    def _save_region(self, region: object) -> None:
        self.settings = replace(self.settings, caption_region=region)  # type: ignore[arg-type]
        self.store.save(self.settings)
        self.region_label.setText(self._region_text())
        self.overlay.clear_results()
        self.scroll_tracker.reset()
        self._reset_capture_handshake()

    def _validated_region(self) -> tuple[CaptionRegion, ScreenDescriptor] | None:
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
        self.preview = RegionPreviewDialog(region, screen, self)
        self.preview.show()

    def _start_scan(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        validated = self._validated_region()
        if validated is None:
            return
        region, screen = validated
        language = SourceLanguage(self.language.currentData())
        reading_direction = ReadingDirection(self.reading_direction.currentData())
        self.last_reading_direction = reading_direction
        self.settings = replace(
            self.settings,
            source_language=language,
            reading_direction=reading_direction,
            experimental_vertical_ocr=self.vertical_ocr.isChecked(),
        )
        self.store.save(self.settings)
        self.settling.reset()
        self.scroll_tracker.reset()
        self._reset_capture_handshake()
        self.latest_frame = None
        worker = ScanWorker(
            region,
            screen,
            language,
            self.translation_cache,
            reading_direction,
            self.settings.experimental_vertical_ocr,
        )
        capture = RegionCaptureWorker(
            WindowsGdiCaptureProvider(), region, screen, frames_per_second=5.0
        )
        worker.status_changed.connect(self._set_status)
        worker.viewport_ready.connect(self._set_results)
        worker.scan_started.connect(self._scan_started)
        worker.scan_completed.connect(self._scan_completed)
        worker.scan_failed.connect(self._scan_failed)
        worker.runtime_failed.connect(self._runtime_failed)
        worker.finished.connect(self._runtime_stopped)
        capture.frame_sampled.connect(self._observe_frame)
        capture.error.connect(self._capture_failed)
        self.worker = worker
        self.capture_worker = capture
        self.overlay.align_to_region(region, screen)
        self.overlay.clear_results()
        self.overlay.show()
        self.start_button.setEnabled(False)
        self.rescan_button.setEnabled(True)
        self.pause_button.setEnabled(True)
        self.overlay_toggle_button.setEnabled(True)
        self.clear_button.setEnabled(True)
        self.language.setEnabled(False)
        self.reading_direction.setEnabled(False)
        self.vertical_ocr.setEnabled(False)
        worker.start()
        capture.start_capture()
        self.diagnostics.start_stop_cycles += 1

    def _observe_frame(self, frame: CapturedFrame) -> None:
        if self.sender() is not self.capture_worker:
            return
        self.latest_frame = frame
        if self.clean_capture_request is not None:
            self._consume_clean_capture(frame)
            return
        if self.post_render_rebase_pending:
            self.post_render_rebase_pending = False
            self.settling.adopt_stable(frame)
            self.scroll_tracker.reset()
            self.scroll_tracker.observe(fingerprint_frame(frame), physical_height=frame.height)
            self.diagnostics.record_post_render_rebase()
            return
        displacement = self.scroll_tracker.observe(
            fingerprint_frame(frame), physical_height=frame.height
        )
        snapshot = self.settling.observe(frame)
        if snapshot is not None:
            self._submit_snapshot(snapshot)
        elif self.settling.state is ViewportState.MOVING:
            self._apply_scroll_displacement(displacement)
            self.status.setText(RuntimeStatus.MOVING.value)
        elif self.settling.state is ViewportState.SETTLING:
            self.status.setText(RuntimeStatus.SETTLING.value)

    def _consume_clean_capture(self, frame: CapturedFrame) -> None:
        request = self.clean_capture_request
        if request is None:
            return
        if frame.captured_at < request.hidden_at:
            return
        self.diagnostics.record_clean_frame_drain()
        request.remaining_samples = max(0, request.remaining_samples - 1)
        if (
            request.remaining_samples > 0
            or frame.captured_at - request.hidden_at + 1e-9 < 0.4
        ):
            return
        self.clean_capture_request = None
        if self.worker is None or request.generation != self.generation:
            return
        snapshot = self.settling.manual_snapshot(frame)
        self.worker.submit(ScanJob(request.generation, snapshot))

    def _apply_scroll_displacement(self, displacement: ScrollDisplacement) -> None:
        if displacement.trackable:
            logical_dy = displacement.physical_dy * self.overlay.scale_y
            self.overlay.translate_vertical(logical_dy)
            self.diagnostics.record_scroll(
                physical_dy=displacement.physical_dy,
                logical_dy=logical_dy,
                confidence=displacement.confidence,
            )
            return
        if displacement.reason == "initial frame":
            return
        had_boxes = self.overlay.rendered_box_count > 0
        if had_boxes:
            self.overlay.clear_results()
        self.diagnostics.record_scroll(
            physical_dy=0.0,
            logical_dy=0.0,
            confidence=displacement.confidence,
            cleared=had_boxes,
        )

    def _submit_snapshot(self, _snapshot: ViewportSnapshot) -> None:
        self._begin_clean_capture(manual=False)

    def _begin_clean_capture(self, *, manual: bool) -> None:
        if self.worker is None or self.capture_worker is None:
            return
        self.overlay.clear_results()
        self.scroll_tracker.reset()
        self.generation += 1
        self._submitted_at.clear()
        self._submitted_at[self.generation] = time.monotonic()
        self.worker.clear_pending()
        self.clean_capture_request = CleanCaptureRequest(
            self.generation, manual, time.monotonic()
        )
        self.post_render_rebase_pending = False
        self.capture_worker.request_capture()

    def _set_results(self, result: ViewportTranslation) -> None:
        if self.sender() is self.worker and result.generation == self.generation:
            self.overlay.reconcile_results(result)
            self.post_render_rebase_pending = self.overlay.rendered_box_count > 0
            self.last_reading_direction = result.reading_direction
            submitted_at = self._submitted_at.pop(result.generation, time.monotonic())
            self.diagnostics.record_viewport(
                ocr_seconds=result.ocr_seconds,
                translation_seconds=result.translation_seconds,
                completion_seconds=time.monotonic() - submitted_at,
                translated_blocks=sum(block.translation is not None for block in result.blocks),
                failed_blocks=sum(block.error is not None for block in result.blocks),
            )
            self.settling.mark_stable()

    def _set_status(self, status: RuntimeStatus, detail: str | None) -> None:
        if self.sender() is self.worker and (self.worker.active_generation in (0, self.generation)):
            self.status.setText(status.value + (f" — {detail}" if detail else ""))

    def _request_scan(self) -> None:
        self._begin_clean_capture(manual=True)

    def _scan_started(self) -> None:
        if self.sender() is self.worker:
            self.status.setText(RuntimeStatus.READING.value)

    def _scan_completed(self) -> None:
        if self.sender() is self.worker and self.settling.state is ViewportState.PROCESSING:
            self.settling.mark_stable()

    def _scan_failed(self, detail: str) -> None:
        if self.sender() is self.worker and self.worker.active_generation == self.generation:
            QMessageBox.warning(self, "Scan failed", detail)

    def _capture_failed(self, detail: str) -> None:
        if self.sender() is self.capture_worker:
            self._reset_capture_handshake()
            self.overlay.hide()
            self.status.setText(f"{RuntimeStatus.ERROR.value} — {detail}")
            QMessageBox.warning(self, "Capture failed", detail)

    def _runtime_failed(self, detail: str) -> None:
        if self.sender() is self.worker:
            self._reset_capture_handshake()
            self.overlay.hide()
            QMessageBox.critical(self, "Scan runtime failed", detail)

    def _clear_history(self) -> None:
        self.generation += 1
        self._submitted_at.clear()
        self.overlay.clear_results()
        self.scroll_tracker.reset()
        self._reset_capture_handshake()
        if self.worker is not None:
            self.worker.clear_pending()
            self.worker.clear_reconciliation()

    def _pause_scan(self) -> None:
        self.generation += 1
        self._submitted_at.clear()
        if self.capture_worker is not None:
            self.capture_worker.close()
            self.capture_worker.deleteLater()
            self.capture_worker = None
        if self.worker is not None:
            self.worker.stop()
        self._runtime_stopped()
        self.settling.reset()
        self.scroll_tracker.reset()
        self._reset_capture_handshake()
        self.latest_frame = None
        self.overlay.hide()
        self.status.setText(RuntimeStatus.PAUSED.value)

    def _runtime_stopped(self) -> None:
        self.start_button.setEnabled(True)
        self.rescan_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.overlay_toggle_button.setEnabled(False)
        self.clear_button.setEnabled(True)
        self.language.setEnabled(True)
        self.vertical_ocr.setEnabled(True)
        self._language_changed(save=False)
        if self.worker is not None and not self.worker.isRunning():
            self.worker.deleteLater()
            self.worker = None

    def _reset_capture_handshake(self) -> None:
        self.clean_capture_request = None
        self.post_render_rebase_pending = False

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._pause_scan()
        self.overlay.close()
        event.accept()
