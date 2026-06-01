"""Tests for registry validation."""

from pathlib import Path

from validate import validate_registry


def test_current_registry_is_valid():
    root = Path(__file__).resolve().parents[1]
    errors = validate_registry(root / "registries" / "sources", root / "registries")

    assert errors == []


def test_unknown_deduction_token_is_reported(tmp_path):
    registry = tmp_path / "registries" / "sources"
    registries = tmp_path / "registries"
    registry.mkdir(parents=True)

    (registry / "chains.json").write_text('{"chains":{"ethereum":{}}}', encoding="utf-8")
    (registry / "contracts.json").write_text('{"contracts":{"USDC":{"ethereum":"0xabc"}}}', encoding="utf-8")
    (registry / "taxonomies.json").write_text('{"taxonomies":{"USDC":{}}}', encoding="utf-8")
    (registry / "labels.json").write_text('{"labels":{"ethereum":{}}}', encoding="utf-8")
    (registry / "deductions.json").write_text(
        '{"deductions":{"USDT":{"ethereum":[{"address":"0xabc","type":"locked"}]}}}',
        encoding="utf-8",
    )

    errors = validate_registry(registry, registries)

    assert any("unknown token 'USDT'" in error for error in errors)


def test_missing_deduction_label_is_reported(tmp_path):
    registry = tmp_path / "registries" / "sources"
    registries = tmp_path / "registries"
    registry.mkdir(parents=True)

    (registry / "chains.json").write_text('{"chains":{"ethereum":{}}}', encoding="utf-8")
    (registry / "contracts.json").write_text('{"contracts":{"USDC":{"ethereum":"0xabc"}}}', encoding="utf-8")
    (registry / "taxonomies.json").write_text('{"taxonomies":{"USDC":{}}}', encoding="utf-8")
    (registry / "labels.json").write_text('{"labels":{"ethereum":{}}}', encoding="utf-8")
    (registry / "deductions.json").write_text(
        '{"deductions":{"USDC":{"ethereum":[{"address":"0xabc","type":"locked"}]}}}',
        encoding="utf-8",
    )

    errors = validate_registry(registry, registries)

    assert any("missing deduction address '0xabc'" in error for error in errors)


def test_plain_evm_contract_addresses_must_be_lowercase(tmp_path):
    registry = tmp_path / "registries" / "sources"
    registries = tmp_path / "registries"
    registry.mkdir(parents=True)

    (registry / "chains.json").write_text('{"chains":{"ethereum":{}}}', encoding="utf-8")
    (registry / "contracts.json").write_text(
        '{"contracts":{"USDC":{"ethereum":"0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"}}}',
        encoding="utf-8",
    )
    (registry / "taxonomies.json").write_text('{"taxonomies":{"USDC":{}}}', encoding="utf-8")
    (registry / "labels.json").write_text('{"labels":{}}', encoding="utf-8")
    (registry / "deductions.json").write_text('{"deductions":{}}', encoding="utf-8")

    errors = validate_registry(registry, registries)

    assert any("plain EVM address must be lowercase" in error for error in errors)


def test_evm_contract_addresses_must_have_40_hex_characters(tmp_path):
    registry = tmp_path / "registries" / "sources"
    registries = tmp_path / "registries"
    registry.mkdir(parents=True)

    (registry / "chains.json").write_text('{"chains":{"ethereum":{}}}', encoding="utf-8")
    (registry / "contracts.json").write_text(
        '{"contracts":{"pzETH":{"ethereum":"0x8c9532a60e0e7c6bbd2b2c1303f63ace1c3e981"}}}',
        encoding="utf-8",
    )
    (registry / "taxonomies.json").write_text('{"taxonomies":{"pzETH":{}}}', encoding="utf-8")
    (registry / "labels.json").write_text('{"labels":{}}', encoding="utf-8")
    (registry / "deductions.json").write_text('{"deductions":{}}', encoding="utf-8")

    errors = validate_registry(registry, registries)

    assert any("plain EVM address must be lowercase 0x plus 40 hex characters" in error for error in errors)


def test_generated_protocol_records_reject_embedded_label_objects(tmp_path):
    registry = tmp_path / "registries" / "sources"
    registries = tmp_path / "registries"
    protocols = registries / "protocols"
    registry.mkdir(parents=True)
    protocols.mkdir(parents=True)

    (registry / "chains.json").write_text('{"chains":{"ethereum":{}}}', encoding="utf-8")
    (registry / "contracts.json").write_text(
        '{"contracts":{"USDC":{"ethereum":"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"}}}',
        encoding="utf-8",
    )
    (registry / "taxonomies.json").write_text('{"taxonomies":{"USDC":{}}}', encoding="utf-8")
    (registry / "labels.json").write_text('{"labels":{}}', encoding="utf-8")
    (registry / "deductions.json").write_text('{"deductions":{}}', encoding="utf-8")
    (protocols / "aave_v3.json").write_text(
        """
{
  "aave_v3": [
    {
      "address": "0x724dc807b04555b71ed48a6896b6f41593b8c637",
      "chain": "ethereum",
      "decimals": 6,
      "label": {"name": "embedded"},
      "market": "Core",
      "name": "Aave V3 Ethereum USDC",
      "onchain_name": "Aave Ethereum USDC",
      "onchain_symbol": "aEthUSDC",
      "protocol": "Aave",
      "symbol": "aUSDC",
      "token": "USDC",
      "type": "locked",
      "underlying_address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
      "version": "V3"
    }
  ]
}
""",
        encoding="utf-8",
    )

    errors = validate_registry(registry, registries)

    assert any("unexpected key 'label'" in error for error in errors)
