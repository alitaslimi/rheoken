"""Aave V3 protocol discovery.

This script derives generated aToken deductions from Aave Pool state. For each
tracked token deployment in ``registries/sources/contracts.json``, it asks the matching
Aave Pool for ``getReserveAToken(asset)``. Existing reserves become generated
deductions for their underlying asset.
"""

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Optional

from web3 import Web3

from fetch_metadata import _load_env_file, _safe_error
from rpcs.alchemy import token_metadata as alchemy_token_metadata
from rpcs.base import connect as connect_rpc
from rpcs.base import decode_address_result
from rpcs.base import encode_abi_address
from rpcs.base import eth_call
from rpcs.base import fetch_metadata

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCES = ROOT / "registries" / "sources"
DEFAULT_CONTRACTS = DEFAULT_SOURCES / "contracts.json"
DEFAULT_CHAINS = DEFAULT_SOURCES / "chains.json"
DEFAULT_OUTPUT = ROOT / "registries" / "protocols" / "aave_v3.json"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
GET_RESERVE_ATOKEN_SELECTOR = "0xcff027d9"

AAVE_V3_POOLS = [
    {"chain": "arbitrum", "address": "0x794a61358d6845594f94dc1db02a252b5b4814ad", "market": "Arbitrum"},
    {"chain": "avalanche", "address": "0x794a61358d6845594f94dc1db02a252b5b4814ad", "market": "Avalanche"},
    {"chain": "base", "address": "0xa238dd80c259a72e81d7e4664a9801593f98d1c5", "market": "Base"},
    {"chain": "bsc", "address": "0x6807dc923806fe8fd134338eabca509979a7e0cb", "market": "BNB Chain"},
    {"chain": "celo", "address": "0x3e59a31363e2ad014dcbc521c4a0d5757d9f3402", "market": "Celo"},
    {"chain": "ethereum", "address": "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2", "market": "Core"},
    {"chain": "ethereum", "address": "0x4e033931ad43597d96d6bcc25c280717730b58b1", "market": "Prime"},
    {"chain": "ethereum", "address": "0x0aa97c284e98396202b6a04024f5e2c65026f3c0", "market": "EtherFi"},
    {"chain": "ethereum", "address": "0xae05cd22df81871bc7cc2a04becfb516bfe332c8", "market": "Horizon"},
    {"chain": "gnosis", "address": "0xb50201558b00496a145fe76f7424749556e326d8", "market": "Gnosis"},
    {"chain": "linea", "address": "0xc47b8c00b0f69a36fa203ffeac0334874574a8ac", "market": "Linea"},
    {"chain": "optimism", "address": "0x794a61358d6845594f94dc1db02a252b5b4814ad", "market": "OP"},
    {"chain": "plasma", "address": "0x2b16e93bdb1897f517881b3c388babd0c62c6cdc", "market": "Plasma"},
    {"chain": "polygon", "address": "0x794a61358d6845594f94dc1db02a252b5b4814ad", "market": "Polygon"},
    {"chain": "scroll", "address": "0x11fcfe756c05ad438e312a7fd934381537d3cffe", "market": "Scroll"},
    {"chain": "sonic", "address": "0x5362dbb1e601abf3a4c14c22ffeda64042e5eaa3", "market": "Sonic"},
    {"chain": "zksync", "address": "0x78e30497a3c7527d953c6b1e3541b021a98ac43c", "market": "ZKsync"},
]


def load_config() -> dict:
    """Return Aave V3 Pool source metadata."""
    return {"pools": copy.deepcopy(AAVE_V3_POOLS)}


def markets(chain: str, config: Optional[dict] = None) -> list[dict]:
    """Return configured Aave V3 markets for *chain*."""
    cfg = config or load_config()
    return [
        market for market in cfg.get("pools", [])
        if market.get("chain") == chain
    ]


def discover_atokens(
    w3: Web3,
    chain: str,
    contracts_registry: dict,
    *,
    config: Optional[dict] = None,
) -> list[dict]:
    """
    Derive generated aToken records from Aave Pool state.

    This is intentionally current-state based: if Aave has a reserve for a
    tracked underlying deployment, ``getReserveAToken`` returns the active
    aToken address. Missing reserves are ignored.
    """
    generated = []
    metadata_cache: dict[str, dict[str, Any]] = {}
    for market in markets(chain, config=config):
        for token, underlying in tracked_deployments(chain, contracts_registry):
            atoken = get_reserve_atoken(w3, market["address"], underlying)
            if atoken is None:
                continue

            metadata = metadata_cache.get(atoken)
            if metadata is None:
                metadata = fetch_atoken_metadata(w3, atoken, chain)
                metadata_cache[atoken] = metadata

            generated.append(build_atoken_record(
                token=token,
                chain=chain,
                underlying=underlying,
                atoken=atoken,
                metadata=metadata,
                market=market["market"],
            ))

    return _dedupe_records(generated)


