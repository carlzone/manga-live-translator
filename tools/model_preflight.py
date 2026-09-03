"""Verify all external OCR and translation model assets and print SHA-256 output."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify(root: Path) -> tuple[list[dict[str, object]], list[str]]:
    ocr: dict[str, Any] = json.loads(
        (ROOT / "tools/ocr_models.json").read_text(encoding="utf-8-sig")
    )
    translation: dict[str, Any] = json.loads(
        (ROOT / "tools/translation_models.json").read_text(encoding="utf-8-sig")
    )
    rows: list[dict[str, object]] = []
    errors: list[str] = []
    for item in ocr["files"]:
        path = root / "ocr" / item["name"]
        actual = digest(path) if path.is_file() else None
        valid = actual == item["sha256"]
        rows.append({"path": str(path), "sha256": actual, "valid": valid})
        if not valid:
            errors.append(f"missing or invalid OCR asset: {path}")
    for model in translation["models"]:
        directory = root / "translation" / f"{model['language']}-en"
        for name in translation["required_output_files"]:
            path = directory / name
            actual = digest(path) if path.is_file() else None
            rows.append({"path": str(path), "sha256": actual, "valid": actual is not None})
            if actual is None:
                errors.append(f"missing translation asset: {path}")
    return rows, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows, errors = verify(args.model_dir)
    report = {"assets": rows, "errors": errors, "valid": not errors}
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
