from pathlib import Path
import json

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "xbox_tv"


def test_production_modules_use_relative_imports() -> None:
    for path in COMPONENT.glob("*.py"):
        text = path.read_text()
        assert "from xbox_tv." not in text, path.name
        assert "import xbox_tv." not in text, path.name


def test_translation_json_has_no_trailing_commas() -> None:
    for path in [COMPONENT / "strings.json", COMPONENT / "translations" / "en.json"]:
        json.loads(path.read_text())