def get_reserve_atoken(w3: Web3, pool_address: str, underlying: str) -> str | None:
    """Return the reserve aToken address, or ``None`` when no reserve exists."""
    try:
        result = eth_call(
            w3,
            pool_address,
            f"{GET_RESERVE_ATOKEN_SELECTOR}{encode_abi_address(underlying)}",
        )
    except RuntimeError as exc:
        if "revert" in str(exc).lower():
            return None
        raise

    normalized = decode_address_result(result)
    if normalized == ZERO_ADDRESS:
        return None
    return normalized


def fetch_atoken_metadata(w3: Web3, atoken: str, chain: str) -> dict[str, Any]:
    """Fetch aToken metadata through Alchemy when available, else ERC-20 calls."""
    rpc_url = getattr(w3.provider, "endpoint_uri", "")
    if ".g.alchemy.com/" in rpc_url:
        try:
            metadata = alchemy_token_metadata(rpc_url, atoken)
            return {
                "address": atoken,
                "decimals": int(metadata["decimals"]),
                "name": metadata.get("name", ""),
                "symbol": metadata.get("symbol", ""),
            }
        except Exception:
            pass

    return fetch_metadata(w3, atoken, chain=chain)


def build_atoken_record(
    *,
    token: str,
    chain: str,
    underlying: str,
    atoken: str,
    metadata: dict[str, Any],
    market: str,
) -> dict[str, Any]:
    symbol = f"a{token}"
    version = "V3"
    return {
        "token": token,
        "chain": chain,
        "address": atoken,
        "underlying_address": underlying,
        "decimals": int(metadata["decimals"]),
        "symbol": symbol,
        "name": f"Aave {version} {market} {token}",
        "onchain_symbol": metadata.get("symbol", ""),
        "onchain_name": metadata.get("name", ""),
        "protocol": "Aave",
        "market": market,
        "version": version,
        "type": "locked",
    }


def tracked_deployments(chain: str, contracts_registry: dict) -> list[tuple[str, str]]:
    """Return tracked EVM ``(token, address)`` deployments for *chain*."""
    deployments = []
    for token, chains in contracts_registry.get("contracts", {}).items():
        value = chains.get(chain)
        if value is None:
            continue
        addresses = value if isinstance(value, list) else [value]
        for address in addresses:
            if _is_evm_address(address):
                deployments.append((token, address.lower()))
    return deployments


def write_output(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"aave_v3": records}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_output(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("aave_v3", [])


def merge_output_records(
    existing: list[dict[str, Any]],
    refreshed: list[dict[str, Any]],
    refreshed_chains: set[str],
) -> list[dict[str, Any]]:
    records = [
        record
        for record in existing
        if record.get("chain") not in refreshed_chains
    ]
    records.extend(refreshed)
    return _dedupe_records(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover Aave V3 aTokens.")
    parser.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACTS)
    parser.add_argument("--chains-file", type=Path, default=DEFAULT_CHAINS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--chains", help="Comma-separated chains to refresh.")
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()

    _load_env_file(args.env_file)
    contracts_registry = json.loads(args.contracts.read_text(encoding="utf-8"))
    chains_registry = json.loads(args.chains_file.read_text(encoding="utf-8"))
    chain_filter = {item.strip() for item in args.chains.split(",")} if args.chains else None
    configured_chains = sorted({market["chain"] for market in load_config()["pools"]})
    if chain_filter is not None:
        configured_chains = [chain for chain in configured_chains if chain in chain_filter]

    records = []
    errors = []
    successful_chains = set()
    for chain in configured_chains:
        if chain not in chains_registry["chains"]:
            errors.append((chain, "chain not in registry"))
            continue
        try:
            w3 = connect_rpc(chain, chains_registry["chains"][chain], timeout=args.timeout)
            chain_records = discover_atokens(w3, chain, contracts_registry)
            records.extend(chain_records)
            successful_chains.add(chain)
        except Exception as exc:
            errors.append((chain, _safe_error(exc)))

    records = merge_output_records(
        read_output(args.output),
        _dedupe_records(records),
        successful_chains,
    )
    write_output(args.output, records)
    print(f"Wrote {len(records)} Aave V3 aToken record(s) to {args.output}")
    if errors:
        print(f"Skipped {len(errors)} chain(s) with errors:")
        for chain, error in errors:
            print(f"  {chain}: {error}")

def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for record in records:
        key = (
            record.get("token"),
            record.get("chain"),
            record.get("address"),
            record.get("underlying_address"),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def _is_evm_address(address: Any) -> bool:
    return isinstance(address, str) and Web3.is_address(address)


if __name__ == "__main__":
    main()
