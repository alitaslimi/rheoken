"""Tests for Uniswap V2 generated pair discovery."""

from unittest.mock import MagicMock

import pytest

import protocols.uniswap_v2 as uniswap_v2


CONTRACTS_REGISTRY = {
    "contracts": {
        "USDC": {
            "ethereum": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        },
        "USDT": {
            "ethereum": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        },
        "WETH": {
            "ethereum": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        },
        "cbBTC": {
            "base": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        },
    }
}


def test_pair_candidates_skips_same_root_token():
    deployments = [
        ("USDC", "0x1111111111111111111111111111111111111111"),
        ("USDC", "0x2222222222222222222222222222222222222222"),
        ("WETH", "0x3333333333333333333333333333333333333333"),
    ]

    assert uniswap_v2.pair_candidates(deployments) == [
        (
            "USDC",
            "0x1111111111111111111111111111111111111111",
            "WETH",
            "0x3333333333333333333333333333333333333333",
        ),
        (
            "USDC",
            "0x2222222222222222222222222222222222222222",
            "WETH",
            "0x3333333333333333333333333333333333333333",
        ),
    ]


def test_get_pair_returns_none_when_pair_does_not_exist():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {
        "result": "0x0000000000000000000000000000000000000000000000000000000000000000"
    }

    assert (
        uniswap_v2.get_pair(
            w3,
            "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        )
        is None
    )
    assert w3.provider.make_request.call_count == 2


def test_get_pair_uses_single_raw_call_when_first_order_finds_pair():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {
        "result": (
            "0x000000000000000000000000"
            "b4e16d0168e52d35cacd2c6185b44281ec28c9dc"
        )
    }

    assert uniswap_v2.get_pair(
        w3,
        "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f",
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    ) == "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
    w3.provider.make_request.assert_called_once()


def test_get_pair_tries_reverse_order_only_after_empty_first_call():
    w3 = MagicMock()
    w3.provider.make_request.side_effect = [
        {
            "result": (
                "0x000000000000000000000000"
                "0000000000000000000000000000000000000000"
            )
        },
        {
            "result": (
                "0x000000000000000000000000"
                "b4e16d0168e52d35cacd2c6185b44281ec28c9dc"
            )
        },
    ]

    assert uniswap_v2.get_pair(
        w3,
        "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f",
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    ) == "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
    assert w3.provider.make_request.call_count == 2


def test_get_pair_returns_none_when_factory_reverts():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {"error": {"message": "execution reverted"}}

    assert (
        uniswap_v2.get_pair(
            w3,
            "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        )
        is None
    )


def test_get_pair_surfaces_provider_errors():
    w3 = MagicMock()
    w3.provider.make_request.side_effect = TimeoutError("timeout")

    with pytest.raises(TimeoutError, match="timeout"):
        uniswap_v2.get_pair(
            w3,
            "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        )


def test_build_pair_record_uses_registry_token_symbols():
    result = uniswap_v2.build_pair_record(
        token_a="USDC",
        address_a="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        token_b="WETH",
        address_b="0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        chain="ethereum",
        pair="0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
        metadata={
            "decimals": 18,
            "name": "Uniswap V2",
            "symbol": "UNI-V2",
        },
    )

    assert result == {
        "tokens": ["USDC", "WETH"],
        "chain": "ethereum",
        "address": "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
        "underlying_addresses": {
            "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "WETH": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        },
        "decimals": 18,
        "pool": "USDC-WETH",
        "symbol": "USDC-WETH",
        "name": "Uniswap V2 USDC-WETH",
        "onchain_symbol": "UNI-V2",
        "onchain_name": "Uniswap V2",
        "protocol": "Uniswap",
        "version": "V2",
        "type": "locked",
    }


def test_ordered_underlyings_matches_uniswap_v2_token_order():
    assert uniswap_v2.ordered_underlyings(
        "cbBTC",
        "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
        "USDC",
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    ) == (
        "USDC",
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "cbBTC",
        "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
    )


def test_discover_pairs_queries_factory_for_each_tracked_pair(monkeypatch):
    def fake_get_pair(_w3, _factory_address, token_a, token_b):
        responses = {
            (
                "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "0xdac17f958d2ee523a2206206994597c13d831ec7",
            ): uniswap_v2.ZERO_ADDRESS,
            (
                "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            ): "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
            (
                "0xdac17f958d2ee523a2206206994597c13d831ec7",
                "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            ): uniswap_v2.ZERO_ADDRESS,
        }
        pair = responses.get((token_a, token_b), uniswap_v2.ZERO_ADDRESS)
        return None if pair == uniswap_v2.ZERO_ADDRESS else pair

    w3 = MagicMock()
    monkeypatch.setattr(uniswap_v2, "get_pair", fake_get_pair)
    monkeypatch.setattr(
        uniswap_v2,
        "fetch_pair_metadata",
        lambda _w3, _pair, _chain: {
            "decimals": 18,
            "name": "Uniswap V2",
            "symbol": "UNI-V2",
        },
    )

    result = uniswap_v2.discover_pairs(
        w3,
        "ethereum",
        CONTRACTS_REGISTRY,
        config={
            "factories": [
                {
                    "chain": "ethereum",
                    "address": "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f",
                }
            ]
        },
    )

    assert len(result) == 1
    assert result[0]["tokens"] == ["USDC", "WETH"]
    assert result[0]["symbol"] == "USDC-WETH"
    assert result[0]["protocol"] == "Uniswap"
