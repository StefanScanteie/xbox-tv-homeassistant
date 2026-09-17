"""Xbox SmartGlass plaintext packets and LAN client."""

from __future__ import annotations

import asyncio
import struct
from typing import Protocol

from .const import POLL_TIMEOUT, SMARTGLASS_PORT

_BROADCAST_HOSTS = frozenset({"255.255.255.255", "239.255.255.250"})

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


class UdpTransport(Protocol):
    async def send(self, data: bytes, host: str, port: int) -> None: ...

    async def send_recv(
        self, data: bytes, host: str, port: int, timeout: float
    ) -> bytes | None: ...


class _DatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport | None = None
        self._pending: asyncio.Future[bytes] | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self._pending is not None and not self._pending.done():
            self._pending.set_result(data)

    def error_received(self, exc: Exception) -> None:
        if self._pending is not None and not self._pending.done():
            self._pending.set_exception(exc)


class AsyncioUdpTransport:
    def __init__(self) -> None:
        self._protocol: _DatagramProtocol | None = None
        self._transport: asyncio.DatagramTransport | None = None

    async def _ensure_endpoint(self) -> _DatagramProtocol:
        if self._protocol is None:
            loop = asyncio.get_running_loop()
            transport, protocol = await loop.create_datagram_endpoint(
                _DatagramProtocol,
                local_addr=("0.0.0.0", 0),
                allow_broadcast=True,
            )
            self._transport = transport  # type: ignore[assignment]
            self._protocol = protocol
        return self._protocol

    async def send(self, data: bytes, host: str, port: int) -> None:
        protocol = await self._ensure_endpoint()
        assert protocol.transport is not None
        try:
            protocol.transport.sendto(data, (host, port))
        except OSError:
            if host not in _BROADCAST_HOSTS:
                raise

    async def send_recv(
        self, data: bytes, host: str, port: int, timeout: float
    ) -> bytes | None:
        protocol = await self._ensure_endpoint()
        assert protocol.transport is not None
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bytes] = loop.create_future()
        protocol._pending = future
        try:
            try:
                protocol.transport.sendto(data, (host, port))
            except OSError:
                return None
            try:
                return await asyncio.wait_for(future, timeout)
            except (TimeoutError, OSError):
                return None
            except Exception:
                return None
        finally:
            protocol._pending = None


class SmartGlassClient:
    def __init__(
        self,
        host: str,
        live_id: str,
        port: int = SMARTGLASS_PORT,
        timeout: float = POLL_TIMEOUT,
        *,
        udp: UdpTransport | None = None,
    ) -> None:
        self._host = host
        self._live_id = live_id
        self._port = port
        self._timeout = timeout
        self._udp = udp if udp is not None else AsyncioUdpTransport()

    async def async_get_powered_on(self) -> bool:
        try:
            response = await self._udp.send_recv(
                encode_discovery_request(),
                self._host,
                self._port,
                self._timeout,
            )
        except OSError:
            return False
        return response is not None and is_discovery_response(response)

    async def async_power_on(self) -> None:
        packet = encode_power_on(self._live_id)
        destinations = (self._host, "255.255.255.255", "239.255.255.250")
        for host in destinations:
            for _ in range(2):
                await self._udp.send(packet, host, self._port)
