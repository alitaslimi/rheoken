"""Tests for token metadata registry updates."""

from fetch_metadata import _safe_error, build_metadata, is_evm_address, iter_contracts


def test_iter_contracts_expands_address_lists():
    contracts = {
        "contracts": {
            "USDC": {
                "arbitrum": [
                    "0xaf88d065e77c8cc2239327c5edb3a432268e5831",
                    "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8",
                ],
                "solana": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            }
        }
    }

    assert list(iter_contracts(contracts)) == [
        ("USDC", "arbitrum", "0xaf88d065e77c8cc2239327c5edb3a432268e5831"),
        ("USDC", "arbitrum", "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8"),
        ("USDC", "solana", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"),
    ]


def test_is_evm_address_rejects_non_evm_identifiers():
    assert is_evm_address("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")
    assert not is_evm_address("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    assert not is_evm_address(
        "0xdba34672e30cb065b1f93e3ab55318768fd6fef66c15942c9f7cb846e2f900e7::usdc::USDC"
    )


def test_build_metadata_uses_address_keyed_shape_and_skips_non_evm():
    contracts = {
        "contracts": {
            "USDC": {
                "ethereum": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "solana": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            }
        }
    }

    def fetcher(token, chain, address):
        assert token == "USDC"
        assert chain == "ethereum"
        assert address == "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
        return {"symbol": "USDC", "name": "USD Coin", "decimals": 6, "ignored": True}

    assert build_metadata(contracts, fetcher) == {
        "metadata": {
            "USDC": {
                "ethereum": {
                    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {
                        "symbol": "USDC",
                        "name": "USD Coin",
                        "decimals": 6,
                    }
                }
            }
        }
    }


def test_build_metadata_preserves_existing_entries_unless_refreshing():
    contracts = {
        "contracts": {
            "USDT": {
                "ethereum": "0xdac17f958d2ee523a2206206994597c13d831ec7",
            }
        }
    }
    existing = {
        "metadata": {
            "USDT": {
                "ethereum": {
                    "0xdac17f958d2ee523a2206206994597c13d831ec7": {
                        "symbol": "USDT",
                        "name": "Tether USD",
                        "decimals": 6,
                    }
                }
            }
        }
    }

    calls = []

    def fetcher(token, chain, address):
        calls.append((token, chain, address))
        return {"symbol": "USD\u20ae", "name": "Tether USD", "decimals": 6}

    assert build_metadata(contracts, fetcher, existing=existing) == existing
    assert calls == []

    refreshed = build_metadata(contracts, fetcher, existing=existing, refresh=True)
    assert refreshed["metadata"]["USDT"]["ethereum"][
        "0xdac17f958d2ee523a2206206994597c13d831ec7"
    ]["symbol"] == "USD\u20ae"
    assert calls == [("USDT", "ethereum", "0xdac17f958d2ee523a2206206994597c13d831ec7")]


def test_build_metadata_fetches_missing_entries_while_preserving_existing():
    contracts = {
        "contracts": {
            "USDC": {
                "ethereum": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "polygon": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
            }
        }
    }
    existing = {
        "metadata": {
            "USDC": {
                "ethereum": {
                    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {
                        "symbol": "USDC",
                        "name": "USD Coin",
                        "decimals": 6,
                    }
                }
            }
        }
    }
    skipped = []

    def fetcher(token, chain, address):
        assert (token, chain, address) == (
            "USDC",
            "polygon",
            "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
        )
        return {"symbol": "USDC", "name": "USD Coin", "decimals": 6}

    result = build_metadata(
        contracts,
        fetcher,
        existing=existing,
        on_skip=lambda token, chain, address, reason: skipped.append(
            (token, chain, address, reason)
        ),
    )

    assert set(result["metadata"]["USDC"]) == {"ethereum", "polygon"}
    assert skipped == [
        (
            "USDC",
            "ethereum",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "already present",
        )
    ]


def test_build_metadata_reports_skipped_non_evm_entries():
    contracts = {
        "contracts": {
            "USDC": {
                "solana": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            }
        }
    }
    skipped = []

    result = build_metadata(
        contracts,
        lambda *_args: {},
        on_skip=lambda token, chain, address, reason: skipped.append(
            (token, chain, address, reason)
        ),
    )

    assert result == {"metadata": {}}
    assert skipped == [
        (
            "USDC",
            "solana",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "unsupported non-EVM address",
        )
    ]


def test_build_metadata_can_continue_after_fetch_error():
    contracts = {
        "contracts": {
            "USDC": {
                "ethereum": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            }
        }
    }
    errors = []

    def fetcher(_token, _chain, _address):
        raise RuntimeError("rpc unavailable")

    result = build_metadata(
        contracts,
        fetcher,
        on_error=lambda token, chain, address, exc: errors.append(
            (token, chain, address, str(exc))
        ),
    )

    assert result == {"metadata": {}}
    assert errors == [
        ("USDC", "ethereum", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "rpc unavailable")
    ]


def test_safe_error_redacts_alchemy_rpc_urls():
    error = RuntimeError(
        "https://tempo-mainnet.g.alchemy.com/v2/not-a-real-key: not connected"
    )

    assert _safe_error(error) == (
        "https://tempo-mainnet.g.alchemy.com/v2/<redacted> not connected"
    )
