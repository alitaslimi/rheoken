"""Sanity checks for source registry files."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRIES = ROOT / "registries"
SOURCES = REGISTRIES / "sources"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_registry_file(name):
    return load_json(SOURCES / name)


def load_generated_aave_tokens():
    protocols_path = REGISTRIES / "protocols" / "aave_v3.json"
    if not protocols_path.exists():
        return set()
    return {
        record["symbol"]
        for record in load_json(protocols_path)["aave_v3"]
    }


def test_registry_files_parse():
    for name in [
        "chains.json",
        "contracts.json",
        "deductions.json",
        "labels.json",
        "taxonomies.json",
    ]:
        assert isinstance(load_registry_file(name), dict)


def test_generated_metadata_parses():
    assert set(load_json(REGISTRIES / "artifacts" / "metadata.json")) == {"metadata"}


def test_generated_tokens_parses_when_present():
    tokens_path = REGISTRIES / "tokens.json"
    if tokens_path.exists():
        assert set(load_json(tokens_path)) == {"tokens"}


def test_generated_tokens_cover_contract_registry_when_present():
    tokens_path = REGISTRIES / "tokens.json"
    if tokens_path.exists():
        contracts = load_registry_file("contracts.json")["contracts"]
        tokens = load_json(tokens_path)["tokens"]

        assert set(contracts) <= set(tokens)


def test_all_contract_chains_are_known():
    contracts = load_registry_file("contracts.json")["contracts"]
    chains = set(load_registry_file("chains.json")["chains"])

    referenced = {
        chain
        for token_contracts in contracts.values()
        for chain in token_contracts
    }

    assert referenced <= chains


def test_all_contract_deployments_have_labels():
    contracts = load_registry_file("contracts.json")["contracts"]
    labels = load_registry_file("labels.json")["labels"]

    missing = []
    incomplete = []
    for token, token_contracts in contracts.items():
        for chain, addresses in token_contracts.items():
            if isinstance(addresses, str):
                addresses = [addresses]
            for address in addresses:
                label = labels.get(chain, {}).get(address)
                if not label:
                    missing.append((token, chain, address))
                elif not all(label.get(key) for key in ("name", "protocol", "deduction")) or label.get("type") != "token":
                    incomplete.append((token, chain, address))

    assert not missing
    assert not incomplete


def test_all_contract_tokens_have_taxonomies():
    contracts = load_registry_file("contracts.json")["contracts"]
    taxonomies = load_registry_file("taxonomies.json")["taxonomies"]

    assert set(contracts) <= set(taxonomies)


def test_deductions_reference_known_tokens_and_chains():
    contracts = load_registry_file("contracts.json")["contracts"]
    chains = set(load_registry_file("chains.json")["chains"])
    deductions = load_registry_file("deductions.json")["deductions"]

    assert set(deductions) <= set(contracts) | load_generated_aave_tokens()
    for token, token_deductions in deductions.items():
        assert set(token_deductions) <= chains, token


def test_deduction_labels_have_matching_deduction_type():
    deductions = load_registry_file("deductions.json")["deductions"]
    labels = load_registry_file("labels.json")["labels"]

    missing = []
    mismatched = []
    for token, token_deductions in deductions.items():
        for chain, entries in token_deductions.items():
            for entry in entries:
                label = labels.get(chain, {}).get(entry["address"])
                if not label:
                    missing.append((token, chain, entry["address"]))
                elif label.get("deduction") != entry["type"]:
                    mismatched.append((token, chain, entry["address"]))

    assert not missing
    assert not mismatched
