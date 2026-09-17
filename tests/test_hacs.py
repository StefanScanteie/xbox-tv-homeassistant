from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "xbox_tv"
HACS_JSON = ROOT / "hacs.json"
MANIFEST = COMPONENT / "manifest.json"
BRAND_ICON = COMPONENT / "brand" / "icon.png"

REQUIRED_MANIFEST_KEYS = (
    "domain",
    "documentation",
    "issue_tracker",
    "codeowners",
    "name",
    "version",
)


def test_single_integration_directory() -> None:
    dirs = [path for path in (ROOT / "custom_components").iterdir() if path.is_dir()]
    assert [path.name for path in dirs] == ["xbox_tv"]


def test_hacs_json_has_required_name() -> None:
    data = json.loads(HACS_JSON.read_text())
    assert data["name"] == "Xbox TV"
    assert "filename" not in data
    assert data.get("content_in_root") is not True


def test_manifest_has_hacs_required_keys() -> None:
    data = json.loads(MANIFEST.read_text())
    for key in REQUIRED_MANIFEST_KEYS:
        assert key in data, key
    assert data["domain"] == "xbox_tv"
    assert data["codeowners"] == ["@StefanScanteie"]
    assert data["documentation"].startswith("https://")
    assert data["issue_tracker"].endswith("/issues")


def test_brand_icon_exists_for_hacs() -> None:
    assert BRAND_ICON.is_file()
