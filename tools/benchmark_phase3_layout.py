"""Offline Phase 3 layout-quality acceptance benchmark."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manga_live_translator.config import ReadingDirection, SourceLanguage  # noqa: E402
from manga_live_translator.ocr import OcrTextBlock  # noqa: E402
from manga_live_translator.ocr.processing import process_manga_layout  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "phase3" / "manifest.json"


def _block(raw: dict[str, Any]) -> OcrTextBlock:
    left, top, right, bottom = (float(value) for value in raw["box"])
    return OcrTextBlock(
        str(raw["text"]),
        float(raw["confidence"]),
        ((left, top), (right, top), (right, bottom), (left, bottom)),
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.fixtures.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    expected_count = recalled_count = correctly_ordered = 0
    vertical_expected = vertical_correct = 0
    timings: list[float] = []
    for fixture in manifest["fixtures"]:
        blocks = tuple(_block(raw) for raw in fixture["blocks"])
        started = time.perf_counter()
        result = process_manga_layout(
            blocks,
            reading_direction=ReadingDirection(fixture["mode"]),
            language=SourceLanguage(fixture["language"]),
            allow_vertical=bool(fixture.get("allow_vertical", False)),
        )
        elapsed = time.perf_counter() - started
        actual = [block.text for block in result.blocks]
        expected = fixture["expected"]
        expected_count += len(expected)
        recalled_count += sum(text in actual for text in expected)
        correctly_ordered += actual == expected
        if fixture.get("allow_vertical"):
            vertical_expected += sum(
                raw["box"][3] - raw["box"][1] >= (raw["box"][2] - raw["box"][0]) * 1.4
                for raw in fixture["blocks"]
            )
            vertical_correct += sum(
                block.orientation.value == "vertical" for block in result.blocks
            )
        timings.append(elapsed)
        rows.append(
            {
                "name": fixture["name"],
                "expected": expected,
                "actual": actual,
                "selected_mode": result.reading_direction.value,
                "expected_mode": fixture.get("expected_mode", fixture["mode"]),
                "seconds": elapsed,
            }
        )
    recall = recalled_count / max(1, expected_count)
    order_accuracy = correctly_ordered / max(1, len(rows))
    report = {
        "fixture_license": manifest["license"],
        "fixtures": len(rows),
        "block_group_recall": recall,
        "reading_order_accuracy": order_accuracy,
        "vertical_candidate_accuracy": vertical_correct / max(1, vertical_expected),
        "median_layout_seconds": sorted(timings)[len(timings) // 2],
        "accepted": recall >= 0.90 and order_accuracy >= 0.95,
        "results": rows,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
