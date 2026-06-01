"""Tests for Aave V3 generated deduction discovery."""

from unittest.mock import MagicMock

import pytest

import protocols.aave_v3 as aave_v3


CONTRACTS_REGISTRY = {
    "contracts": {
        "USDC": {
            "ethereum": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        },
        "WETH": {
            "ethereum": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        },
        "cbBTC": {
            "base": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        },
    }
}


def test_tracked_deployments_returns_chain_evm_contracts():
    assert aave_v3.tracked_deployments("ethereum", CONTRACTS_REGISTRY) == [
        ("USDC", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"),
        ("WETH", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"),
    ]


def test_get_reserve_atoken_returns_none_when_reserve_does_not_exist():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {
        "result": "0x0000000000000000000000000000000000000000000000000000000000000000"
    }

    assert (
        aave_v3.get_reserve_atoken(
            w3,
            "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        )
        is None
    )


def test_get_reserve_atoken_returns_none_when_pool_reverts():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {"error": {"message": "execution reverted"}}

    assert (
        aave_v3.get_reserve_atoken(
            w3,
            "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        )
        is None
    )


def test_get_reserve_atoken_surfaces_provider_errors():
    w3 = MagicMock()
    w3.provider.make_request.side_effect = TimeoutError("timeout")

    with pytest.raises(TimeoutError, match="timeout"):
        aave_v3.get_reserve_atoken(
            w3,
            "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        )


def test_fetch_atoken_metadata_falls_back_when_alchemy_fails(monkeypatch):
    w3 = MagicMock()
    w3.provider.endpoint_uri = "https://eth-mainnet.g.alchemy.com/v2/demo"

    def fail_alchemy_metadata(_rpc, _address):
        raise RuntimeError("alchemy failed")

    monkeypatch.setattr(
        aave_v3,
        "alchemy_token_metadata",
        fail_alchemy_metadata,
    )
    monkeypatch.setattr(
        aave_v3,
        "fetch_metadata",
        lambda _w3, _address, chain: {
            "chain": chain,
            "address": _address,
            "decimals": 6,
            "name": "Aave Ethereum USDC",
            "symbol": "aEthUSDC",
        },
    )

    assert aave_v3.fetch_atoken_metadata(w3, "0x1234", "ethereum") == {
        "chain": "ethereum",
        "address": "0x1234",
        "decimals": 6,
        "name": "Aave Ethereum USDC",
        "symbol": "aEthUSDC",
    }


def test_build_atoken_record_normalizes_symbol_to_root_token():
    result = aave_v3.build_atoken_record(
        token="cbBTC",
        chain="base",
        underlying="0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        atoken="0xbdb9300b7cde636d9cd4aff00f6f009ffbbc8ee6",
        metadata={
            "decimals": 8,
            "name": "Aave Base cbBTC",
            "symbol": "aBascbBTC",
        },
        market="Base",
    )

    assert result == {
        "token": "cbBTC",
        "chain": "base",
        "address": "0xbdb9300b7cde636d9cd4aff00f6f009ffbbc8ee6",
        "underlying_address": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        "decimals": 8,
        "symbol": "acbBTC",
        "name": "Aave V3 Base cbBTC",
        "onchain_symbol": "aBascbBTC",
        "onchain_name": "Aave Base cbBTC",
        "protocol": "Aave",
        "market": "Base",
        "version": "V3",
        "type": "locked",
    }


def test_discover_atokens_queries_pool_for_each_tracked_underlying(monkeypatch):
    def fake_get_reserve_atoken(_w3, _pool_address, asset):
        responses = {
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": (
                "0x98c23e9d8f34fefb1b7bd6a91b7ff122f4e16f5c"
            ),
            "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": None,
        }
        return responses[asset]

    w3 = MagicMock()
    monkeypatch.setattr(aave_v3, "get_reserve_atoken", fake_get_reserve_atoken)
    monkeypatch.setattr(
        aave_v3,
        "fetch_atoken_metadata",
        lambda _w3, _atoken, _chain: {
            "decimals": 6,
            "name": "Aave Ethereum USDC",
            "symbol": "aEthUSDC",
        },
    )

    result = aave_v3.discover_atokens(
        w3,
        "ethereum",
        CONTRACTS_REGISTRY,
        config={
            "pools": [
                {
                    "chain": "ethereum",
                    "address": "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2",
                    "market": "Core",
                }
            ]
        },
    )

    assert len(result) == 1
    assert result[0]["token"] == "USDC"
    assert result[0]["symbol"] == "aUSDC"
    assert result[0]["onchain_symbol"] == "aEthUSDC"
    assert result[0]["protocol"] == "Aave"
    assert result[0]["market"] == "Core"
