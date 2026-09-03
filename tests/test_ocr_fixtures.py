import json
from pathlib import Path


def test_ocr_fixture_manifest_is_complete_and_license_safe() -> None:
    root = Path(__file__).parent / "fixtures" / "ocr"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    fixtures = manifest["fixtures"]
    assert len(fixtures) == 30
    assert "project-created" in manifest["license"]
    assert {item["language"] for item in fixtures} == {"ja", "zh-CN", "zh-TW"}
    assert all((root / item["file"]).is_file() for item in fixtures)
    assert all(item["expected"] for item in fixtures)
