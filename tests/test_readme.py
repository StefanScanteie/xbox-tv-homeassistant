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


def test_readme_covers_setup_homekit_and_microsoft_account() -> None:
    text = README.read_text()
    assert "Xbox network device ID" in text
    assert "mode: accessory" in text
    assert "xccs.xboxlive.com" in text
    assert "no known account-ban risk" in text
    assert "official `xbox` integration" in text
    assert "388ea51c-0b25-4029-aae2-17df49d23905" in text
    assert "GoHome" in text
    assert "ActivateApplicationWithOneStoreProductId" in text
    assert "Something went wrong" in text
    assert "hacs_repository" in text
