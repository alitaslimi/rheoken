"""Generic EVM JSON-RPC helpers."""

import os
import re
from typing import Any

from web3 import Web3

from rpcs import alchemy, drpc

DEFAULT_RPC_TIMEOUT = 10
NATIVE_TOKEN_ADDRESS = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
BURN_ADDRESSES = {
    "0x0000000000000000000000000000000000000000": "Null Address",
}
TOTAL_SUPPLY_SELECTOR = "0x18160ddd"
BALANCE_OF_SELECTOR = "0x70a08231"
DECIMALS_SELECTOR = "0x313ce567"
SYMBOL_SELECTOR = "0x95d89b41"
NAME_SELECTOR = "0x06fdde03"


def connect(
    chain: str,
    chain_config: dict,
    *,
    rpc: str | None = None,
    timeout: float = DEFAULT_RPC_TIMEOUT,
) -> Web3:
    """Connect to the first working RPC endpoint for *chain_config*."""
    candidates = rpc_candidates(chain, chain_config, rpc=rpc)
    failures = []

    for rpc_url in candidates:
        try:
            return connect_url(rpc_url, chain_config, timeout=timeout)
        except Exception as exc:
            failures.append(
                f"{safe_rpc_url(rpc_url)}: {exc.__class__.__name__}: {safe_error(exc)}"
            )

    detail = "\n  ".join(failures) if failures else "(no RPCs configured)"
    raise ConnectionError(f"All RPCs failed for chain '{chain}':\n  {detail}")


def connect_url(
    rpc_url: str,
    _chain_config: dict,
    *,
    timeout: float = DEFAULT_RPC_TIMEOUT,
) -> Web3:
    """Create a Web3 client without RPC preflight calls."""
    return Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))


def rpc_candidates(chain: str, chain_config: dict, *, rpc: str | None = None) -> list[str]:
    """Return configured RPC candidates in preference order."""
    candidates = []
    if rpc:
        candidates.append(rpc)
    for provider_url in (alchemy.rpc_url(chain), drpc.rpc_url(chain)):
        if provider_url:
            candidates.append(provider_url)
    candidates.extend(chain_config.get("public_rpcs", []))
    return list(dict.fromkeys(candidates))


def safe_rpc_url(value: str) -> str:
    """Redact API keys from known RPC endpoint URLs."""
    value = re.sub(
        r"(https://[^/\s]+\.g\.alchemy\.com/v2/)[^\s]+",
        r"\1<redacted>",
        value,
    )
    value = re.sub(
        r"(https://lb\.drpc\.live/[^/\s]+/)[^\s]+",
        r"\1<redacted>",
        value,
    )
    for key, secret in os.environ.items():
        if key.endswith("ALCHEMY_API_KEY") or key.endswith("DRPC_API_KEY"):
            if secret:
                value = value.replace(secret, "<redacted>")
    return value


def safe_error(exc: BaseException) -> str:
    """Return an exception message with known RPC API keys redacted."""
    return safe_rpc_url(str(exc))


def block_info(w3: Web3, block: int | None = None) -> tuple[int, int]:
    """Fetch ``(block_number, block_timestamp)`` through ``eth_getBlockByNumber``."""
    identifier = block_identifier(block)
    response = w3.provider.make_request("eth_getBlockByNumber", [identifier, False])
    if response.get("error"):
        raise RuntimeError(f"eth_getBlockByNumber failed: {response['error']}")
    result = response.get("result")
    if result is None:
        raise RuntimeError(f"eth_getBlockByNumber returned no block for {identifier}")
    return int(result["number"], 16), int(result["timestamp"], 16)


def block_identifier(block: int | str | None) -> str:
    """Return the JSON-RPC block identifier without extra RPC lookups."""
    if block is None:
        return "latest"
    if isinstance(block, int):
        return hex(block)
    return block


def supply(w3: Web3, token_address: str, block: int | str = "latest") -> int:
    """Call ``totalSupply()`` through one raw ``eth_call``."""
    return eth_call_uint256(w3, token_address, TOTAL_SUPPLY_SELECTOR, block=block)


