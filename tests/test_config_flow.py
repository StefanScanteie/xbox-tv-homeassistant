from pathlib import Path


def test_config_flow_defines_menu_step_handlers() -> None:
    text = (Path(__file__).resolve().parents[1] / "custom_components" / "xbox_tv" / "config_flow.py").read_text()
    assert "async def async_step_sign_in" in text
    assert "async def async_step_skip" in text
