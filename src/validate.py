"""Validate the registry artifact files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ROOT / "registries" / "sources"
DEFAULT_ARTIFACTS = ROOT / "registries" / "artifacts"
DEFAULT_REGISTRIES = ROOT / "registries"

REQUIRED_REGISTRY_FILES = {
    "chains.json",
    "contracts.json",
    "deductions.json",
    "labels.json",
    "taxonomies.json",
}
PLAIN_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
ALLOWED_DEDUCTION_TYPES = {"burned", "excluded", "locked"}
NON_EVM_0X_ADDRESS_CHAINS = {
    "aptos",
    "movement",
    "starknet",
    "sui",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_registry(
    sources_dir: Path = DEFAULT_SOURCES,
    registries_dir: Path = DEFAULT_REGISTRIES,
    artifacts_dir: Path = DEFAULT_ARTIFACTS,
) -> list[str]:
    errors: list[str] = []

    registry = _load_registry_files(sources_dir, errors)
    if errors:
        return errors

    chains = registry["chains.json"].get("chains")
    contracts = registry["contracts.json"].get("contracts")
    deductions = registry["deductions.json"].get("deductions")
    labels = registry["labels.json"].get("labels")
    taxonomies = registry["taxonomies.json"].get("taxonomies")

    for name, value in {
        "chains": chains,
        "contracts": contracts,
        "deductions": deductions,
        "labels": labels,
        "taxonomies": taxonomies,
    }.items():
        if not isinstance(value, dict):
            errors.append(f"{name}: must be an object")

    if errors:
        return errors

    chain_ids = set(chains)
    token_ids = set(contracts)
    generated_token_ids = _load_generated_token_ids(registries_dir / "protocols")
    known_deduction_tokens = token_ids | generated_token_ids

    _validate_chains(chains, errors)

    for token, token_contracts in contracts.items():
        if token not in taxonomies:
            errors.append(f"taxonomies: missing token '{token}'")
        if not isinstance(token_contracts, dict):
            errors.append(f"contracts/{token}: must be an object")
            continue
        _validate_chain_map(f"contracts/{token}", token_contracts, chain_ids, errors)
        for chain, addresses in token_contracts.items():
            _validate_addresses(
                f"contracts/{token}/{chain}",
                addresses,
                errors,
                require_plain_evm=_requires_plain_evm_address(chain),
            )

    for token, taxonomy in taxonomies.items():
        if token not in token_ids:
            errors.append(f"taxonomies: unknown token '{token}'")
        if not isinstance(taxonomy, dict):
            errors.append(f"taxonomies/{token}: must be an object")
            continue
        _validate_taxonomy(f"taxonomies/{token}", taxonomy, errors)

    for token, token_deductions in deductions.items():
        if token not in known_deduction_tokens:
            errors.append(f"deductions: unknown token '{token}'")
        if not isinstance(token_deductions, dict):
            errors.append(f"deductions/{token}: must be an object")
            continue
        _validate_chain_map(f"deductions/{token}", token_deductions, chain_ids, errors)
        for chain, entries in token_deductions.items():
            if not isinstance(entries, list):
                errors.append(f"deductions/{token}/{chain}: must be a list")
                continue
            seen: set[str] = set()
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    errors.append(f"deductions/{token}/{chain}[{index}]: must be an object")
                    continue
                address = entry.get("address")
                if not isinstance(address, str) or not address:
                    errors.append(f"deductions/{token}/{chain}[{index}]: missing address")
                    continue
                _validate_address_format(f"deductions/{token}/{chain}[{index}]/address", address, errors)
                if address in seen:
                    errors.append(f"deductions/{token}/{chain}[{index}]: duplicate address '{address}'")
                seen.add(address)
                if entry.get("type") not in ALLOWED_DEDUCTION_TYPES:
                    errors.append(f"deductions/{token}/{chain}[{index}]: invalid type")
                if address not in labels.get(chain, {}):
                    errors.append(f"labels/{chain}: missing deduction address '{address}'")

    for chain, chain_labels in labels.items():
        if chain not in chain_ids:
            errors.append(f"labels: unknown chain '{chain}'")
        if not isinstance(chain_labels, dict):
            errors.append(f"labels/{chain}: must be an object")
            continue
        for address, label in chain_labels.items():
            _validate_address_format(f"labels/{chain}/{address}", address, errors)
            if not isinstance(label, dict):
                errors.append(f"labels/{chain}/{address}: must be an object")
                continue
            if not label.get("name"):
                errors.append(f"labels/{chain}/{address}: missing name")
            if label.get("label"):
                errors.append(f"labels/{chain}/{address}: use 'name', not nested/singular 'label'")

    metadata_path = artifacts_dir / "metadata.json"
    if metadata_path.exists():
        metadata = load_json(metadata_path)
        if not isinstance(metadata, dict) or not isinstance(metadata.get("metadata"), dict):
            errors.append("registries/artifacts/metadata.json: must contain a metadata object")
        else:
            _validate_metadata(metadata["metadata"], token_ids, chain_ids, errors)

    protocols_dir = registries_dir / "protocols"
    if protocols_dir.exists():
        _validate_protocol_outputs(protocols_dir, token_ids, chain_ids, errors)

    tokens_path = registries_dir / "tokens.json"
    if tokens_path.exists():
        _validate_generated_tokens(tokens_path, token_ids, errors)

    return errors


def _load_registry_files(registry_dir: Path, errors: list[str]) -> dict[str, Any]:
    registry: dict[str, Any] = {}
    for name in sorted(REQUIRED_REGISTRY_FILES):
        path = registry_dir / name
        try:
            registry[name] = load_json(path)
        except FileNotFoundError:
            errors.append(f"{name}: missing")
        except json.JSONDecodeError as exc:
            errors.append(f"{name}: invalid JSON ({exc})")
    return registry


def _load_generated_token_ids(protocols_dir: Path) -> set[str]:
    token_ids: set[str] = set()
    if not protocols_dir.exists():
        return token_ids

    for path in sorted(protocols_dir.glob("*.json"), key=lambda item: item.name.lower()):
        try:
            registry = load_json(path)
        except json.JSONDecodeError:
            continue
        if path.stem != "aave_v3":
            continue
        records = registry.get("aave_v3") if isinstance(registry, dict) else None
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, dict) and isinstance(record.get("symbol"), str):
                token_ids.add(record["symbol"])

    return token_ids


def _validate_chain_map(
    path: str,
    chain_map: dict[str, Any],
    known_chains: set[str],
    errors: list[str],
) -> None:
    for chain in chain_map:
        if chain not in known_chains:
            errors.append(f"{path}: unknown chain '{chain}'")


def _validate_chains(chains: dict[str, Any], errors: list[str]) -> None:
    for chain, chain_data in chains.items():
        if not isinstance(chain_data, dict):
            errors.append(f"chains/{chain}: must be an object")
            continue
        if not isinstance(chain_data.get("name"), str) or not chain_data.get("name"):
            errors.append(f"chains/{chain}: missing name")
        if "public_rpcs" in chain_data and not isinstance(chain_data["public_rpcs"], list):
            errors.append(f"chains/{chain}/public_rpcs: must be a list")
        for private_key in ("alchemy_rpc_base", "drpc_network", "rpc_env"):
            if private_key in chain_data:
                errors.append(f"chains/{chain}/{private_key}: provider endpoints belong in src/rpcs, not registry")
        if "chain_id" in chain_data and not isinstance(chain_data["chain_id"], int):
            errors.append(f"chains/{chain}/chain_id: must be an integer")


def _validate_addresses(
    path: str,
    addresses: Any,
    errors: list[str],
    *,
    require_plain_evm: bool = False,
) -> None:
    if isinstance(addresses, str):
        if not addresses:
            errors.append(f"{path}: address cannot be empty")
        _validate_address_format(path, addresses, errors, require_plain_evm=require_plain_evm)
        return

    if not isinstance(addresses, list):
        errors.append(f"{path}: address value must be a string or list")
        return

    seen: set[str] = set()
    for index, address in enumerate(addresses):
        if not isinstance(address, str) or not address:
            errors.append(f"{path}[{index}]: address must be a non-empty string")
            continue
        _validate_address_format(
            f"{path}[{index}]",
            address,
            errors,
            require_plain_evm=require_plain_evm,
        )
        if address in seen:
            errors.append(f"{path}[{index}]: duplicate address '{address}'")
        seen.add(address)


def _requires_plain_evm_address(chain: str) -> bool:
    return chain not in NON_EVM_0X_ADDRESS_CHAINS | {"solana", "stellar", "ton", "tron"}


def _validate_address_format(
    path: str,
    address: str,
    errors: list[str],
    *,
    require_plain_evm: bool = False,
) -> None:
    if address.startswith("0X"):
        errors.append(f"{path}: plain EVM address must use lowercase '0x'")
        return
    if require_plain_evm and (not address.startswith("0x") or "::" in address):
        errors.append(f"{path}: plain EVM address must be lowercase 0x plus 40 hex characters")
        return
    if require_plain_evm and not PLAIN_EVM_ADDRESS_RE.match(address):
        errors.append(f"{path}: plain EVM address must be lowercase 0x plus 40 hex characters")
        return
    if not address.startswith("0x") or "::" in address or len(address) != 42:
        return
    if not PLAIN_EVM_ADDRESS_RE.match(address):
        errors.append(f"{path}: plain EVM address must be lowercase 0x plus 40 hex characters")


def _validate_taxonomy(path: str, taxonomy: dict[str, Any], errors: list[str]) -> None:
    prices = taxonomy.get("prices")
    if prices is not None:
        if not isinstance(prices, dict):
            errors.append(f"{path}/prices: must be an object")
        elif "coingecko_id" in prices and not isinstance(prices["coingecko_id"], str):
            errors.append(f"{path}/prices/coingecko_id: must be a string")

    for key, value in taxonomy.items():
        if key == "prices":
            continue
        if not isinstance(value, str):
            errors.append(f"{path}/{key}: must be a string")
            continue
        if value != value.strip():
            errors.append(f"{path}/{key}: value has leading or trailing whitespace")


def _validate_metadata(
    metadata: dict[str, Any],
    known_tokens: set[str],
    known_chains: set[str],
    errors: list[str],
) -> None:
    for token, token_metadata in metadata.items():
        if token not in known_tokens:
            errors.append(f"registries/artifacts/metadata.json: unknown token '{token}'")
        if not isinstance(token_metadata, dict):
            errors.append(f"registries/artifacts/metadata.json/{token}: must be an object")
            continue
        for chain, chain_metadata in token_metadata.items():
            if chain not in known_chains:
                errors.append(f"registries/artifacts/metadata.json/{token}: unknown chain '{chain}'")
            if not isinstance(chain_metadata, dict):
                errors.append(f"registries/artifacts/metadata.json/{token}/{chain}: must be an object")
                continue
            for address, item in chain_metadata.items():
                _validate_address_format(f"registries/artifacts/metadata.json/{token}/{chain}/{address}", address, errors)
                if not isinstance(item, dict):
                    errors.append(f"registries/artifacts/metadata.json/{token}/{chain}/{address}: must be an object")
                    continue
                for key in ("name", "symbol"):
                    if key in item and not isinstance(item[key], str):
                        errors.append(f"registries/artifacts/metadata.json/{token}/{chain}/{address}/{key}: must be a string")
                if "decimals" in item and not isinstance(item["decimals"], int):
                    errors.append(f"registries/artifacts/metadata.json/{token}/{chain}/{address}/decimals: must be an integer")


def _validate_protocol_outputs(
    protocols_dir: Path,
    known_tokens: set[str],
    known_chains: set[str],
    errors: list[str],
) -> None:
    for path in sorted(protocols_dir.glob("*.json"), key=lambda item: item.name.lower()):
        try:
            registry = load_json(path)
        except json.JSONDecodeError as exc:
            errors.append(f"registries/protocols/{path.name}: invalid JSON ({exc})")
            continue
        protocol = path.stem
        if not isinstance(registry, dict) or set(registry) != {protocol}:
            errors.append(f"registries/protocols/{path.name}: must contain only a '{protocol}' key")
            continue
        records = registry[protocol]
        if not isinstance(records, list):
            errors.append(f"registries/protocols/{path.name}/{protocol}: must be a list")
            continue
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                errors.append(f"registries/protocols/{path.name}/{protocol}[{index}]: must be an object")
                continue
            _validate_protocol_record(protocol, index, record, known_tokens, known_chains, errors)


def _validate_protocol_record(
    protocol: str,
    index: int,
    record: dict[str, Any],
    known_tokens: set[str],
    known_chains: set[str],
    errors: list[str],
) -> None:
    path = f"registries/protocols/{protocol}[{index}]"
    forbidden_keys = {"generated_by", "label", "labels"}
    for key in forbidden_keys & set(record):
        errors.append(f"{path}: unexpected key '{key}'")

    required = {"address", "chain", "name", "protocol", "symbol", "type"}
    if protocol == "aave_v3":
        required |= {"decimals", "market", "onchain_name", "onchain_symbol", "token", "underlying_address", "version"}
    elif protocol == "uniswap_v2":
        required |= {"decimals", "onchain_name", "onchain_symbol", "pool", "tokens", "underlying_addresses", "version"}
    elif protocol == "uniswap_v3":
        required |= {"fee", "onchain_name", "pool", "tokens", "underlying_addresses", "version"}

    for key in sorted(required - set(record)):
        errors.append(f"{path}: missing {key}")

    chain = record.get("chain")
    if chain not in known_chains:
        errors.append(f"{path}: unknown chain '{chain}'")
    address = record.get("address")
    if isinstance(address, str):
        _validate_address_format(f"{path}/address", address, errors)
    else:
        errors.append(f"{path}/address: must be a string")
    if record.get("type") not in ALLOWED_DEDUCTION_TYPES:
        errors.append(f"{path}/type: invalid type")

    if protocol == "aave_v3":
        token = record.get("token")
        if token not in known_tokens:
            errors.append(f"{path}: unknown token '{token}'")
        if not isinstance(record.get("decimals"), int):
            errors.append(f"{path}/decimals: must be an integer")
        underlying_address = record.get("underlying_address")
        if isinstance(underlying_address, str):
            _validate_address_format(f"{path}/underlying_address", underlying_address, errors)
    elif protocol in {"uniswap_v2", "uniswap_v3"}:
        tokens = record.get("tokens")
        if not isinstance(tokens, list) or len(tokens) != 2:
            errors.append(f"{path}/tokens: must be a two-item list")
        else:
            for token in tokens:
                if token not in known_tokens:
                    errors.append(f"{path}: unknown token '{token}'")
        underlying_addresses = record.get("underlying_addresses")
        if not isinstance(underlying_addresses, dict):
            errors.append(f"{path}/underlying_addresses: must be an object")
        elif isinstance(tokens, list) and set(underlying_addresses) != set(tokens):
            errors.append(f"{path}/underlying_addresses: must match tokens")
        if protocol == "uniswap_v3" and not isinstance(record.get("fee"), int):
            errors.append(f"{path}/fee: must be an integer")


def _validate_generated_tokens(tokens_path: Path, manual_tokens: set[str], errors: list[str]) -> None:
    try:
        registry = load_json(tokens_path)
    except json.JSONDecodeError as exc:
        errors.append(f"registries/tokens.json: invalid JSON ({exc})")
        return
    tokens = registry.get("tokens") if isinstance(registry, dict) else None
    if not isinstance(tokens, dict):
        errors.append("registries/tokens.json: must contain a tokens object")
        return

    missing = manual_tokens - set(tokens)
    for token in sorted(missing, key=str.lower):
        errors.append(f"registries/tokens.json: missing manual token '{token}'")

    for token, item in tokens.items():
        if not isinstance(item, dict):
            errors.append(f"registries/tokens.json/{token}: must be an object")
            continue
        deployments = item.get("deployments")
        if not isinstance(deployments, dict):
            errors.append(f"registries/tokens.json/{token}/deployments: must be an object")
        else:
            for chain, chain_deployments in deployments.items():
                if not isinstance(chain_deployments, list):
                    errors.append(f"registries/tokens.json/{token}/deployments/{chain}: must be a list")
                    continue
                for index, deployment in enumerate(chain_deployments):
                    if not isinstance(deployment, dict):
                        errors.append(f"registries/tokens.json/{token}/deployments/{chain}[{index}]: must be an object")
                        continue
                    address = deployment.get("address")
                    if isinstance(address, str):
                        _validate_address_format(
                            f"registries/tokens.json/{token}/deployments/{chain}[{index}]/address",
                            address,
                            errors,
                        )
                    else:
                        errors.append(f"registries/tokens.json/{token}/deployments/{chain}[{index}]: missing address")

        deductions = item.get("deductions", {})
        if deductions and not isinstance(deductions, dict):
            errors.append(f"registries/tokens.json/{token}/deductions: must be an object")
            continue
        for chain, entries in deductions.items():
            if not isinstance(entries, list):
                errors.append(f"registries/tokens.json/{token}/deductions/{chain}: must be a list")
                continue
            for index, deduction in enumerate(entries):
                if not isinstance(deduction, dict):
                    errors.append(f"registries/tokens.json/{token}/deductions/{chain}[{index}]: must be an object")
                    continue
                if "label" in deduction:
                    errors.append(f"registries/tokens.json/{token}/deductions/{chain}[{index}]: use 'labels', not 'label'")
                if deduction.get("type") not in ALLOWED_DEDUCTION_TYPES:
                    errors.append(f"registries/tokens.json/{token}/deductions/{chain}[{index}]: invalid type")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate registry JSON files.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--registries", type=Path, default=DEFAULT_REGISTRIES)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    args = parser.parse_args()

    errors = validate_registry(args.sources, args.registries, args.artifacts)
    if errors:
        for error in errors:
            print(error)
        sys.exit(1)

    print("OK")


if __name__ == "__main__":
    main()
