"""Tests for generic EVM RPC helpers."""

from unittest.mock import MagicMock, patch

import pytest

from rpcs.base import (
    BURN_ADDRESSES,
    DEFAULT_RPC_TIMEOUT,
    NATIVE_TOKEN_ADDRESS,
    balance,
    block_info,
    connect,
    native_balance,
    rpc_candidates,
    safe_error,
    supply,
)


CHAIN_CONFIG = {
    "chain_id": 1,
    "public_rpcs": ["https://ethereum.publicnode.com"],
}


def test_connect_uses_timeout_without_rpc_preflight(monkeypatch):
    monkeypatch.delenv("ALCHEMY_API_KEY", raising=False)
    monkeypatch.delenv("DRPC_API_KEY", raising=False)
    fake_w3 = MagicMock()
    fake_w3.is_connected.return_value = True
    chain_id = MagicMock(return_value=1)
    type(fake_w3.eth).chain_id = property(chain_id)

    with patch("rpcs.base.Web3", return_value=fake_w3) as web3_cls:
        web3_cls.HTTPProvider = MagicMock()
        result = connect("ethereum", CHAIN_CONFIG)

    assert result is fake_w3
    fake_w3.is_connected.assert_not_called()
    chain_id.assert_not_called()
    web3_cls.HTTPProvider.assert_called_with(
        "https://ethereum.publicnode.com",
        request_kwargs={"timeout": DEFAULT_RPC_TIMEOUT},
    )


def test_rpc_candidates_uses_alchemy_key_from_env(monkeypatch):
    monkeypatch.setenv("ALCHEMY_API_KEY", "secret")
    monkeypatch.delenv("DRPC_API_KEY", raising=False)

    assert rpc_candidates(
        "avalanche",
        {
            "public_rpcs": ["https://avalanche.public-rpc.com"],
        },
    ) == [
        "https://avax-mainnet.g.alchemy.com/v2/secret",
        "https://avalanche.public-rpc.com",
    ]


def test_rpc_candidates_uses_drpc_key_from_env(monkeypatch):
    monkeypatch.setenv("DRPC_API_KEY", "drpc-secret")
    monkeypatch.delenv("ALCHEMY_API_KEY", raising=False)

    assert rpc_candidates(
        "arbitrum",
        {
            "public_rpcs": ["https://arbitrum.publicnode.com"],
        },
    ) == [
        "https://lb.drpc.live/arbitrum/drpc-secret",
        "https://arbitrum.publicnode.com",
    ]


def test_rpc_candidates_prefers_alchemy_before_drpc_and_public(monkeypatch):
    monkeypatch.setenv("ALCHEMY_API_KEY", "alchemy-secret")
    monkeypatch.setenv("DRPC_API_KEY", "drpc-secret")

    assert rpc_candidates(
        "arbitrum",
        {
            "public_rpcs": ["https://arbitrum.publicnode.com"],
        },
    ) == [
        "https://arb-mainnet.g.alchemy.com/v2/alchemy-secret",
        "https://lb.drpc.live/arbitrum/drpc-secret",
        "https://arbitrum.publicnode.com",
    ]


def test_safe_error_redacts_rpc_api_keys(monkeypatch):
    monkeypatch.setenv("ALCHEMY_API_KEY", "alchemy-secret")
    monkeypatch.setenv("DRPC_API_KEY", "drpc-secret")

    error = RuntimeError(
        "failed for https://arb-mainnet.g.alchemy.com/v2/alchemy-secret "
        "and https://lb.drpc.live/arbitrum/drpc-secret"
    )

    assert safe_error(error) == (
        "failed for https://arb-mainnet.g.alchemy.com/v2/<redacted> "
        "and https://lb.drpc.live/arbitrum/<redacted>"
    )


def test_block_info_returns_parsed_number_and_timestamp():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {
        "result": {"number": hex(12345), "timestamp": hex(1700000000)}
    }

    assert block_info(w3) == (12345, 1700000000)
    w3.provider.make_request.assert_called_with("eth_getBlockByNumber", ["latest", False])


def test_supply_uses_single_raw_eth_call():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {"result": hex(12345)}

    assert supply(w3, "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48") == 12345
    w3.provider.make_request.assert_called_once_with(
        "eth_call",
        [
            {
                "to": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "data": "0x18160ddd",
            },
            "latest",
        ],
    )


def test_balance_uses_single_raw_eth_call_at_resolved_block():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {"result": hex(99)}

    assert (
        balance(
            w3,
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "0x5754284f345afc66a98fbb0a0afe71e0f007b949",
            12345,
        )
        == 99
    )
    w3.provider.make_request.assert_called_once_with(
        "eth_call",
        [
            {
                "to": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "data": (
                    "0x70a08231"
                    "0000000000000000000000005754284f345afc66a98fbb0a0afe71e0f007b949"
                ),
            },
            "0x3039",
        ],
    )


def test_raw_eth_call_errors_are_raised():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {"error": {"message": "execution reverted"}}

    with pytest.raises(RuntimeError, match="eth_call failed"):
        supply(w3, "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")


def test_native_token_address_is_the_defi_convention():
    assert NATIVE_TOKEN_ADDRESS == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"


def test_only_null_address_is_default_burn_address():
    assert BURN_ADDRESSES == {
        "0x0000000000000000000000000000000000000000": "Null Address"
    }


def test_native_balance_calls_eth_get_balance_with_checksummed_address():
    w3 = MagicMock()
    w3.eth.get_balance.return_value = 12345

    assert native_balance(w3, "0x036676389e48133b63a802f8635ad39e752d375d") == 12345
    args, kwargs = w3.eth.get_balance.call_args
    assert args[0] == "0x036676389e48133B63a802f8635AD39E752D375D"
    assert kwargs == {"block_identifier": "latest"}
