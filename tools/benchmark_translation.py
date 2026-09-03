"""Reproducible CPU benchmark for the selected local caption translation models."""

from __future__ import annotations

import argparse
import difflib
import json
import statistics
import sys
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manga_live_translator.config import SourceLanguage  # noqa: E402
from manga_live_translator.text_translation import CTranslate2TextEngine  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/translation/manifest.json"


def percentile95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(0.95 * len(ordered) - 1)))]


def normalized(text: str) -> str:
    return "".join(character.lower() for character in text if character.isalnum())


def quality_score(actual: str, expected: str) -> float:
    return difflib.SequenceMatcher(None, normalized(actual), normalized(expected)).ratio()


def has_excessive_repetition(text: str) -> bool:
    words = [word.casefold().strip(".,!?;:'\"") for word in text.split()]
    words = [word for word in words if word]
    if len(words) < 8:
        return False
    unique_ratio = len(set(words)) / len(words)
    repeated_trigram = any(
        words[index : index + 3] == words[index + 3 : index + 6] for index in range(len(words) - 5)
    )
    return unique_ratio < 0.35 or repeated_trigram


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models/translation")
    parser.add_argument("--output", type=Path, default=ROOT / "build/translation-benchmark.json")
    args = parser.parse_args()
    fixtures: dict[str, Any] = json.loads(FIXTURES.read_text(encoding="utf-8"))
    engine = CTranslate2TextEngine(args.model_dir)
    load_started = time.perf_counter()
    tracemalloc.start()
    engine.load()
    cold_load_seconds = time.perf_counter() - load_started
    rows: list[dict[str, object]] = []
    try:
        for fixture in fixtures["fixtures"]:
            language = (
                SourceLanguage.JAPANESE if fixture["language"] == "ja" else SourceLanguage.CHINESE
            )
            engine.translate(fixture["source"], language)  # warm-up
            result = engine.translate(fixture["source"], language)
            rows.append(
                {
                    **fixture,
                    "actual": result.text,
                    "seconds": result.inference_seconds,
                    "exact_normalized": normalized(result.text) == normalized(fixture["expected"]),
                    "quality_score": quality_score(result.text, fixture["expected"]),
                    "excessive_repetition": has_excessive_repetition(result.text),
                }
            )
        _, peak_python_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        engine.close()
    grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["language"])].append(row)
    languages = {}
    for language, items in grouped.items():
        timings = [float(item["seconds"]) for item in items]
        languages[language] = {
            "fixtures": len(items),
            "exact_normalized_rate": sum(bool(item["exact_normalized"]) for item in items)
            / len(items),
            "mean_quality_score": statistics.mean(float(item["quality_score"]) for item in items),
            "median_seconds": statistics.median(timings),
            "p95_seconds": percentile95(timings),
        }
    model_bytes = sum(path.stat().st_size for path in args.model_dir.rglob("*") if path.is_file())
    failures = [
        row
        for row in rows
        if not row["actual"]
        or bool(row["excessive_repetition"])
        or float(row["quality_score"]) < 0.45
    ]
    accepted = (
        not failures
        and all(item["p95_seconds"] <= 1.5 for item in languages.values())
        and all(item["mean_quality_score"] >= 0.60 for item in languages.values())
    )
    report = {
        "engine": "CTranslate2 / OPUS-MT / int8 / CPU",
        "cold_load_seconds": cold_load_seconds,
        "model_bytes": model_bytes,
        "peak_python_bytes": peak_python_bytes,
        "languages": languages,
        "failures": failures,
        "accepted": accepted,
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
