"""Uniswap V3 pool discovery.

This script derives generated pool deductions from Uniswap V3 Factory state.
For each same-chain pair of tracked token deployments in ``registries/sources/contracts.json``,
it asks the matching factory for ``getPool(tokenA, tokenB, fee)`` across known
fee tiers. Existing pools become generated deductions for both underlying assets
and standalone generated pool entries.
"""

import argparse
import copy
import json
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

from web3 import Web3

from fetch_metadata import _load_env_file, _safe_error
from rpcs.base import connect as connect_rpc
from rpcs.base import decode_address_result
from rpcs.base import encode_abi_address
from rpcs.base import encode_abi_uint24
from rpcs.base import eth_call

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCES = ROOT / "registries" / "sources"
DEFAULT_CONTRACTS = DEFAULT_SOURCES / "contracts.json"
DEFAULT_CHAINS = DEFAULT_SOURCES / "chains.json"
DEFAULT_OUTPUT = ROOT / "registries" / "protocols" / "uniswap_v3.json"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
FEE_TIERS = [100, 200, 300, 400, 500, 3000, 10000]
GET_POOL_SELECTOR = "0x1698ee82"

UNISWAP_V3_FACTORIES = [
    {"chain": "arbitrum", "address": "0x1f98431c8ad98523631ae4a59f267346ea31f984"},
    {"chain": "avalanche", "address": "0x740b1c1de25031c31ff4fc9a62f554a55cdc1bad"},
    {"chain": "base", "address": "0x33128a8fc17869897dce68ed026d694621f6fdfd"},
    {"chain": "blast", "address": "0x792edade80af5fc680d96a2ed80a44247d2cf6fd"},
    {"chain": "bsc", "address": "0xdb1d10011ad0ff90774d0c6bb92e5c5c8b4461f7"},
    {"chain": "celo", "address": "0xafe208a311b21f13ef87e33a90049fc17a7acdec"},
    {"chain": "ethereum", "address": "0x1f98431c8ad98523631ae4a59f267346ea31f984"},
    {"chain": "megaeth", "address": "0x3a5f0cd7d62452b7f899b2a5758bfa57be0de478"},
    {"chain": "monad", "address": "0x204faca1764b154221e35c0d20abb3c525710498"},
    {"chain": "optimism", "address": "0x1f98431c8ad98523631ae4a59f267346ea31f984"},
    {"chain": "polygon", "address": "0x1f98431c8ad98523631ae4a59f267346ea31f984"},
    {"chain": "unichain", "address": "0x1f98400000000000000000000000000000000003"},
    {"chain": "worldchain", "address": "0x7a5028bda40e7b173c278c5342087826455ea25a"},
    {"chain": "zksync", "address": "0x8fda5a7a8dca67bbcdd10f02fa0649a937215422"},
    {"chain": "zora", "address": "0x7145f8aeef1f6510e92164038e1b6f8cb2c42cbb"},
]


def load_config() -> dict[str, Any]:
    """Return Uniswap V3 Factory source metadata."""
    return {
        "factories": copy.deepcopy(UNISWAP_V3_FACTORIES),
        "fee_tiers": list(FEE_TIERS),
    }


