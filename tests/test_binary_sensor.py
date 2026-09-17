from pathlib import Path

from xbox_tv.const import PLATFORMS


def test_binary_sensor_platform_is_registered() -> None:
    assert "binary_sensor" in PLATFORMS
    init_text = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "xbox_tv"
        / "__init__.py"
    ).read_text()
    assert "PLATFORMS" in init_text

    sensor_text = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "xbox_tv"
        / "binary_sensor.py"
    ).read_text()
    assert "BinarySensorDeviceClass.OCCUPANCY" in sensor_text
    assert "Occupied" in sensor_text
    assert "powered_on" in sensor_text
