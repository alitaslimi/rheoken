"""Build the unified token registry artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = ROOT / "registries" / "artifacts"
DEFAULT_SOURCES = ROOT / "registries" / "sources"
DEFAULT_CONTRACTS = DEFAULT_SOURCES / "contracts.json"
DEFAULT_TAXONOMIES = DEFAULT_SOURCES / "taxonomies.json"
DEFAULT_DEDUCTIONS = DEFAULT_SOURCES / "deductions.json"
DEFAULT_LABELS = DEFAULT_SOURCES / "labels.json"
DEFAULT_METADATA = DEFAULT_ARTIFACTS / "metadata.json"
DEFAULT_PROTOCOLS_DIR = ROOT / "registries" / "protocols"
DEFAULT_OUTPUT = ROOT / "registries" / "tokens.json"
TOKEN_ENTRY_KEY_ORDER = {
    "taxonomies": 0,
    "deployments": 1,
    "deductions": 2,
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sort_json(data), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_tokens(
    contracts_registry: dict[str, Any],
    metadata_registry: dict[str, Any],
    taxonomies_registry: dict[str, Any],
    deductions_registry: dict[str, Any],
    labels_registry: dict[str, Any],
    protocol_registries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    contracts = contracts_registry.get("contracts", {})
    metadata = metadata_registry.get("metadata", {})
    taxonomies = taxonomies_registry.get("taxonomies", {})
    deductions = deductions_registry.get("deductions", {})
    labels = labels_registry.get("labels", {})
    generated_deductions = build_generated_deductions(protocol_registries or [])
    generated_tokens = build_generated_tokens(protocol_registries or [])

    tokens: dict[str, Any] = {}
    manual_tokens = set(contracts)
    for token in sorted(contracts, key=str.lower):
        token_contracts = contracts[token]
        entry: dict[str, Any] = {
            "deployments": build_deployments(
                token,
                token_contracts,
                metadata.get(token, {}),
            ),
            "taxonomies": taxonomies.get(token, {}),
        }

        token_deductions = build_deductions(
            deductions.get(token, {}),
            labels,
        )
        merge_deductions(token_deductions, generated_deductions.get(token, {}))
        if token_deductions:
            entry["deductions"] = token_deductions

        tokens[token] = entry

    merge_generated_tokens(tokens, generated_tokens)
    for token in sorted(deductions, key=str.lower):
        if token in manual_tokens or token not in tokens:
            continue
        token_deductions = build_deductions(
            deductions[token],
            labels,
        )
        if token_deductions:
            merge_deductions(tokens[token].setdefault("deductions", {}), token_deductions)

    return {"tokens": tokens}


def load_protocol_registries(protocols_dir: Path) -> list[dict[str, Any]]:
    if not protocols_dir.exists():
        return []
    return [
        load_json(path)
        for path in sorted(protocols_dir.glob("*.json"), key=lambda item: item.name.lower())
    ]


def build_deployments(
    token: str,
    token_contracts: dict[str, Any],
    token_metadata: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    deployments: dict[str, list[dict[str, Any]]] = {}
    for chain in sorted(token_contracts, key=str.lower):
        deployments[chain] = []
        for address in normalize_addresses(token_contracts[chain]):
            deployment = {"address": address}
            metadata = token_metadata.get(chain, {}).get(address, {})
            for key in ("name", "symbol", "decimals"):
                if key in metadata:
                    deployment[key] = metadata[key]
            deployments[chain].append(deployment)

    return deployments


def build_deductions(
    token_deductions: dict[str, Any],
    labels: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for chain in sorted(token_deductions, key=str.lower):
        output[chain] = []
        for deduction in token_deductions[chain]:
            address = deduction["address"]
            entry = {
                "address": address,
                "type": deduction["type"],
            }
            label = labels.get(chain, {}).get(address)
            if label:
                entry["labels"] = label
            output[chain].append(entry)

    return output


def build_generated_deductions(
    protocol_registries: list[dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    output: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for registry in protocol_registries:
        for protocol, records in registry.items():
            for record in records:
                chain = record["chain"]
                entry = {
                    "address": record["address"],
                    "type": record["type"],
                }
                labels = generated_deduction_labels(protocol, record)
                if labels:
                    entry["labels"] = labels
                for token in generated_deduction_tokens(protocol, record):
                    output.setdefault(token, {}).setdefault(chain, []).append(entry.copy())

    return output


def generated_deduction_tokens(
    protocol: str,
    record: dict[str, Any],
) -> list[str]:
    if protocol in {"uniswap_v2", "uniswap_v3"}:
        return record.get("tokens", [])
    return [record["token"]]


def generated_deduction_labels(
    protocol: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    if protocol == "aave_v3":
        protocol_name = record["protocol"]
        version = record.get("version", protocol_version(protocol))
        market = record["market"]
        return {
            "market": market,
            "name": record["name"],
            "protocol": protocol_name,
            "symbol": record["symbol"],
            "version": version,
        }
    if protocol in {"uniswap_v2", "uniswap_v3"}:
        protocol_name = record["protocol"]
        version = record.get("version", protocol_version(protocol))
        pool = record.get("pool", "-".join(record["tokens"]))
        return {
            "name": f"{protocol_name} {version} {pool}",
            "pool": pool,
            "protocol": protocol_name,
            "version": version,
        }
    return {
        key: record[key]
        for key in ("name", "protocol", "symbol")
        if key in record
    }


def protocol_version(protocol: str) -> str:
    return {
        "aave_v3": "V3",
        "uniswap_v2": "V2",
        "uniswap_v3": "V3",
    }[protocol]


def build_generated_tokens(
    protocol_registries: list[dict[str, Any]],
) -> dict[str, Any]:
    tokens: dict[str, Any] = {}
    for registry in protocol_registries:
        for protocol, records in registry.items():
            if protocol != "aave_v3":
                continue
            for record in records:
                symbol = record["symbol"]
                entry = tokens.setdefault(
                    symbol,
                    {
                        "deployments": {},
                        "taxonomies": {
                            "category": "Lending",
                            "issuer": "Aave",
                        },
                    },
                )
                entry["deployments"].setdefault(record["chain"], []).append({
                    "address": record["address"],
                    "decimals": record["decimals"],
                    "name": record["onchain_name"],
                    "symbol": record["onchain_symbol"],
                })
    return tokens


def merge_generated_tokens(
    tokens: dict[str, Any],
    generated_tokens: dict[str, Any],
) -> None:
    for token, generated in generated_tokens.items():
        entry = tokens.setdefault(
            token,
            {
                "deployments": {},
                "taxonomies": generated["taxonomies"],
            },
        )
        entry.setdefault("taxonomies", generated["taxonomies"])
        for chain, deployments in generated["deployments"].items():
            target_deployments = entry.setdefault("deployments", {}).setdefault(chain, [])
            seen = {deployment["address"].lower() for deployment in target_deployments}
            for deployment in deployments:
                if deployment["address"].lower() in seen:
                    continue
                target_deployments.append(deployment)
                seen.add(deployment["address"].lower())


def merge_deductions(
    target: dict[str, list[dict[str, Any]]],
    generated: dict[str, list[dict[str, Any]]],
) -> None:
    for chain, entries in generated.items():
        target_entries = target.setdefault(chain, [])
        seen = {entry["address"].lower() for entry in target_entries}
        for entry in entries:
            if entry["address"].lower() in seen:
                continue
            target_entries.append(entry)
            seen.add(entry["address"].lower())


def normalize_addresses(value: Any) -> list[str]:
    return value if isinstance(value, list) else [value]


def sort_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: sort_json(value[key])
            for key in sorted(value, key=sort_key)
        }
    if isinstance(value, list):
        return [sort_json(item) for item in value]
    return value


def sort_key(key: str) -> tuple[int, str]:
    return (TOKEN_ENTRY_KEY_ORDER.get(key, len(TOKEN_ENTRY_KEY_ORDER)), key.lower())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build registries/tokens.json.")
    parser.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACTS)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--taxonomies", type=Path, default=DEFAULT_TAXONOMIES)
    parser.add_argument("--deductions", type=Path, default=DEFAULT_DEDUCTIONS)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--protocols-dir", type=Path, default=DEFAULT_PROTOCOLS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    tokens = build_tokens(
        load_json(args.contracts),
        load_json(args.metadata),
        load_json(args.taxonomies),
        load_json(args.deductions),
        load_json(args.labels),
        load_protocol_registries(args.protocols_dir),
    )
    write_json(args.output, tokens)
    print(f"Wrote tokens to {args.output}")


if __name__ == "__main__":
    main()
