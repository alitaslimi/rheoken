"""Fluid fToken liquidity deduction discovery.

This script derives generated deductions from Fluid's Lending Factory. For each
configured chain, it calls ``allTokens()`` on the factory, calls ``asset()`` on
each returned fToken, and keeps fTokens whose underlying asset matches a tracked
registry deployment on the same chain. Matching underlyings receive a deduction
for the Fluid Liquidity Contract balance.
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
from rpcs.base import eth_call
from rpcs.base import fetch_metadata

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCES = ROOT / "registries" / "sources"
DEFAULT_CONTRACTS = DEFAULT_SOURCES / "contracts.json"
DEFAULT_CHAINS = DEFAULT_SOURCES / "chains.json"
DEFAULT_OUTPUT = ROOT / "registries" / "protocols" / "fluid_v1.json"
FACTORY_ADDRESS = "0x54b91a0d94cb471f37f949c60f7fa7935b551d03"
LIQUIDITY_CONTRACT = "0x52aa899454998be5b000ad077a46bbe360f4e497"
ALL_TOKENS_SELECTOR = "0x6ff97f1d"
ASSET_SELECTOR = "0x38d52e0f"

FLUID_LENDING_FACTORIES = [
    {
        "chain": chain,
        "address": FACTORY_ADDRESS,
        "liquidity_contract": LIQUIDITY_CONTRACT,
    }
    for chain in ("arbitrum", "base", "bsc", "ethereum", "plasma", "polygon")
]


def load_config() -> dict[str, Any]:
    """Return Fluid Lending Factory source metadata."""
    return {"factories": copy.deepcopy(FLUID_LENDING_FACTORIES)}


def factories(chain: str, config: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Return configured Fluid factories for *chain*."""
    cfg = config or load_config()
    return [
        factory for factory in cfg.get("factories", [])
        if factory.get("chain") == chain
    ]


def discover_fluid_tokens(
    w3: Web3,
    chain: str,
    contracts_registry: dict[str, Any],
    *,
    config: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Derive generated Fluid liquidity deduction records."""
    registry_deployments = tracked_deployments_by_address(chain, contracts_registry)
    if not registry_deployments:
        return []

    generated = []
    metadata_cache: dict[str, dict[str, Any]] = {}
    for factory in factories(chain, config=config):
        for ftoken in get_all_tokens(w3, factory["address"]):
            underlying = get_asset(w3, ftoken)
            if underlying is None:
                continue
            token = registry_deployments.get(underlying)
            if token is None:
                continue

            metadata = metadata_cache.get(ftoken)
            if metadata is None:
                metadata = fetch_ftoken_metadata(w3, ftoken, chain)
                metadata_cache[ftoken] = metadata

            generated.append(build_fluid_record(
                token=token,
                chain=chain,
                underlying=underlying,
                ftoken=ftoken,
                liquidity_contract=factory["liquidity_contract"],
                factory=factory["address"],
                metadata=metadata,
            ))

    return _dedupe_records(generated)


def get_all_tokens(w3: Web3, factory_address: str) -> list[str]:
    """Return all fTokens from a Fluid Lending Factory."""
    try:
        result = eth_call(w3, factory_address, ALL_TOKENS_SELECTOR)
    except RuntimeError as exc:
        if "revert" in str(exc).lower():
            return []
        raise
    return decode_address_array_result(result)


def get_asset(w3: Web3, ftoken_address: str) -> str | None:
    """Return an fToken's underlying asset, or ``None`` when it reverts."""
    try:
        return decode_address_result(eth_call(w3, ftoken_address, ASSET_SELECTOR))
    except RuntimeError as exc:
        if "revert" in str(exc).lower():
            return None
        raise


def decode_address_array_result(result: Any) -> list[str]:
    """Decode an ABI-encoded ``address[]`` return value."""
    if not isinstance(result, str) or not result.startswith("0x"):
        raise RuntimeError(f"invalid address array result: {result}")
    raw = result.removeprefix("0x")
    if not raw:
        return []
    if len(raw) < 128:
        raise RuntimeError(f"invalid address array result: {result}")

    offset = int(raw[:64], 16)
    length_start = offset * 2
    if len(raw) < length_start + 64:
        raise RuntimeError(f"invalid address array result: {result}")
    length = int(raw[length_start:length_start + 64], 16)
    addresses_start = length_start + 64
    addresses_end = addresses_start + length * 64
    if len(raw) < addresses_end:
        raise RuntimeError(f"invalid address array result: {result}")

    addresses = []
    for start in range(addresses_start, addresses_end, 64):
        addresses.append(f"0x{raw[start:start + 64][-40:]}".lower())
    return addresses


def fetch_ftoken_metadata(w3: Web3, ftoken_address: str, chain: str) -> dict[str, Any]:
    """Fetch fToken metadata through Alchemy when available, else ERC-20 calls."""
    rpc_url = getattr(w3.provider, "endpoint_uri", "")
    if ".g.alchemy.com/" in rpc_url:
        try:
            metadata = alchemy_token_metadata(rpc_url, ftoken_address)
            return {
                "address": ftoken_address,
                "decimals": int(metadata["decimals"]),
                "name": metadata.get("name", ""),
                "symbol": metadata.get("symbol", ""),
            }
        except Exception:
            pass

    return fetch_metadata(w3, ftoken_address, chain=chain)


def build_fluid_record(
    *,
    token: str,
    chain: str,
    underlying: str,
    ftoken: str,
    liquidity_contract: str,
    factory: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build a generated Fluid liquidity deduction record."""
    onchain_symbol = metadata.get("symbol", "")
    symbol = onchain_symbol or f"f{token}"
    return {
        "token": token,
        "chain": chain,
        "address": liquidity_contract,
        "underlying_address": underlying,
        "ftoken_address": ftoken,
        "factory": factory,
        "liquidity_contract": liquidity_contract,
        "decimals": int(metadata["decimals"]),
        "symbol": symbol,
        "name": f"Fluid Liquidity Contract {token}",
        "onchain_symbol": onchain_symbol,
        "onchain_name": metadata.get("name", ""),
        "protocol": "Fluid",
        "version": "fToken",
        "type": "locked",
    }


def tracked_deployments_by_address(
    chain: str,
    contracts_registry: dict[str, Any],
) -> dict[str, str]:
    """Return tracked EVM deployment address to token mappings for *chain*."""
    deployments: dict[str, str] = {}
    for token, chains in contracts_registry.get("contracts", {}).items():
        value = chains.get(chain)
        if value is None:
            continue
        addresses = value if isinstance(value, list) else [value]
        for address in addresses:
            if _is_evm_address(address):
                deployments[address.lower()] = token
    return deployments


def write_output(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fluid_v1": records}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_output(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("fluid_v1", [])


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
    parser = argparse.ArgumentParser(description="Discover Fluid fToken deductions.")
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
            chain_records = discover_fluid_tokens(w3, chain, contracts_registry)
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
    print(f"Wrote {len(records)} Fluid fToken record(s) to {args.output}")
    if errors:
        print(f"Skipped {len(errors)} chain(s) with errors:")
        for chain, error in errors:
            print(f"  {chain}: {error}")


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for record in sorted(
        records,
        key=lambda item: (
            item.get("chain", ""),
            item.get("token", "").lower(),
            item.get("ftoken_address", ""),
        ),
    ):
        key = (
            record.get("token"),
            record.get("chain"),
            record.get("address"),
            record.get("underlying_address"),
            record.get("ftoken_address"),
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
