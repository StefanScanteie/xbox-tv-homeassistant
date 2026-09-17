"""Xbox SmartGlass plaintext packets and LAN client."""

from __future__ import annotations

import struct

PACKET_DISCOVERY_REQUEST = 0xDD00
PACKET_DISCOVERY_RESPONSE = 0xDD01
PACKET_POWER_ON = 0xDD02
CLIENT_TYPE_ANDROID = 0x0008


def encode_sg_string(value: str) -> bytes:
    payload = value.encode("ascii")
    return struct.pack(">H", len(payload)) + payload + b"\x00"


def decode_sg_string(data: bytes, offset: int = 0) -> tuple[str, int]:
    length = struct.unpack_from(">H", data, offset)[0]
    start = offset + 2
    end = start + length
    value = data[start:end].decode("ascii")
    return value, end + 1


def encode_simple_header(packet_type: int, unprotected_len: int, version: int) -> bytes:
    return struct.pack(">HHH", packet_type, unprotected_len, version)


def encode_power_on(live_id: str) -> bytes:
    payload = encode_sg_string(live_id.upper())
    return encode_simple_header(PACKET_POWER_ON, len(payload), 2) + payload


def encode_discovery_request() -> bytes:
    payload = struct.pack(">IHHH", 0, CLIENT_TYPE_ANDROID, 0, 2)
    return encode_simple_header(PACKET_DISCOVERY_REQUEST, len(payload), 0) + payload


def is_discovery_response(data: bytes) -> bool:
    if len(data) < 2:
        return False
    return struct.unpack_from(">H", data, 0)[0] == PACKET_DISCOVERY_RESPONSE
