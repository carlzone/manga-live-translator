"""Bounded, reconciliation-aware multi-block translation panel."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from manga_live_translator.workers.scan import TranslatedBlock, ViewportTranslation


class TranslationPanel(QScrollArea):
    def __init__(self, *, maximum_history: int = 100) -> None:
        super().__init__()
        if maximum_history <= 0:
            raise ValueError("maximum_history must be positive")
        self.maximum_history = maximum_history
        self.setWidgetResizable(True)
        self.content = QWidget()
        self.results_layout = QVBoxLayout(self.content)
        self.results_layout.addStretch()
        self.setWidget(self.content)
        self.blocks: list[TranslatedBlock] = []
        self._labels: dict[str, QLabel] = {}
        self._show_source = True
        self.setAccessibleName("Translation history")

    def set_appearance(self, *, font_size: int, opacity: float) -> None:
        self.setStyleSheet(f"QScrollArea {{ font-size: {font_size}px; }}")
        self.setWindowOpacity(opacity)

    def set_show_source(self, show_source: bool) -> None:
        self._show_source = show_source
        for block in self.blocks:
            stable_id = block.stable_id or ""
            if stable_id in self._labels:
                self._labels[stable_id].setText(self._result_text(block, show_source=show_source))

    def copy_all(self) -> str:
        text = "\n\n".join(
            block.translation or f"Translation failed: {block.error or 'Unknown error'}"
            for block in self.blocks
        )
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        return text

    def clear_results(self) -> None:
        self.blocks.clear()
        self._labels.clear()
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_results(self, viewport: ViewportTranslation, *, show_source: bool = True) -> None:
        """Retain Phase 1 replacement behavior for callers that explicitly request it."""
        self.clear_results()
        self.reconcile_results(viewport, show_source=show_source)

    def reconcile_results(self, viewport: ViewportTranslation, *, show_source: bool = True) -> None:
        self._show_source = show_source
        for result in viewport.blocks:
            stable_id = result.stable_id or f"legacy-{id(result)}"
            existing = next(
                (index for index, block in enumerate(self.blocks) if block.stable_id == stable_id),
                None,
            )
            if existing is not None:
                self.blocks[existing] = result
                self._labels[stable_id].setText(self._result_text(result, show_source=show_source))
                continue
            self.blocks.append(result)
            self._labels[stable_id] = self._add_result_widget(result, show_source=show_source)
        while len(self.blocks) > self.maximum_history:
            removed = self.blocks.pop(0)
            stable_id = removed.stable_id or next(iter(self._labels))
            label = self._labels.pop(stable_id)
            self.results_layout.removeWidget(label)
            label.deleteLater()

    def _result_text(self, result: TranslatedBlock, *, show_source: bool) -> str:
        box = result.source.box
        left = round(min(point[0] for point in box))
        top = round(min(point[1] for point in box))
        source = f"{result.source.text}\n" if show_source else ""
        translated = result.translation or f"Translation failed: {result.error or 'Unknown error'}"
        return f"{source}{translated}\nConfidence {result.source.confidence:.0%} · ({left}, {top})"

    def _add_result_widget(self, result: TranslatedBlock, *, show_source: bool) -> QLabel:
        label = QLabel(self._result_text(result, show_source=show_source))
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet("QLabel { padding: 10px; border-bottom: 1px solid #777; }")
        self.results_layout.insertWidget(self.results_layout.count() - 1, label)
        return label