def factories(chain: str, config: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Return configured Uniswap V3 factories for *chain*."""
    cfg = config or load_config()
    return [
        factory for factory in cfg.get("factories", [])
        if factory.get("chain") == chain
    ]


def fee_tiers(config: Optional[dict[str, Any]] = None) -> list[int]:
    """Return configured Uniswap V3 fee tiers."""
    cfg = config or load_config()
    return list(cfg.get("fee_tiers", FEE_TIERS))


def discover_pools(
    w3: Web3,
    chain: str,
    contracts_registry: dict[str, Any],
    *,
    config: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Derive generated pool records from Uniswap V3 Factory state."""
    generated = []
    deployments = tracked_deployments(chain, contracts_registry)
    for factory_config in factories(chain, config=config):
        queries = pool_queries(deployments, fee_tiers(config=config))
        pools = get_pools(w3, factory_config["address"], queries)
        for query, pool in zip(queries, pools):
            if pool is None:
                continue
            generated.append(build_pool_record(
                token_a=query["token0"],
                address_a=query["address0"],
                token_b=query["token1"],
                address_b=query["address1"],
                chain=chain,
                pool=pool,
                fee=query["fee"],
            ))

    return _dedupe_records(generated)


def pool_queries(
    deployments: list[tuple[str, str]],
    fees: list[int],
) -> list[dict[str, Any]]:
    """Return getPool queries in Uniswap V3 token0/token1 order."""
    queries = []
    for token_a, address_a, token_b, address_b in pool_candidates(deployments):
        token0, address0, token1, address1 = ordered_underlyings(
            token_a,
            address_a,
            token_b,
            address_b,
        )
        for fee in fees:
            queries.append({
                "token0": token0,
                "address0": address0,
                "token1": token1,
                "address1": address1,
                "fee": fee,
            })
    return queries


def get_pools(
    w3: Web3,
    factory_address: str,
    queries: list[dict[str, Any]],
) -> list[str | None]:
    """Return pool addresses for many getPool queries."""
    rpc_url = getattr(w3.provider, "endpoint_uri", "")
    if rpc_url:
        return get_pools_batch(rpc_url, factory_address, queries)
    return [
        get_pool(w3, factory_address, query["address0"], query["address1"], query["fee"])
        for query in queries
    ]


def get_pool(w3: Web3, factory_address: str, token_a: str, token_b: str, fee: int) -> str | None:
    """Return the pool address, or ``None`` when no pool exists."""
    pool = _get_pool_once(w3, factory_address, token_a, token_b, fee)
    if pool is not None:
        return pool
    return _get_pool_once(w3, factory_address, token_b, token_a, fee)


def _get_pool_once(
    w3: Web3,
    factory_address: str,
    token_a: str,
    token_b: str,
    fee: int,
) -> str | None:
    try:
        result = eth_call(
            w3,
            factory_address,
            encode_get_pool_data(token_a, token_b, fee),
        )
    except RuntimeError as exc:
        if "revert" in str(exc).lower():
            return None
        raise
    normalized = decode_address_result(result)
    if normalized == ZERO_ADDRESS:
        return None
    return normalized


def get_pools_batch(
    rpc_url: str,
    factory_address: str,
    queries: list[dict[str, Any]],
    *,
    batch_size: int = 25,
    max_retries: int = 5,
    timeout: float = 30,
) -> list[str | None]:
    """Fetch Uniswap V3 pools through batched ``eth_call`` requests."""
    output: list[str | None] = []
    request_id = 1
    checksum_factory = Web3.to_checksum_address(factory_address)
    for start in range(0, len(queries), batch_size):
        chunk = queries[start:start + batch_size]
        batch, request_id = build_get_pool_batch(
            checksum_factory,
            chunk,
            request_id,
            reverse=False,
        )
        output.extend(execute_get_pool_batch(
            rpc_url,
            batch,
            max_retries=max_retries,
            timeout=timeout,
        ))
        missing = [
            (index, query)
            for index, query in enumerate(chunk, start=len(output) - len(chunk))
            if output[index] is None
        ]
        if missing:
            reverse_batch, request_id = build_get_pool_batch(
                checksum_factory,
                [query for _, query in missing],
                request_id,
                reverse=True,
            )
            reverse_results = execute_get_pool_batch(
                rpc_url,
                reverse_batch,
                max_retries=max_retries,
                timeout=timeout,
            )
            for (index, _query), pool in zip(missing, reverse_results):
                output[index] = pool
        time.sleep(0.1)
    return output


def build_get_pool_batch(
    checksum_factory: str,
    queries: list[dict[str, Any]],
    request_id: int,
    *,
    reverse: bool,
) -> tuple[list[dict[str, Any]], int]:
    batch = []
    for query in queries:
        address0 = query["address1"] if reverse else query["address0"]
        address1 = query["address0"] if reverse else query["address1"]
        batch.append({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "eth_call",
            "params": [
                {
                    "to": checksum_factory,
                    "data": encode_get_pool_data(address0, address1, query["fee"]),
                },
                "latest",
            ],
        })
        request_id += 1
    return batch, request_id


def execute_get_pool_batch(
    rpc_url: str,
    batch: list[dict[str, Any]],
    *,
    max_retries: int,
    timeout: float,
) -> list[str | None]:
    responses = post_rpc_batch_with_retries(
        rpc_url,
        batch,
        max_retries=max_retries,
        timeout=timeout,
    )
    by_id = {response.get("id"): response for response in responses}
    output = []
    for request in batch:
        response = by_id.get(request["id"])
        if response is None:
            raise RuntimeError(f"missing RPC response for request {request['id']}")
        if response.get("error"):
            raise RuntimeError(f"eth_call failed: {response['error']}")
        normalized = decode_address_result(response.get("result"))
        output.append(None if normalized == ZERO_ADDRESS else normalized)
    return output


def post_rpc_batch_with_retries(
    rpc_url: str,
    batch: list[dict[str, Any]],
    *,
    max_retries: int,
    timeout: float,
) -> list[dict[str, Any]]:
    for attempt in range(max_retries + 1):
        responses = post_rpc_batch(rpc_url, batch, timeout=timeout)
        if not has_rate_limit_error(responses):
            return responses
        if attempt == max_retries:
            return responses
        time.sleep(0.5 * 2**attempt)
    return responses


def has_rate_limit_error(responses: list[dict[str, Any]]) -> bool:
    for response in responses:
        error = response.get("error")
        if isinstance(error, dict) and error.get("code") == 429:
            return True
    return False


def post_rpc_batch(
    rpc_url: str,
    batch: list[dict[str, Any]],
    *,
    timeout: float,
) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        rpc_url,
        data=json.dumps(batch).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"expected batch RPC response, got {type(payload).__name__}")
    return payload


