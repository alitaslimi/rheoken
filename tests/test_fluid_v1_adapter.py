"""Tests for Fluid fToken liquidity deduction discovery."""

from unittest.mock import MagicMock

import protocols.fluid_v1 as fluid


CONTRACTS_REGISTRY = {
    "contracts": {
        "USDC": {
            "base": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        },
        "WETH": {
            "base": "0x4200000000000000000000000000000000000006",
        },
        "SOL": {
            "solana": "So11111111111111111111111111111111111111112",
        },
    }
}


def encode_address_array(addresses):
    words = [
        "20".rjust(64, "0"),
        hex(len(addresses)).removeprefix("0x").rjust(64, "0"),
    ]
    words.extend(address.removeprefix("0x").rjust(64, "0") for address in addresses)
    return f"0x{''.join(words)}"


def test_tracked_deployments_by_address_returns_chain_evm_contracts():
    assert fluid.tracked_deployments_by_address("base", CONTRACTS_REGISTRY) == {
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": "USDC",
        "0x4200000000000000000000000000000000000006": "WETH",
    }


def test_decode_address_array_result_decodes_all_tokens_return_value():
    assert fluid.decode_address_array_result(encode_address_array([
        "0x1111111111111111111111111111111111111111",
        "0x2222222222222222222222222222222222222222",
    ])) == [
        "0x1111111111111111111111111111111111111111",
        "0x2222222222222222222222222222222222222222",
    ]


def test_get_all_tokens_returns_empty_when_factory_reverts():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {"error": {"message": "execution reverted"}}

    assert fluid.get_all_tokens(
        w3,
        "0x54b91a0d94cb471f37f949c60f7fa7935b551d03",
    ) == []


def test_get_asset_returns_none_when_ftoken_reverts():
    w3 = MagicMock()
    w3.provider.make_request.return_value = {"error": {"message": "execution reverted"}}

    assert fluid.get_asset(
        w3,
        "0x1111111111111111111111111111111111111111",
    ) is None


def test_build_fluid_record_uses_liquidity_contract_as_deduction_address():
    result = fluid.build_fluid_record(
        token="USDC",
        chain="base",
        underlying="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        ftoken="0x1111111111111111111111111111111111111111",
        liquidity_contract="0x52aa899454998be5b000ad077a46bbe360f4e497",
        factory="0x54b91a0d94cb471f37f949c60f7fa7935b551d03",
        metadata={
            "decimals": 6,
            "name": "Fluid USDC",
            "symbol": "fUSDC",
        },
    )

    assert result == {
        "token": "USDC",
        "chain": "base",
        "address": "0x52aa899454998be5b000ad077a46bbe360f4e497",
        "underlying_address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "ftoken_address": "0x1111111111111111111111111111111111111111",
        "factory": "0x54b91a0d94cb471f37f949c60f7fa7935b551d03",
        "liquidity_contract": "0x52aa899454998be5b000ad077a46bbe360f4e497",
        "decimals": 6,
        "symbol": "fUSDC",
        "name": "Fluid Liquidity Contract USDC",
        "onchain_symbol": "fUSDC",
        "onchain_name": "Fluid USDC",
        "protocol": "Fluid",
        "version": "fToken",
        "type": "locked",
    }


def test_discover_fluid_tokens_keeps_only_ftokens_matching_registry_tokens(monkeypatch):
    monkeypatch.setattr(
        fluid,
        "get_all_tokens",
        lambda _w3, _factory: [
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
        ],
    )
    monkeypatch.setattr(
        fluid,
        "get_asset",
        lambda _w3, ftoken: {
            "0x1111111111111111111111111111111111111111": (
                "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
            ),
            "0x2222222222222222222222222222222222222222": (
                "0x9999999999999999999999999999999999999999"
            ),
        }[ftoken],
    )
    monkeypatch.setattr(
        fluid,
        "fetch_ftoken_metadata",
        lambda _w3, _ftoken, _chain: {
            "decimals": 6,
            "name": "Fluid USDC",
            "symbol": "fUSDC",
        },
    )

    result = fluid.discover_fluid_tokens(
        MagicMock(),
        "base",
        CONTRACTS_REGISTRY,
        config={
            "factories": [
                {
                    "chain": "base",
                    "address": "0x54b91a0d94cb471f37f949c60f7fa7935b551d03",
                    "liquidity_contract": (
                        "0x52aa899454998be5b000ad077a46bbe360f4e497"
                    ),
                }
            ]
        },
    )

    assert len(result) == 1
    assert result[0]["token"] == "USDC"
    assert result[0]["address"] == "0x52aa899454998be5b000ad077a46bbe360f4e497"
    assert result[0]["ftoken_address"] == "0x1111111111111111111111111111111111111111"
