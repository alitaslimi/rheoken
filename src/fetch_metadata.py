"""CLI for refreshing generated token contract metadata.

Uses Alchemy's ``alchemy_getTokenMetadata`` when an Alchemy endpoint is
available for the chain — one RPC call returns symbol/name/decimals
(instead of three eth_calls). Falls back to dRPC / public RPCs with the
per-method eth_call path only when the bundled endpoint isn't usable
(chain not on plan, rate-limit, contract not indexed by Alchemy, etc.).
"""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Callable, Iterable

from web3 import Web3

from rpcs import alchemy
from rpcs.base import fetch_metadata, rpc_candidates, safe_error, safe_rpc_url

EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
ALCHEMY_HOST_MARKER = ".g.alchemy.com"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(
        r"(https://[^/\s]+\.g\.alchemy\.com/v2/)[^\s]+",
        r"\1<redacted>",
        message,
    )
    message = re.sub(
        r"(https://lb\.drpc\.live/[^/\s]+/)[^\s]+",
        r"\1<redacted>",
        message,
    )
    for key, value in os.environ.items():
        if key.endswith("ALCHEMY_API_KEY") or key.endswith("DRPC_API_KEY"):
            if value:
                message = message.replace(value, "<redacted>")
    return message


def is_evm_address(address: str) -> bool:
    """Return True when *address* is a standard 20-byte EVM hex address."""
    return bool(EVM_ADDRESS_RE.fullmatch(address))


def iter_contracts(contracts_registry: dict) -> Iterable[tuple[str, str, str]]:
    """Yield ``(token, chain, address)`` from string-or-list contract entries."""
    for token, chains in contracts_registry.get("contracts", {}).items():
        for chain, value in chains.items():
            addresses = value if isinstance(value, list) else [value]
            for address in addresses:
                yield token, chain, address


def build_metadata(
    contracts_registry: dict,
    fetcher: Callable[[str, str, str], dict],
    *,
    tokens: set[str] | None = None,
    chains: set[str] | None = None,
    existing: dict | None = None,
    refresh: bool = False,
    on_error: Callable[[str, str, str, Exception], None] | None = None,
    on_skip: Callable[[str, str, str, str], None] | None = None,
) -> dict:
    """
    Build metadata from contracts using *fetcher*.

    The returned shape is:
    ``{"metadata": {token: {chain: {address: {"symbol", "name", "decimals"}}}}}``.
    """
    output = json.loads(json.dumps(existing or {"metadata": {}}))
    output.setdefault("metadata", {})

    for token, chain, address in iter_contracts(contracts_registry):
        if tokens is not None and token not in tokens:
            continue
        if chains is not None and chain not in chains:
            continue
        if not is_evm_address(address):
            if on_skip is not None:
                on_skip(token, chain, address, "unsupported non-EVM address")
            continue

        normalized_address = address.lower()
        chain_metadata = output["metadata"].get(token, {}).get(chain, {})
        if not refresh and normalized_address in chain_metadata:
            if on_skip is not None:
                on_skip(token, chain, normalized_address, "already present")
            continue

        try:
            fetched = fetcher(token, chain, normalized_address)
        except Exception as exc:
            if on_error is None:
                raise
            on_error(token, chain, normalized_address, exc)
            continue

        chain_metadata = output["metadata"].setdefault(token, {}).setdefault(chain, {})
        chain_metadata[normalized_address] = {
            key: fetched[key]
            for key in ("symbol", "name", "decimals")
            if key in fetched
        }

    return output


def _alchemy_result_is_usable(result: dict) -> bool:
    """alchemy_getTokenMetadata returns nulls when it hasn't indexed the
    contract; treat that as a miss and fall through to eth_call."""
    if not isinstance(result, dict):
        return False
    decimals = result.get("decimals")
    if not isinstance(decimals, int):
        return False
    # Symbol or name being null is OK for some tokens; treat as empty string.
    return True


