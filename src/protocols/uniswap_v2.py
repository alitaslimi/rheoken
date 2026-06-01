"""Uniswap V2 pair discovery.

This script derives generated LP token deductions from Uniswap V2 Factory
state. For each same-chain pair of tracked token deployments in
``registries/sources/contracts.json``, it asks the matching factory for
``getPair(tokenA, tokenB)``. Existing pairs become generated deductions for
both underlying assets and standalone generated LP token entries.
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
DEFAULT_OUTPUT = ROOT / "registries" / "protocols" / "uniswap_v2.json"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
GET_PAIR_SELECTOR = "0xe6a43905"

UNISWAP_V2_FACTORIES = [
    {"chain": "arbitrum", "address": "0xf1d7cc64fb4452f05c498126312ebe29f30fbcf9"},
    {"chain": "avalanche", "address": "0x9e5a52f57b3038f1b8eee45f28b3c1967e22799c"},
    {"chain": "base", "address": "0x8909dc15e40173ff4699343b6eb8132c65e18ec6"},
    {"chain": "blast", "address": "0x5c346464d33f90babaf70db6388507cc889c1070"},
    {"chain": "bsc", "address": "0x8909dc15e40173ff4699343b6eb8132c65e18ec6"},
    {"chain": "ethereum", "address": "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f"},
    {"chain": "megaeth", "address": "0xbf56488c857a881ae7e3bed27cf99c10a7ab7e50"},
    {"chain": "monad", "address": "0x182a927119d56008d921126764bf884221b10f59"},
    {"chain": "optimism", "address": "0x0c3c1c532f1e39edf36be9fe0be1410313e074bf"},
    {"chain": "polygon", "address": "0x9e5a52f57b3038f1b8eee45f28b3c1967e22799c"},
    {"chain": "unichain", "address": "0x1f98400000000000000000000000000000000002"},
    {"chain": "worldchain", "address": "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f"},
    {"chain": "zora", "address": "0x0f797dc7efaea995bb916f268d919d0a1950ee3c"},
]


def load_config() -> dict[str, Any]:
    """Return Uniswap V2 Factory source metadata."""
    return {"factories": copy.deepcopy(UNISWAP_V2_FACTORIES)}


def factories(chain: str, config: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Return configured Uniswap V2 factories for *chain*."""
    cfg = config or load_config()
    return [
        factory for factory in cfg.get("factories", [])
        if factory.get("chain") == chain
    ]


def discover_pairs(
    w3: Web3,
    chain: str,
    contracts_registry: dict[str, Any],
    *,
    config: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Derive generated LP token records from Uniswap V2 Factory state."""
    generated = []
    metadata_cache: dict[str, dict[str, Any]] = {}
    deployments = tracked_deployments(chain, contracts_registry)
    for factory_config in factories(chain, config=config):
        for token_a, address_a, token_b, address_b in pair_candidates(deployments):
            pair = get_pair(w3, factory_config["address"], address_a, address_b)
            if pair is None:
                continue

            metadata = metadata_cache.get(pair)
            if metadata is None:
                metadata = fetch_pair_metadata(w3, pair, chain)
                metadata_cache[pair] = metadata

            generated.append(build_pair_record(
                token_a=token_a,
                address_a=address_a,
                token_b=token_b,
                address_b=address_b,
                chain=chain,
                pair=pair,
                metadata=metadata,
            ))

    return _dedupe_records(generated)


def get_pair(w3: Web3, factory_address: str, token_a: str, token_b: str) -> str | None:
    """Return the LP pair address, or ``None`` when no pair exists."""
    pair = _get_pair_once(w3, factory_address, token_a, token_b)
    if pair is not None:
        return pair
    return _get_pair_once(w3, factory_address, token_b, token_a)


def _get_pair_once(w3: Web3, factory_address: str, token_a: str, token_b: str) -> str | None:
    try:
        result = eth_call(
            w3,
            factory_address,
            f"{GET_PAIR_SELECTOR}{encode_abi_address(token_a)}{encode_abi_address(token_b)}",
        )
    except RuntimeError as exc:
        if "revert" in str(exc).lower():
            return None
        raise
    normalized = decode_address_result(result)
    if normalized == ZERO_ADDRESS:
        return None
    return normalized


def fetch_pair_metadata(w3: Web3, pair: str, chain: str) -> dict[str, Any]:
    """Fetch LP pair metadata through Alchemy when available, else ERC-20 calls."""
    rpc_url = getattr(w3.provider, "endpoint_uri", "")
    if ".g.alchemy.com/" in rpc_url:
        try:
            metadata = alchemy_token_metadata(rpc_url, pair)
            return {
                "address": pair,
                "decimals": int(metadata["decimals"]),
                "name": metadata.get("name", ""),
                "symbol": metadata.get("symbol", ""),
            }
        except Exception:
            pass

    return fetch_metadata(w3, pair, chain=chain)


def build_pair_record(
    *,
    token_a: str,
    address_a: str,
    token_b: str,
    address_b: str,
    chain: str,
    pair: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    token0, address0, token1, address1 = ordered_underlyings(
        token_a,
        address_a,
        token_b,
        address_b,
    )
    symbol = f"{token0}-{token1}"
    version = "V2"
    return {
        "tokens": [token0, token1],
        "chain": chain,
        "address": pair,
        "underlying_addresses": {
            token0: address0,
            token1: address1,
        },
        "decimals": int(metadata["decimals"]),
        "pool": symbol,
        "symbol": symbol,
        "name": f"Uniswap {version} {symbol}",
        "onchain_symbol": metadata.get("symbol", ""),
        "onchain_name": metadata.get("name", ""),
        "protocol": "Uniswap",
        "version": version,
        "type": "locked",
    }


def ordered_underlyings(
    token_a: str,
    address_a: str,
    token_b: str,
    address_b: str,
) -> tuple[str, str, str, str]:
    """Return underlyings in Uniswap V2 token0/token1 address order."""
    if int(address_a, 16) <= int(address_b, 16):
        return token_a, address_a, token_b, address_b
    return token_b, address_b, token_a, address_a


def tracked_deployments(chain: str, contracts_registry: dict[str, Any]) -> list[tuple[str, str]]:
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
    return sorted(deployments, key=lambda item: (item[0].lower(), item[1].lower()))


def pair_candidates(deployments: list[tuple[str, str]]) -> list[tuple[str, str, str, str]]:
    """Return unique cross-token pair candidates from tracked deployments."""
    candidates = []
    for index, (token_a, address_a) in enumerate(deployments):
        for token_b, address_b in deployments[index + 1:]:
            if token_a == token_b:
                continue
            candidates.append((token_a, address_a, token_b, address_b))
    return candidates


def write_output(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"uniswap_v2": records}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_output(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("uniswap_v2", [])


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
    parser = argparse.ArgumentParser(description="Discover Uniswap V2 pairs.")
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
    configured_chains = sorted({factory["chain"] for factory in load_config()["factories"]})
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
            chain_records = discover_pairs(w3, chain, contracts_registry)
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
    print(f"Wrote {len(records)} Uniswap V2 pair record(s) to {args.output}")
    if errors:
        print(f"Skipped {len(errors)} chain(s) with errors:")
        for chain, error in errors:
            print(f"  {chain}: {error}")


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for record in records:
        key = (
            record.get("chain"),
            record.get("address"),
            tuple(record.get("tokens", [])),
            tuple(record.get("underlying_addresses", {}).values()),
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
