from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"
ICON_PATH = "custom_components/xbox_tv/brand/icon.png"
RAW_ICON_URL = (
    "https://raw.githubusercontent.com/StefanScanteie/xbox-tv-homeassistant/"
    f"main/{ICON_PATH}"
)


def test_readme_icon_uses_absolute_url_for_hacs() -> None:
    text = README.read_text()
    assert RAW_ICON_URL in text
    assert f'src="{ICON_PATH}"' not in text
    assert f"]({ICON_PATH})" not in text
