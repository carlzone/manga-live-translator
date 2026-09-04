"""Synthetic long-session gate for bounded timing storage and process resource drift."""

from __future__ import annotations

import argparse
import json
import time

from manga_live_translator.config import ReadingDirection
from manga_live_translator.diagnostics import RuntimeDiagnostics, _process_memory_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=600.0, help="Run duration in seconds")
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--maximum-memory-growth-mib", type=float, default=32.0)
    args = parser.parse_args()
    if args.duration <= 0 or args.interval <= 0:
        parser.error("duration and interval must be positive")

    diagnostics = RuntimeDiagnostics(maximum_samples=500)
    memory_start = _process_memory_bytes()
    deadline = time.monotonic() + args.duration
    samples = 0
    while time.monotonic() < deadline:
        diagnostics.record_viewport(
            ocr_seconds=0.15,
            translation_seconds=0.05,
            completion_seconds=0.4,
            translated_blocks=4,
            failed_blocks=0,
        )
        samples += 1
        time.sleep(min(args.interval, max(0.0, deadline - time.monotonic())))
    memory_end = _process_memory_bytes()
    growth = (
        max(0, memory_end - memory_start)
        if memory_start is not None and memory_end is not None
        else None
    )
    valid = growth is None or growth <= args.maximum_memory_growth_mib * 1024 * 1024
    report = {
        "duration_seconds": args.duration,
        "iterations": samples,
        "retained_timing_samples": len(diagnostics._ocr_seconds),
        "memory_start_bytes": memory_start,
        "memory_end_bytes": memory_end,
        "memory_growth_bytes": growth,
        "valid": valid,
        "diagnostics": diagnostics.report(
            region=None, reading_direction=ReadingDirection.AUTOMATIC, state="Synthetic complete"
        ),
    }
    print(json.dumps(report, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
