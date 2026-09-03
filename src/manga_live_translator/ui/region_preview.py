"""One-frame preview of a selected reader region."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from manga_live_translator.config import CaptionRegion
from manga_live_translator.screen import ScreenDescriptor, WindowsGdiCaptureProvider


class RegionPreviewDialog(QDialog):
    def __init__(
        self, region: CaptionRegion, screen: ScreenDescriptor, parent: object = None
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self.setWindowTitle("Reader Region Preview")
        self.resize(700, 500)
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
        provider = WindowsGdiCaptureProvider()
        try:
            frame = provider.capture(region, screen)
            image = QImage(
                frame.pixels, frame.width, frame.height, frame.stride, QImage.Format.Format_ARGB32
            ).copy()
            label.setPixmap(
                QPixmap.fromImage(image).scaled(
                    680,
                    460,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        finally:
            provider.close()
