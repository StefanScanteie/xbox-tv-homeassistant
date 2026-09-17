import pytest

from xbox_tv.smartglass import (
    SmartGlassClient,
    encode_discovery_request,
    encode_power_on,
    is_discovery_response,
)


class FakeUdp:
    def __init__(self, response: bytes | None = None) -> None:
        self.sent: list[tuple[bytes, str, int]] = []
        self.response = response

    async def send(self, data: bytes, host: str, port: int) -> None:
        self.sent.append((data, host, port))

    async def send_recv(
        self, data: bytes, host: str, port: int, timeout: float
    ) -> bytes | None:
        self.sent.append((data, host, port))
        return self.response


@pytest.mark.asyncio
async def test_get_powered_on_true_on_discovery_response() -> None:
    reply = bytes([0xDD, 0x01, 0x00, 0x00, 0x00, 0x00])
    udp = FakeUdp(reply)
    client = SmartGlassClient("192.168.1.50", "FD00112233445566", udp=udp)
    assert await client.async_get_powered_on() is True
    assert udp.sent[0][0] == encode_discovery_request()
    assert udp.sent[0][1:] == ("192.168.1.50", 5050)


@pytest.mark.asyncio
async def test_get_powered_on_false_on_timeout() -> None:
    client = SmartGlassClient("192.168.1.50", "FD00112233445566", udp=FakeUdp(None))
    assert await client.async_get_powered_on() is False


@pytest.mark.asyncio
async def test_power_on_sends_to_host_broadcast_and_multicast() -> None:
    udp = FakeUdp()
    live_id = "FD00112233445566"
    client = SmartGlassClient("192.168.1.50", live_id, udp=udp)
    await client.async_power_on()
    packet = encode_power_on(live_id)
    hosts = [dest for _data, dest, _port in udp.sent]
    assert hosts.count("192.168.1.50") == 2
    assert hosts.count("255.255.255.255") == 2
    assert hosts.count("239.255.255.250") == 2
    assert all(data == packet for data, _h, _p in udp.sent)
