"""Tests for unified token registry builder."""

from build_tokens import build_tokens, sort_json


def test_build_tokens_merges_contracts_metadata_taxonomies_and_deduction_labels():
    contracts = {
        "contracts": {
            "USDC": {
                "arbitrum": [
                    "0xaf88d065e77cc2239327c5edb3a432268e5831",
                    "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8",
                ],
                "solana": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            }
        }
    }
    metadata = {
        "metadata": {
            "USDC": {
                "arbitrum": {
                    "0xaf88d065e77cc2239327c5edb3a432268e5831": {
                        "name": "USD Coin",
                        "symbol": "USDC",
                        "decimals": 6,
                    }
                }
            }
        }
    }
    taxonomies = {
        "taxonomies": {
            "USDC": {
                "category": "Stablecoin",
                "denomination": "USD",
            }
        }
    }
    deductions = {
        "deductions": {
            "USDC": {
                "arbitrum": [
                    {
                        "address": "0x2df1c51e09aecf9cacb7bc98cb1742757f163df7",
                        "type": "locked",
                    }
                ]
            }
        }
    }
    labels = {
        "labels": {
            "arbitrum": {
                "0x2df1c51e09aecf9cacb7bc98cb1742757f163df7": {
                    "name": "Hyperliquid Deposit Bridge 2",
                    "protocol": "Hyperliquid",
                }
            }
        }
    }
    protocols = [
        {
            "aave_v3": [
                {
                    "token": "USDC",
                    "chain": "arbitrum",
                    "address": "0x724dc807b04555b71ed48a6896b6f41593b8c637",
                    "decimals": 6,
                    "market": "Arbitrum",
                    "name": "Aave V3 Arbitrum USDC.e",
                    "onchain_name": "Aave Arbitrum USDC",
                    "onchain_symbol": "aArbUSDC",
                    "protocol": "Aave",
                    "symbol": "aUSDC",
                    "type": "locked",
                    "underlying_address": "0xaf88d065e77cc2239327c5edb3a432268e5831",
                    "version": "V3",
                }
            ]
        }
    ]

    assert build_tokens(
        contracts,
        metadata,
        taxonomies,
        deductions,
        labels,
        protocols,
    ) == {
        "tokens": {
            "USDC": {
                "deployments": {
                    "arbitrum": [
                        {
                            "address": "0xaf88d065e77cc2239327c5edb3a432268e5831",
                            "decimals": 6,
                            "name": "USD Coin",
                            "symbol": "USDC",
                        },
                        {
                            "address": "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8",
                        },
                    ],
                    "solana": [
                        {
                            "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                        }
                    ],
                },
                "deductions": {
                    "arbitrum": [
                        {
                            "address": "0x2df1c51e09aecf9cacb7bc98cb1742757f163df7",
                            "labels": {
                                "name": "Hyperliquid Deposit Bridge 2",
                                "protocol": "Hyperliquid",
                            },
                            "type": "locked",
                        },
                        {
                            "address": "0x724dc807b04555b71ed48a6896b6f41593b8c637",
                            "labels": {
                                "market": "Arbitrum",
                                "name": "Aave V3 Arbitrum USDC.e",
                                "protocol": "Aave",
                                "symbol": "aUSDC",
                                "version": "V3",
                            },
                            "type": "locked",
                        },
                    ]
                },
                "taxonomies": {
                    "category": "Stablecoin",
                    "denomination": "USD",
                },
            },
            "aUSDC": {
                "deployments": {
                    "arbitrum": [
                        {
                            "address": "0x724dc807b04555b71ed48a6896b6f41593b8c637",
                            "decimals": 6,
                            "name": "Aave Arbitrum USDC",
                            "symbol": "aArbUSDC",
                        }
                    ]
                },
                "taxonomies": {
                    "category": "Lending",
                    "issuer": "Aave",
                },
            },
        }
    }


def test_sort_json_orders_token_entry_keys_for_readability():
    assert list(sort_json({
        "deductions": {},
        "deployments": {},
        "taxonomies": {},
    })) == ["taxonomies", "deployments", "deductions"]


def test_build_tokens_applies_manual_deductions_to_generated_aave_tokens():
    contracts = {
        "contracts": {
            "WETH": {
                "ethereum": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            }
        }
    }
    metadata = {"metadata": {}}
    taxonomies = {"taxonomies": {}}
    deductions = {
        "deductions": {
            "aWETH": {
                "ethereum": [
                    {
                        "address": "0x62de59c08eb5dae4b7e6f7a8cad3006d6965ec16",
                        "type": "locked",
                    }
                ]
            }
        }
    }
    labels = {
        "labels": {
            "ethereum": {
                "0x62de59c08eb5dae4b7e6f7a8cad3006d6965ec16": {
                    "name": "Kelp DAO LRT Withdrawal Manager",
                    "protocol": "Kelp",
                }
            }
        }
    }
    protocols = [
        {
            "aave_v3": [
                {
                    "token": "WETH",
                    "chain": "ethereum",
                    "address": "0x4d5f47fa6a74757f35c14fd3a6ef8e3c9bc514e8",
                    "decimals": 18,
                    "market": "Core",
                    "name": "Aave V3 Core WETH",
                    "onchain_name": "Aave Ethereum WETH",
                    "onchain_symbol": "aEthWETH",
                    "protocol": "Aave",
                    "symbol": "aWETH",
                    "type": "locked",
                    "underlying_address": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
                    "version": "V3",
                }
            ]
        }
    ]

    result = build_tokens(
        contracts,
        metadata,
        taxonomies,
        deductions,
        labels,
        protocols,
    )

    assert result["tokens"]["aWETH"]["deductions"]["ethereum"] == [
        {
            "address": "0x62de59c08eb5dae4b7e6f7a8cad3006d6965ec16",
            "labels": {
                "name": "Kelp DAO LRT Withdrawal Manager",
                "protocol": "Kelp",
            },
            "type": "locked",
        }
    ]


def test_build_tokens_adds_uniswap_v2_pairs_as_deductions_only():
    contracts = {
        "contracts": {
            "USDC": {
                "ethereum": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            },
            "WETH": {
                "ethereum": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            },
        }
    }
    metadata = {"metadata": {}}
    taxonomies = {"taxonomies": {}}
    deductions = {"deductions": {}}
    labels = {"labels": {}}
    protocols = [
        {
            "uniswap_v2": [
                {
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
                    "type": "locked",
                    "version": "V2",
                }
            ]
        }
    ]

    result = build_tokens(
        contracts,
        metadata,
        taxonomies,
        deductions,
        labels,
        protocols,
    )

    pair_deduction = {
        "address": "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
        "labels": {
            "name": "Uniswap V2 USDC-WETH",
            "pool": "USDC-WETH",
            "protocol": "Uniswap",
            "version": "V2",
        },
        "type": "locked",
    }
    assert result["tokens"]["USDC"]["deductions"]["ethereum"] == [pair_deduction]
    assert result["tokens"]["WETH"]["deductions"]["ethereum"] == [pair_deduction]
    assert "USDC-WETH" not in result["tokens"]


def test_build_tokens_adds_uniswap_v3_pools_as_deductions_only():
    contracts = {
        "contracts": {
            "USDC": {
                "ethereum": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            },
            "WETH": {
                "ethereum": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
            },
        }
    }
    metadata = {"metadata": {}}
    taxonomies = {"taxonomies": {}}
    deductions = {"deductions": {}}
    labels = {"labels": {}}
    protocols = [
        {
            "uniswap_v3": [
                {
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
                    "type": "locked",
                    "version": "V3",
                }
            ]
        }
    ]

    result = build_tokens(
        contracts,
        metadata,
        taxonomies,
        deductions,
        labels,
        protocols,
    )

    pool_deduction = {
        "address": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
        "labels": {
            "name": "Uniswap V3 USDC-WETH",
            "pool": "USDC-WETH",
            "protocol": "Uniswap",
            "version": "V3",
        },
        "type": "locked",
    }
    assert result["tokens"]["USDC"]["deductions"]["ethereum"] == [pool_deduction]
    assert result["tokens"]["WETH"]["deductions"]["ethereum"] == [pool_deduction]
    assert "USDC-WETH-500" not in result["tokens"]
