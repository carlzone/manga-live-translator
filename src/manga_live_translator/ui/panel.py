"""Minimal multi-block translation panel."""

from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from manga_live_translator.workers.scan import TranslatedBlock


class TranslationPanel(QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.content = QWidget()
        self.results_layout = QVBoxLayout(self.content)
        self.results_layout.addStretch()
        self.setWidget(self.content)
        self.blocks: list[TranslatedBlock] = []

    def clear_results(self) -> None:
        self.blocks.clear()
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_result(self, result: TranslatedBlock, *, show_source: bool = True) -> None:
        self.blocks.append(result)
        box = result.source.box
        left = round(min(point[0] for point in box))
        top = round(min(point[1] for point in box))
        source = f"{result.source.text}\n" if show_source else ""
        label = QLabel(
            f"{source}{result.translation}\n"
            f"Confidence {result.source.confidence:.0%} · ({left}, {top})"
        )
        label.setWordWrap(True)
        label.setStyleSheet("QLabel { padding: 10px; border-bottom: 1px solid #777; }")
        self.results_layout.insertWidget(self.results_layout.count() - 1, label)