def native_balance(w3: Web3, holder_address: str, block: int | str = "latest") -> int:
    """Fetch native asset balance through ``eth_getBalance``."""
    checksum_holder = Web3.to_checksum_address(holder_address.lower())
    return w3.eth.get_balance(checksum_holder, block_identifier=block)


def balance(
    w3: Web3,
    token_address: str,
    holder_address: str,
    block: int | str = "latest",
) -> int:
    """Call ``balanceOf(holder_address)`` through one raw ``eth_call``."""
    checksum_holder = Web3.to_checksum_address(holder_address.lower())
    holder_word = checksum_holder[2:].lower().rjust(64, "0")
    return eth_call_uint256(
        w3,
        token_address,
        f"{BALANCE_OF_SELECTOR}{holder_word}",
        block=block,
    )


def eth_call_uint256(
    w3: Web3,
    token_address: str,
    data: str,
    *,
    block: int | str = "latest",
) -> int:
    """Execute one raw ``eth_call`` and parse the uint256 return value."""
    return int(eth_call(w3, token_address, data, block=block), 16)


def eth_call(
    w3: Web3,
    contract_address: str,
    data: str,
    *,
    block: int | str = "latest",
) -> str:
    """Execute one raw ``eth_call`` and return its hex result."""
    checksum_token = Web3.to_checksum_address(contract_address.lower())
    response = w3.provider.make_request(
        "eth_call",
        [
            {
                "to": checksum_token,
                "data": data,
            },
            block_identifier(block),
        ],
    )
    if response.get("error"):
        raise RuntimeError(f"eth_call failed: {response['error']}")
    result = response.get("result")
    if result is None:
        raise RuntimeError("eth_call returned no result")
    if not isinstance(result, str) or not result.startswith("0x"):
        raise RuntimeError(f"eth_call returned invalid result: {result}")
    return result


def encode_abi_address(address: str) -> str:
    """ABI-encode an address argument without importing an ABI codec."""
    return Web3.to_checksum_address(address).lower().removeprefix("0x").rjust(64, "0")


def encode_abi_uint24(value: int) -> str:
    """ABI-encode a uint24 argument without importing an ABI codec."""
    if value < 0 or value > 2**24 - 1:
        raise ValueError(f"uint24 out of range: {value}")
    return hex(value).removeprefix("0x").rjust(64, "0")


def decode_address_result(result: Any) -> str:
    """Decode a single address return value from raw ``eth_call`` output."""
    if not isinstance(result, str) or not result.startswith("0x"):
        raise RuntimeError(f"invalid address result: {result}")
    return f"0x{result[-40:]}".lower()


def fetch_metadata(
    w3: Web3,
    token_address: str,
    *,
    chain: str | None = None,
    block: int | str = "latest",
) -> dict:
    """Fetch ERC-20 ``decimals``, ``symbol``, and ``name`` metadata."""
    metadata = {
        "address": token_address.lower(),
        "decimals": eth_call_uint256(w3, token_address, DECIMALS_SELECTOR, block=block),
        "symbol": _decode_abi_text_result(
            eth_call(w3, token_address, SYMBOL_SELECTOR, block=block)
        ),
    }
    if chain is not None:
        metadata = {"chain": chain, **metadata}

    try:
        metadata["name"] = _decode_abi_text_result(
            eth_call(w3, token_address, NAME_SELECTOR, block=block)
        )
    except Exception:
        pass

    return metadata


def _decode_abi_text_result(result: str) -> str:
    raw = result.removeprefix("0x")
    if not raw:
        return ""
    try:
        if len(raw) >= 128 and int(raw[:64], 16) == 32:
            size = int(raw[64:128], 16)
            return _decode_text(bytes.fromhex(raw[128:128 + size * 2]))
        return _decode_text(bytes.fromhex(raw[:64]))
    except ValueError:
        return ""


def _decode_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.rstrip(b"\x00").decode("utf-8", errors="replace")
    if hasattr(value, "hex"):
        raw = bytes(value).rstrip(b"\x00")
        return raw.decode("utf-8", errors="replace")
    return str(value)
