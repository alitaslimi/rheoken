# Contribution

Thanks for helping improve Rheoken's registry. This repo is meant to be easy to
review: humans edit source files, scripts refresh derived artifacts, and CI
checks the result.

## What To Edit

Manual inputs live in `registries/sources/`:

| File | Purpose |
| --- | --- |
| `chains.json` | Chain slugs, names, chain IDs, native assets, and public RPC fallbacks. |
| `contracts.json` | Root token deployments by token and chain. |
| `taxonomies.json` | Token category, issuer, denomination, backing, and CoinGecko IDs. |
| `deductions.json` | Reviewed holder addresses that reduce free float. |
| `labels.json` | Shared labels for manual deduction addresses. |

Do not hand-edit these unless you are intentionally refreshing generated data:

| File | Created by |
| --- | --- |
| `registries/artifacts/metadata.json` | `src/fetch_metadata.py` |
| `registries/protocols/*.json` | `src/protocols/*.py` |
| `registries/tokens.json` | `src/build_tokens.py` |

## Workflow

1. Fork the repo and create a branch.
2. Edit the relevant files in `registries/sources/`.
3. Refresh metadata or protocol artifacts if needed.
4. Rebuild `registries/tokens.json`.
5. Run validation, tests, and lint.
6. Open a pull request.

```bash
uv sync
uv run python src/build_tokens.py
uv run python src/validate.py
uv run pytest -q -p no:cacheprovider
uv run ruff check . --no-cache
```

CI runs on pushes and pull requests to `main`.

## Adding A Token

1. Add deployments to `registries/sources/contracts.json`.
2. Add taxonomy metadata to `registries/sources/taxonomies.json`.
3. Add deductions and matching labels only when holder balances should reduce
   free float.
4. Refresh EVM metadata for the changed token:

```bash
uv run python src/fetch_metadata.py --tokens TOKEN
```

5. Rebuild and validate:

```bash
uv run python src/build_tokens.py
uv run python src/validate.py
uv run pytest -q -p no:cacheprovider
uv run ruff check . --no-cache
```

## Address Rules

- Plain EVM addresses must be lowercase.
- Non-EVM addresses should keep their chain-native format and casing.
- Use a string for one deployment on a chain.
- Use a list for multiple deployments on the same chain.
- Every manual deduction address must have a matching label for the same chain.

## Taxonomy Rules

Current categories:

```text
Commodity
Governance
Liquid Restaking
Liquid Staking
Native
Stablecoin
Staked
Wrapped
Yield Bearing
```

Use `denomination` only when it describes a useful exposure bucket, such as
`USD`, `EUR`, `XAU`, `ETH`, `BTC`, `AVAX`, `SOL`, or `BNB`. Do not use it when
it only repeats a governance or plain staked token's own symbol.

Use `backing` only for stablecoins and commodities. Keep it categorical:

```text
Fiat
Crypto
Synthetic
Commodity
```

Omit `backing` for yield-bearing, wrapped, staked, governance, liquid staking,
liquid restaking, and native tokens.

Use `prices.coingecko_id` only when the CoinGecko ID is known. Omit the key when
there is no ID.

## Deduction Rules

Allowed deduction types:

| Type | Meaning |
| --- | --- |
| `locked` | Protocol contracts, bridges, escrow, vesting, and similar locked holders. |
| `excluded` | Issuer treasury-style balances outside the circulating float methodology. |
| `burned` | Burn addresses only. |

The EVM null address is handled as the default burned-address baseline. Add
dead/max burn addresses only when there is a token-specific reason.

## Protocol Artifacts

Protocol scripts live in `src/protocols/` and write committed review artifacts
under `registries/protocols/`.

```bash
uv run python src/protocols/aave_v3.py
uv run python src/protocols/uniswap_v2.py
uv run python src/protocols/uniswap_v3.py
uv run python src/build_tokens.py
```

Aave V3 aTokens are included as generated root tokens and as deductions against
their underlyings. Uniswap V2 pairs and Uniswap V3 pools are deduction-only.

## Using The Registry

Do not fork this repo just to add database integrations, backfills, pricing,
metrics, or scheduled jobs. Keep those in a separate app or data repo and pin
this repo at a commit SHA or release tag.

Production ingestion should record the registry version it used:

```text
registry_repo
registry_commit_sha
registry_tokens_path
started_at
completed_at
status
```
