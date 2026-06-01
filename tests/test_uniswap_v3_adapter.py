"""Tests for Uniswap V3 generated pool discovery."""

from unittest.mock import MagicMock

import pytest

import protocols.uniswap_v3 as uniswap_v3


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


def test_pool_candidates_skips_same_root_token():
    deployments = [
        ("USDC", "0x1111111111111111111111111111111111111111"),
        ("USDC", "0x2222222222222222222222222222222222222222"),
        ("WETH", "0x3333333333333333333333333333333333333333"),
    ]

    assert uniswap_v3.pool_candidates(deployments) == [
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


def test_pool_queries_expands_each_pair_across_fee_tiers_in_token_order():
    deployments = [
        ("cbBTC", "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"),
        ("USDC", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"),
    ]

    assert uniswap_v3.pool_queries(deployments, [500, 3000]) == [
        {
            "token0": "USDC",
            "address0": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "token1": "cbBTC",
            "address1": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
            "fee": 500,
        },
        {
            "token0": "USDC",
            "address0": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "token1": "cbBTC",
            "address1": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf",
            "fee": 3000,
        },
    ]


def test_get_pool_returns_none_when_pool_does_not_exist():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {
        "result": "0x0000000000000000000000000000000000000000000000000000000000000000"
    }

    assert (
        uniswap_v3.get_pool(
            w3,
            "0x1f98431c8ad98523631ae4a59f267346ea31f984",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            500,
        )
        is None
    )
    assert w3.provider.make_request.call_count == 2


def test_get_pool_uses_single_raw_call_when_first_order_finds_pool():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {
        "result": (
            "0x000000000000000000000000"
            "88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
        )
    }

    assert uniswap_v3.get_pool(
        w3,
        "0x1f98431c8ad98523631ae4a59f267346ea31f984",
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        500,
    ) == "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    w3.provider.make_request.assert_called_once()


def test_get_pool_tries_reverse_order_only_after_empty_first_call():
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
                "88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
            )
        },
    ]

    assert uniswap_v3.get_pool(
        w3,
        "0x1f98431c8ad98523631ae4a59f267346ea31f984",
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        500,
    ) == "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    assert w3.provider.make_request.call_count == 2


def test_encode_and_decode_get_pool_rpc_payload():
    data = uniswap_v3.encode_get_pool_data(
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        500,
    )

    assert data.startswith("0x1698ee82")
    assert data.endswith("00000000000000000000000000000000000000000000000000000000000001f4")
    assert uniswap_v3.decode_address_result(
        "0x00000000000000000000000088e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    ) == "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    assert uniswap_v3.decode_address_result(
        "0x0000000000000000000000000000000000000000000000000000000000000000"
    ) == uniswap_v3.ZERO_ADDRESS


def test_has_rate_limit_error_detects_429_batch_response():
    assert uniswap_v3.has_rate_limit_error([
        {"id": 1, "result": "0x"},
        {"id": 2, "error": {"code": 429, "message": "rate limited"}},
    ])
    assert not uniswap_v3.has_rate_limit_error([
        {"id": 1, "result": "0x"},
    ])


def test_get_pools_batch_retries_only_empty_results_in_reverse_order(monkeypatch):
    calls = []

    def fake_post_batch(_rpc_url, batch, *, timeout):
        calls.append(batch)
        if len(calls) == 1:
            return [
                {
                    "id": batch[0]["id"],
                    "result": (
                        "0x000000000000000000000000"
                        "88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
                    ),
                },
                {
                    "id": batch[1]["id"],
                    "result": (
                        "0x000000000000000000000000"
                        "0000000000000000000000000000000000000000"
                    ),
                },
            ]
        return [
            {
                "id": batch[0]["id"],
                "result": (
                    "0x000000000000000000000000"
                    "8ad599c3a0ff1de082011efddc58f1908eb6e6d8"
                ),
            }
        ]

    monkeypatch.setattr(uniswap_v3, "post_rpc_batch", fake_post_batch)
    monkeypatch.setattr(uniswap_v3.time, "sleep", lambda *_args: None)

    result = uniswap_v3.get_pools_batch(
        "https://example.invalid",
        "0x1f98431c8ad98523631ae4a59f267346ea31f984",
        [
            {
                "address0": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "address1": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
                "fee": 500,
            },
            {
                "address0": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "address1": "0xdac17f958d2ee523a2206206994597c13d831ec7",
                "fee": 500,
            },
        ],
        batch_size=25,
    )

    assert result == [
        "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8",
    ]
    assert [len(batch) for batch in calls] == [2, 1]


def test_get_pool_returns_none_when_factory_reverts():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {"error": {"message": "execution reverted"}}

    assert (
        uniswap_v3.get_pool(
            w3,
            "0x1f98431c8ad98523631ae4a59f267346ea31f984",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            500,
        )
        is None
    )


def test_get_pool_surfaces_provider_errors():
    w3 = MagicMock()
    w3.provider.make_request.side_effect = TimeoutError("timeout")

    with pytest.raises(TimeoutError, match="timeout"):
        uniswap_v3.get_pool(
            w3,
            "0x1f98431c8ad98523631ae4a59f267346ea31f984",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            500,
        )


def test_build_pool_record_uses_registry_token_symbols_and_fee():
    result = uniswap_v3.build_pool_record(
        token_a="USDC",
        address_a="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        token_b="WETH",
        address_b="0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        chain="ethereum",
        pool="0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        fee=500,
    )

    assert result == {
        "tokens": ["USDC", "WETH"],
        "chain": "ethereum",
        "address": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        "underlying_addresses": {
            "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "WETH": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        },
        "fee": 500,
        "pool": "USDC-WETH",
        "symbol": "USDC-WETH-500",
        "name": "Uniswap V3 USDC-WETH",
        "onchain_name": "Uniswap V3",
        "protocol": "Uniswap",
        "version": "V3",
        "type": "locked",
    }


def test_ordered_underlyings_matches_uniswap_v3_token_order():
    assert uniswap_v3.ordered_underlyings(
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


def test_discover_pools_queries_factory_for_each_fee(monkeypatch):
    def fake_get_pools(_w3, _factory_address, queries):
        responses = {
            (
                "USDC",
                "USDT",
                500,
            ): None,
            (
                "USDC",
                "WETH",
                500,
            ): "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
            (
                "USDT",
                "WETH",
                500,
            ): None,
        }
        return [
            responses.get((query["token0"], query["token1"], query["fee"]))
            for query in queries
        ]

    w3 = MagicMock()
    w3.provider.endpoint_uri = ""
    monkeypatch.setattr(uniswap_v3, "get_pools", fake_get_pools)

    result = uniswap_v3.discover_pools(
        w3,
        "ethereum",
        CONTRACTS_REGISTRY,
        config={
            "factories": [
                {
                    "chain": "ethereum",
                    "address": "0x1f98431c8ad98523631ae4a59f267346ea31f984",
                }
            ],
            "fee_tiers": [500, 3000],
        },
    )

    assert len(result) == 1
    assert result[0]["tokens"] == ["USDC", "WETH"]
    assert result[0]["fee"] == 500
    assert result[0]["symbol"] == "USDC-WETH-500"
    assert result[0]["protocol"] == "Uniswap"
