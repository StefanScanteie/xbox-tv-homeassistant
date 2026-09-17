from pathlib import Path


def test_config_flow_defines_menu_step_handlers() -> None:
    text = (Path(__file__).resolve().parents[1] / "custom_components" / "xbox_tv" / "config_flow.py").read_text()
    assert "async def async_step_sign_in" in text
    assert "async def async_step_skip" in text


def test_config_flow_defines_options_flow() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "xbox_tv"
        / "config_flow.py"
    ).read_text()
    assert "async_get_options_flow" in text
    assert "class XboxTvOptionsFlow" in text
    assert "CONF_HIDE_DLC" in text
    assert "CONF_HIDE_SYSTEM_APPS" in text
    assert "CONF_FAVORITES" in text