def fetch_token_metadata(
    chain: str,
    chain_config: dict,
    token_address: str,
    *,
    timeout: float = 10,
) -> dict:
    """
    Fetch ``decimals``/``symbol``/``name`` with per-call provider fallback.

    Iterates the chain's RPC candidate list (Alchemy → dRPC → public). For
    an Alchemy URL it issues a single ``alchemy_getTokenMetadata`` request;
    for any other URL it falls back to the three-method eth_call path. On
    any failure (rate-limit, forbidden, contract not indexed, network),
    moves to the next candidate.
    """
    candidates = rpc_candidates(chain, chain_config)
    failures: list[str] = []
    for rpc_url in candidates:
        endpoint = safe_rpc_url(rpc_url)
        try:
            if ALCHEMY_HOST_MARKER in rpc_url:
                result = alchemy.token_metadata(rpc_url, token_address, timeout=timeout)
                if not _alchemy_result_is_usable(result):
                    failures.append(
                        f"{endpoint}: alchemy_getTokenMetadata returned no decimals"
                    )
                    continue
                return {
                    "chain":    chain,
                    "address":  token_address.lower(),
                    "decimals": int(result["decimals"]),
                    "symbol":   result.get("symbol") or "",
                    "name":     result.get("name") or "",
                }
            # Non-Alchemy URL — fall back to the per-method eth_call path.
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
            return fetch_metadata(w3, token_address, chain=chain)
        except Exception as exc:
            failures.append(f"{endpoint}: {exc.__class__.__name__}: {safe_error(exc)}")

    detail = "\n  ".join(failures) if failures else "(no RPCs configured)"
    raise RuntimeError(
        f"All RPC candidates failed for {chain}/{token_address}:\n  {detail}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="fetch_metadata.py",
        description="Fetch EVM token symbol/name/decimals into registries/artifacts/metadata.json.",
    )
    parser.add_argument("--contracts", default="registries/sources/contracts.json")
    parser.add_argument("--chains-file", default="registries/sources/chains.json")
    parser.add_argument("--metadata", default="registries/artifacts/metadata.json")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--tokens", help="Comma-separated token roots to refresh.")
    parser.add_argument("--chains", help="Comma-separated chains to refresh.")
    parser.add_argument("--refresh", action="store_true", help="Refetch existing entries.")
    parser.add_argument("--dry-run", action="store_true", help="Print metadata without writing.")
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))

    contracts_registry = json.loads(Path(args.contracts).read_text(encoding="utf-8"))
    chains_registry = json.loads(Path(args.chains_file).read_text(encoding="utf-8"))
    metadata_path = Path(args.metadata)
    existing = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.exists()
        else {"metadata": {}}
    )

    token_filter = {item.strip() for item in args.tokens.split(",")} if args.tokens else None
    chain_filter = {item.strip() for item in args.chains.split(",")} if args.chains else None
    errors = []
    skipped = []

    def fetcher(_token: str, chain: str, address: str) -> dict:
        if chain not in chains_registry["chains"]:
            raise KeyError(f"chain '{chain}' not in chains registry")
        chain_config = chains_registry["chains"][chain]
        return fetch_token_metadata(chain, chain_config, address, timeout=args.timeout)

    def on_error(token: str, chain: str, address: str, exc: Exception) -> None:
        errors.append((token, chain, address, _safe_error(exc)))

    def on_skip(token: str, chain: str, address: str, reason: str) -> None:
        skipped.append((token, chain, address, reason))

    updated = build_metadata(
        contracts_registry,
        fetcher,
        tokens=token_filter,
        chains=chain_filter,
        existing=existing,
        refresh=args.refresh,
        on_error=on_error,
        on_skip=on_skip,
    )

    text = json.dumps(updated, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.dry_run:
        print(text, end="")
        print(f"Skipped {len(skipped)} contract(s).")
        for token, chain, address, reason in skipped:
            print(f"{token}.{chain}.{address}: {reason}")
        for token, chain, address, error in errors:
            print(f"{token}.{chain}.{address}: {error}")
        return

    metadata_path.write_text(text, encoding="utf-8")
    print(f"Wrote metadata to {metadata_path}")
    print(f"Skipped {len(skipped)} contract(s).")
    if skipped:
        for token, chain, address, reason in skipped:
            print(f"  {token}.{chain}.{address}: {reason}")
    if errors:
        print(f"Skipped {len(errors)} contract(s) with errors:")
        for token, chain, address, error in errors:
            print(f"  {token}.{chain}.{address}: {error}")


if __name__ == "__main__":
    main()
