"""Reproducible multilingual subtitle OCR proof harness."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import tracemalloc
from collections import defaultdict
from pathlib import Path
from typing import Any

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF
from PySide6.QtGui import QFontDatabase, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manga_live_translator.config import CaptionRegion  # noqa: E402
from manga_live_translator.ocr import RapidOcrEngine  # noqa: E402
from manga_live_translator.ocr.processing import normalize_ocr_text  # noqa: E402
from manga_live_translator.screen import CapturedFrame  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "ocr"


def load_cjk_fonts() -> tuple[str, ...]:
    candidates = (
        Path("C:/Windows/Fonts/NotoSansJP-VF.ttf"),
        Path("C:/Windows/Fonts/meiryo.ttc"),
        Path("C:/Windows/Fonts/msjh.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
    )
    loaded = tuple(
        str(candidate)
        for candidate in candidates
        if candidate.is_file() and QFontDatabase.addApplicationFont(str(candidate)) >= 0
    )
    if not loaded:
        raise RuntimeError("No supported CJK fixture font is installed")
    return loaded


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, 1):
        current = [row]
        for column, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def render_svg(path: Path) -> tuple[CapturedFrame, QImage]:
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        raise ValueError(f"Invalid SVG fixture: {path}")
    size = renderer.defaultSize()
    image = QImage(size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size.width(), size.height()))
    painter.end()
    pixels = image.bits().tobytes()
    region = CaptionRegion(
        "fixture", size.width(), size.height(), 1.0, 0, 0, size.width(), size.height()
    )
    frame = CapturedFrame(pixels, size.width(), size.height(), image.bytesPerLine(), 0.0, region)
    return frame, image


def percentile95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(0.95 * len(ordered) - 1)))]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_language: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_language[row["language"]].append(row)
    languages: dict[str, Any] = {}
    for language, items in by_language.items():
        expected_chars = sum(len(item["expected"]) for item in items)
        cer = sum(item["distance"] for item in items) / max(1, expected_chars)
        exact = sum(item["exact"] for item in items) / len(items)
        timings = [item["seconds"] for item in items]
        languages[language] = {
            "character_error_rate": cer,
            "exact_caption_rate": exact,
            "median_seconds": statistics.median(timings),
            "p95_seconds": percentile95(timings),
            "accepted": cer <= 0.15 and exact >= 0.70 and percentile95(timings) <= 0.5,
        }
    return languages


def run_tesseract(image: QImage, language: str) -> str | None:
    executable = shutil.which("tesseract")
    if executable is None:
        return None
    language_pack = {"ja": "jpn", "zh-CN": "chi_sim", "zh-TW": "chi_tra"}[language]
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    with tempfile.NamedTemporaryFile(suffix=".png") as temporary:
        temporary.write(bytes(data))
        temporary.flush()
        completed = subprocess.run(
            [executable, temporary.name, "stdout", "-l", language_pack, "--psm", "6"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    return completed.stdout if completed.returncode == 0 else None


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qt_app = QGuiApplication.instance() or QGuiApplication([])
    fixture_fonts = load_cjk_fonts()
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "ocr-benchmark.json")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models" / "ocr")
    args = parser.parse_args()
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    engine = RapidOcrEngine(args.model_dir)
    rows: list[dict[str, Any]] = []
    tesseract_rows: list[dict[str, Any]] = []
    engine.load()
    try:
        for fixture in manifest["fixtures"]:
            frame, image = render_svg(FIXTURES / fixture["file"])
            result = engine.recognize(frame)
            expected = normalize_ocr_text(fixture["expected"])
            actual = normalize_ocr_text(result.text)
            rows.append(
                {
                    **fixture,
                    "actual": actual,
                    "distance": edit_distance(expected, actual),
                    "exact": expected == actual,
                    "seconds": result.inference_seconds,
                }
            )
            alternative = run_tesseract(image, fixture["language"])
            if alternative is not None:
                candidate = normalize_ocr_text(alternative)
                tesseract_rows.append(
                    {
                        **fixture,
                        "actual": candidate,
                        "distance": edit_distance(expected, candidate),
                        "exact": expected == candidate,
                        "seconds": 0.0,
                    }
                )
        tracemalloc.start()
        memory_frame, _ = render_svg(FIXTURES / manifest["fixtures"][0]["file"])
        engine.recognize(memory_frame)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        engine.close()
    report = {
        "engine": "RapidOCR 3.9.2 / PP-OCRv6 small / ONNX Runtime CPU",
        "fixtures": len(rows),
        "fixture_fonts": fixture_fonts,
        "model_bytes": sum(
            path.stat().st_size for path in args.model_dir.iterdir() if path.is_file()
        ),
        "peak_python_bytes": peak,
        "languages": summarize(rows),
        "accepted": all(item["accepted"] for item in summarize(rows).values()),
        "tesseract": summarize(tesseract_rows) if tesseract_rows else {"status": "skipped"},
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {key: value for key, value in report.items() if key != "results"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    qt_app.processEvents()
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
