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


def test_build_tokens_ignores_pendle_protocol_until_integrated():
    contracts = {
        "contracts": {
            "USDai": {
                "arbitrum": "0x0a1a1a107e45b7ced86833863f482bc5f4ed82ef",
            }
        }
    }
    metadata = {"metadata": {}}
    taxonomies = {"taxonomies": {}}
    deductions = {"deductions": {}}
    labels = {"labels": {}}
    protocols = [
        {
            "pendle": [
                {
                    "token": "USDai",
                    "chain": "arbitrum",
                    "address": "0x5edcbc20cac67adc2e724d4348ff85132b085b82",
                    "underlying_address": "0x0a1a1a107e45b7ced86833863f482bc5f4ed82ef",
                    "decimals": 18,
                    "symbol": "SY-USDai",
                    "name": "Pendle SY-USDai",
                    "onchain_symbol": "SY-USDai",
                    "onchain_name": "SY USDai",
                    "protocol": "Pendle",
                    "version": "V2",
                    "type": "locked",
                    "expiries": [1763596800],
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

    assert "deductions" not in result["tokens"]["USDai"]


def test_build_tokens_adds_fluid_liquidity_contract_as_deduction_only():
    contracts = {
        "contracts": {
            "USDC": {
                "base": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
            }
        }
    }
    metadata = {"metadata": {}}
    taxonomies = {"taxonomies": {}}
    deductions = {"deductions": {}}
    labels = {"labels": {}}
    protocols = [
        {
            "fluid_v1": [
                {
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

    assert result["tokens"]["USDC"]["deductions"]["base"] == [
        {
            "address": "0x52aa899454998be5b000ad077a46bbe360f4e497",
            "labels": {
                "name": "Fluid Liquidity Contract USDC",
                "protocol": "Fluid",
                "symbol": "fUSDC",
                "version": "fToken",
            },
            "type": "locked",
        }
    ]
    assert "fUSDC" not in result["tokens"]
