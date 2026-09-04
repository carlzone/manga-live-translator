"""Verify that a packaged release is complete and contains no model weights."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_SUFFIXES = {".onnx", ".bin", ".spm"}
REQUIRED_DOCUMENTS = (
    "README.md",
    "RELEASE_NOTES.md",
    "PRIVACY.md",
    "THIRD_PARTY_NOTICES.md",
    "WINDOWS_ACCEPTANCE_CHECKLIST.md",
)


def verify(release_dir: Path) -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    executable = release_dir / "MangaLiveTranslator.exe"
    if not executable.is_file():
        errors.append(f"missing executable: {executable}")
    for name in REQUIRED_DOCUMENTS:
        if not (release_dir / name).is_file():
            errors.append(f"missing release document: {name}")
    weights = [
        str(path.relative_to(release_dir))
        for path in release_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() in MODEL_SUFFIXES
    ]
    if weights:
        errors.append("release contains model weights: " + ", ".join(weights))
    digest = None
    if executable.is_file():
        checksum = hashlib.sha256(executable.read_bytes()).hexdigest()
        digest = {"file": executable.name, "sha256": checksum, "bytes": executable.stat().st_size}
    return {"executable": digest, "model_weights": weights, "valid": not errors}, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", nargs="?", type=Path, default=ROOT / "dist" / "release")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report, errors = verify(args.release_dir)
    report["errors"] = errors
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

