"""Tests for token metadata adapter."""

from unittest.mock import MagicMock

from rpcs.base import _decode_text, fetch_metadata


def encode_string_result(value: str) -> str:
    encoded = value.encode()
    padded_length = ((len(encoded) + 31) // 32) * 32
    return (
        "0x"
        + hex(32).removeprefix("0x").rjust(64, "0")
        + hex(len(encoded)).removeprefix("0x").rjust(64, "0")
        + encoded.hex().ljust(padded_length * 2, "0")
    )


def test_fetch_metadata_returns_deployment_shape():
    w3 = MagicMock()
    w3.provider.make_request.side_effect = [
        {"result": hex(6)},
        {"result": encode_string_result("USDC")},
        {"result": encode_string_result("USD Coin")},
    ]

    result = fetch_metadata(
        w3,
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        chain="ethereum",
    )

    assert result == {
        "chain": "ethereum",
        "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "decimals": 6,
        "symbol": "USDC",
        "name": "USD Coin",
    }
    assert w3.provider.make_request.call_count == 3


def test_decode_text_preserves_special_characters():
    assert _decode_text("USD\u20ae0") == "USD\u20ae0"


def test_decode_text_handles_bytes32_values():
    value = b"USDC" + b"\x00" * 28

    assert _decode_text(value) == "USDC"
