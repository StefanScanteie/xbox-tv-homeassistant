from xbox_tv.const import is_valid_host, is_valid_live_id


def test_valid_host_accepts_ipv4_and_hostname() -> None:
    assert is_valid_host("192.168.1.50") is True
    assert is_valid_host("xbox.local") is True


def test_valid_host_rejects_empty() -> None:
    assert is_valid_host("") is False
    assert is_valid_host("   ") is False


def test_valid_live_id_accepts_hex() -> None:
    assert is_valid_live_id("FD00112233445566") is True
    assert is_valid_live_id("fd00112233445566") is True


def test_valid_live_id_rejects_short_or_non_alnum() -> None:
    assert is_valid_live_id("FD00") is False
    assert is_valid_live_id("FD00-1122-3344") is False
    assert is_valid_live_id("") is False
