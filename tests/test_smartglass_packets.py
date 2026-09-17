from xbox_tv.smartglass import (
    decode_sg_string,
    encode_discovery_request,
    encode_power_on,
    encode_sg_string,
    is_discovery_response,
)

LIVE_ID = "FD00112233445566"


def test_sg_string_roundtrip() -> None:
    encoded = encode_sg_string(LIVE_ID)
    value, offset = decode_sg_string(encoded, 0)
    assert value == LIVE_ID
    assert offset == len(encoded)
    assert encoded == bytes([0x00, 0x10]) + LIVE_ID.encode("ascii") + b"\x00"


def test_power_on_packet_matches_openxbox_simple_message() -> None:
    packet = encode_power_on(LIVE_ID)
    assert packet[:2] == bytes([0xDD, 0x02])
    payload = encode_sg_string(LIVE_ID)
    assert packet[2:4] == len(payload).to_bytes(2, "big")
    assert packet[4:6] == bytes([0x00, 0x02])
    assert packet[6:] == payload


def test_discovery_request_is_plaintext_dd00_version_0() -> None:
    packet = encode_discovery_request()
    assert packet[:2] == bytes([0xDD, 0x00])
    assert packet[4:6] == bytes([0x00, 0x00])
    assert len(packet) == 6 + 10
    assert is_discovery_response(packet) is False


def test_discovery_response_detects_dd01() -> None:
    header = bytes([0xDD, 0x01, 0x00, 0x04, 0x00, 0x00]) + b"\x00\x00\x00\x00"
    assert is_discovery_response(header) is True
    assert is_discovery_response(b"\x00\x00") is False
