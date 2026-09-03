"""Validate external text-translation assets and record reproducible SHA-256 hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "tools/translation_models.json")
    parser.add_argument("--output", type=Path, default=ROOT / "build/translation-model-hashes.json")
    args = parser.parse_args()
    manifest: dict[str, Any] = json.loads(args.manifest.read_text(encoding="utf-8"))
    records: list[dict[str, object]] = []
    missing: list[str] = []
    for model in manifest["models"]:
        directory = ROOT / model["output"]
        files: dict[str, dict[str, object]] = {}
        for filename in manifest["required_output_files"]:
            path = directory / filename
            if not path.is_file():
                missing.append(str(path))
                continue
            files[filename] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
        records.append({**model, "files": files})
    report = {"models": records, "missing": missing, "valid": not missing}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
