# Rheoken

Open-source token registry for [rheoken.com](https://rheoken.com). This repo
contains manual registry inputs, reproducible metadata/protocol scripts, cached
script artifacts, and the published `registries/tokens.json` registry.

For contribution steps, see [CONTRIBUTION.md](CONTRIBUTION.md).

## Repository Layout

```text
registries/
  tokens.json              Published registry artifact

  sources/                 Manual source-of-truth inputs
    chains.json
    contracts.json
    deductions.json
    labels.json
    taxonomies.json

  artifacts/               Script-refreshed metadata cache
    metadata.json

  protocols/               Script-refreshed protocol discovery outputs
    aave_v3.json
    uniswap_v2.json
    uniswap_v3.json

src/
  build_tokens.py          Builds registries/tokens.json
  fetch_metadata.py        Refreshes registries/artifacts/metadata.json
  validate.py              Validates registry files
  protocols/               Protocol discovery scripts
  rpcs/                    RPC provider helpers

tests/                     Registry, RPC, metadata, and protocol tests
```

Build flow:

```text
manual sources + metadata artifact + protocol artifacts -> registries/tokens.json
```

Most consumers should read:

```text
registries/tokens.json
registries/sources/chains.json
```

## Setup

```bash
uv sync
```

Requires Python 3.10+.

Copy `.env.example` to `.env` if you need private RPC providers:

```text
ALCHEMY_API_KEY=
DRPC_API_KEY=
```

`COINGECKO_API_KEY` is not used here. CoinGecko IDs are stored as public
metadata in `registries/sources/taxonomies.json`.

## File Lifecycle

| File | Purpose |
| --- | --- |
| `registries/sources/chains.json` | Supported chains and public RPC fallbacks. |
| `registries/sources/contracts.json` | Root token deployments. |
| `registries/sources/taxonomies.json` | Token categories, issuers, denominations, backing, and CoinGecko IDs. |
| `registries/sources/deductions.json` | Manual free-float deduction holders. |
| `registries/sources/labels.json` | Shared labels for manual deduction holders. |
| `registries/artifacts/metadata.json` | ERC-20 symbol, name, and decimals cache created by `src/fetch_metadata.py`. |
| `registries/protocols/*.json` | Aave and Uniswap protocol discovery outputs created by `src/protocols/*.py`. |
| `registries/tokens.json` | Final published registry created by `src/build_tokens.py`. |

## Common Commands

Refresh metadata:

```bash
uv run python src/fetch_metadata.py --tokens USDC,USDT
uv run python src/fetch_metadata.py --chains ethereum,arbitrum
uv run python src/fetch_metadata.py --refresh
```

Refresh protocol artifacts:

```bash
uv run python src/protocols/aave_v3.py
uv run python src/protocols/uniswap_v2.py
uv run python src/protocols/uniswap_v3.py
```

Build and check the registry:

```bash
uv run python src/build_tokens.py
uv run python src/validate.py
uv run pytest -q -p no:cacheprovider
uv run ruff check . --no-cache
```

## Registry Rules

Addresses:

- Plain EVM addresses must be lowercase.
- Non-EVM addresses keep their chain-native format and casing.
- Use a string for one deployment and a list for multiple deployments.
- Every manual deduction address must have a matching label.

Taxonomies:

- Current categories are `Commodity`, `Governance`, `Liquid Restaking`,
  `Liquid Staking`, `Native`, `Stablecoin`, `Staked`, `Wrapped`, and
  `Yield Bearing`.
- Use `denomination` only for useful exposure buckets like `USD`, `EUR`, `XAU`,
  `ETH`, `BTC`, `AVAX`, `SOL`, or `BNB`.
- Use `backing` only for stablecoins and commodities. Valid current values are
  `Fiat`, `Crypto`, `Synthetic`, and `Commodity`.
- Omit `prices.coingecko_id` when no CoinGecko ID is known.

Deductions:

- `locked`: protocol contracts, bridges, escrow, vesting, and similar holders.
- `excluded`: issuer treasury-style balances outside circulating float.
- `burned`: burn addresses only.

Protocol artifacts:

- Aave V3 aTokens are generated root tokens and deductions.
- Uniswap V2 pairs and Uniswap V3 pools are deduction-only.

## Out Of Scope

This repo should not contain production ingestion, database migrations,
historical backfills, price jobs, metric aggregation, API code, frontend code,
or private credentials. Those systems should consume this repo at a pinned git
SHA or release tag.