def encode_get_pool_data(token0: str, token1: str, fee: int) -> str:
    return (
        GET_POOL_SELECTOR
        + encode_abi_address(token0)
        + encode_abi_address(token1)
        + encode_abi_uint24(fee)
    )


def build_pool_record(
    *,
    token_a: str,
    address_a: str,
    token_b: str,
    address_b: str,
    chain: str,
    pool: str,
    fee: int,
) -> dict[str, Any]:
    token0, address0, token1, address1 = ordered_underlyings(
        token_a,
        address_a,
        token_b,
        address_b,
    )
    symbol = f"{token0}-{token1}-{fee}"
    pool_symbol = f"{token0}-{token1}"
    version = "V3"
    return {
        "tokens": [token0, token1],
        "chain": chain,
        "address": pool,
        "underlying_addresses": {
            token0: address0,
            token1: address1,
        },
        "fee": fee,
        "pool": pool_symbol,
        "symbol": symbol,
        "name": f"Uniswap {version} {pool_symbol}",
        "onchain_name": "Uniswap V3",
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
    """Return underlyings in Uniswap V3 token0/token1 address order."""
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


def pool_candidates(deployments: list[tuple[str, str]]) -> list[tuple[str, str, str, str]]:
    """Return unique cross-token pool candidates from tracked deployments."""
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
        json.dumps({"uniswap_v3": records}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_output(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("uniswap_v3", [])


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
    parser = argparse.ArgumentParser(description="Discover Uniswap V3 pools.")
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
            chain_records = discover_pools(w3, chain, contracts_registry)
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
    print(f"Wrote {len(records)} Uniswap V3 pool record(s) to {args.output}")
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
            record.get("fee"),
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
