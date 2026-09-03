"""Run the Phase 0 CPU-only capture/OCR/translation spike on a real display."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manga_live_translator.config import CaptionRegion, SourceLanguage  # noqa: E402
from manga_live_translator.ocr import RapidOcrEngine  # noqa: E402
from manga_live_translator.screen import QtScreenProvider, WindowsGdiCaptureProvider  # noqa: E402
from manga_live_translator.text_translation import (  # noqa: E402
    CTranslate2TextEngine,
    TextTranslationError,
)
from manga_live_translator.ui.panel import TranslationPanel  # noqa: E402
from manga_live_translator.workers.scan import TranslatedBlock  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", default="MYS240")
    parser.add_argument("--language", choices=("auto", "ja", "zh"), default="auto")
    parser.add_argument("--x", type=int, default=0)
    parser.add_argument("--y", type=int, default=0)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--max-blocks", type=int, default=8)
    parser.add_argument(
        "--fixture", action="store_true", help="Render two Japanese lines on the target display"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "build/phase0-spike.json")
    args = parser.parse_args()

    application = QApplication.instance() or QApplication([])
    screen = next((item for item in QtScreenProvider().screens() if item.name == args.screen), None)
    if screen is None:
        print(f"Display not found: {args.screen}", file=sys.stderr)
        return 2
    fixture: QWidget | None = None
    if args.fixture:
        fixture = QWidget()
        fixture.setWindowTitle("MangaLiveTranslator Phase 0 Fixture")
        fixture.setStyleSheet("background: white; color: black;")
        fixture_layout = QVBoxLayout(fixture)
        for text in ("\u3053\u3093\u306b\u3061\u306f", "\u65b0\u3057\u3044\u4e16\u754c"):
            label = QLabel(text)
            label.setStyleSheet("font-size: 48px; font-weight: bold; padding: 20px;")
            fixture_layout.addWidget(label)
        fixture.setGeometry(screen.x + 100, screen.y + 100, 700, 300)
        fixture.show()
        target_qscreen = next(
            item for item in QGuiApplication.screens() if item.name() == screen.name
        )
        if fixture.windowHandle() is not None:
            fixture.windowHandle().setScreen(target_qscreen)
            fixture.setGeometry(screen.x + 100, screen.y + 100, 700, 300)
        application.processEvents()
        QTest.qWait(750)
        application.processEvents()
        args.x, args.y, args.width, args.height = 100, 100, 700, 300
    width = args.width or screen.width - args.x
    height = args.height or screen.height - args.y
    region = CaptionRegion(
        screen.name,
        screen.width,
        screen.height,
        screen.device_pixel_ratio,
        args.x,
        args.y,
        width,
        height,
    )

    capture = WindowsGdiCaptureProvider()
    ocr = RapidOcrEngine()
    translator = CTranslate2TextEngine()
    panel = TranslationPanel()
    rows: list[dict[str, object]] = []
    try:
        frame = capture.capture(region, screen)
        ocr.load()
        recognized = ocr.recognize(frame)
        translator.load()
        for block in recognized.blocks:
            if args.fixture and not any("\u3040" <= char <= "\u9fff" for char in block.text):
                continue
            try:
                translated = translator.translate(block.text, SourceLanguage(args.language))
            except TextTranslationError:
                if args.language == "auto":
                    continue
                raise
            panel.add_result(
                TranslatedBlock(
                    block, translated.text, translated.source_language, translated.inference_seconds
                )
            )
            rows.append(
                {
                    "source": block.text,
                    "translation": translated.text,
                    "confidence": block.confidence,
                    "box": block.box,
                    "translation_seconds": translated.inference_seconds,
                }
            )
            if len(rows) >= args.max_blocks:
                break
        application.processEvents()
        report = {
            "display": {
                "name": screen.name,
                "width": screen.width,
                "height": screen.height,
                "device_pixel_ratio": screen.device_pixel_ratio,
            },
            "region": {
                "x": region.x,
                "y": region.y,
                "width": region.width,
                "height": region.height,
            },
            "ocr_seconds": recognized.inference_seconds,
            "detected_blocks": len(recognized.blocks),
            "rendered_blocks": len(panel.blocks),
            "results": rows,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if len(rows) >= 2 else 1
    finally:
        panel.close()
        if fixture is not None:
            fixture.close()
        capture.close()
        ocr.close()
        translator.close()


if __name__ == "__main__":
    raise SystemExit(main())
