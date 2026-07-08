"""Alchemy-specific Token API helpers."""

import json
import os
from urllib import request

ALCHEMY_RPC_BASES = {
    "arbitrum": "https://arb-mainnet.g.alchemy.com/v2/",
    "avalanche": "https://avax-mainnet.g.alchemy.com/v2/",
    "base": "https://base-mainnet.g.alchemy.com/v2/",
    "berachain": "https://berachain-mainnet.g.alchemy.com/v2/",
    "bsc": "https://bnb-mainnet.g.alchemy.com/v2/",
    "celo": "https://celo-mainnet.g.alchemy.com/v2/",
    "edge": "https://edge-mainnet.g.alchemy.com/v2/",
    "ethereum": "https://eth-mainnet.g.alchemy.com/v2/",
    "gnosis": "https://gnosis-mainnet.g.alchemy.com/v2/",
    "hyperevm": "https://hyperliquid-mainnet.g.alchemy.com/v2/",
    "ink": "https://ink-mainnet.g.alchemy.com/v2/",
    "linea": "https://linea-mainnet.g.alchemy.com/v2/",
    "mantle": "https://mantle-mainnet.g.alchemy.com/v2/",
    "megaeth": "https://megaeth-mainnet.g.alchemy.com/v2/",
    "monad": "https://monad-mainnet.g.alchemy.com/v2/",
    "optimism": "https://opt-mainnet.g.alchemy.com/v2/",
    "plasma": "https://plasma-mainnet.g.alchemy.com/v2/",
    "polygon": "https://polygon-mainnet.g.alchemy.com/v2/",
    "robinhood": "https://robinhood-mainnet.g.alchemy.com/v2/",
    "rootstock": "https://rootstock-mainnet.g.alchemy.com/v2/",
    "scroll": "https://scroll-mainnet.g.alchemy.com/v2/",
    "sei": "https://sei-mainnet.g.alchemy.com/v2/",
    "sonic": "https://sonic-mainnet.g.alchemy.com/v2/",
    "solana": "https://solana-mainnet.g.alchemy.com/v2/",
    "stable": "https://stable-mainnet.g.alchemy.com/v2/",
    "sui": "https://sui-mainnet.g.alchemy.com/v2/",
    "tempo": "https://tempo-mainnet.g.alchemy.com/v2/",
    "tron": "https://tron-mainnet.g.alchemy.com/v2/",
    "unichain": "https://unichain-mainnet.g.alchemy.com/v2/",
    "worldchain": "https://worldchain-mainnet.g.alchemy.com/v2/",
    "zksync": "https://zksync-mainnet.g.alchemy.com/v2/",
}


def api_key() -> str | None:
    """Return the configured Alchemy API key."""
    return os.environ.get("ALCHEMY_API_KEY")


def rpc_url(chain: str) -> str | None:
    """Build the Alchemy RPC URL for a supported chain."""
    key = api_key()
    base = ALCHEMY_RPC_BASES.get(chain)
    if not key or not base:
        return None
    return f"{base.rstrip('/')}/{key}"


def token_metadata(rpc_url: str, token_address: str, *, timeout: float = 10) -> dict:
    """Fetch token metadata through ``alchemy_getTokenMetadata``."""
    return _post_json_rpc(
        rpc_url,
        "alchemy_getTokenMetadata",
        [token_address],
        timeout=timeout,
    )


def token_balances(
    rpc_url: str,
    holder_address: str,
    token_addresses: list[str],
    *,
    timeout: float = 10,
) -> dict:
    """Fetch selected token balances through ``alchemy_getTokenBalances``."""
    return _post_json_rpc(
        rpc_url,
        "alchemy_getTokenBalances",
        [holder_address, token_addresses],
        timeout=timeout,
    )


def _post_json_rpc(
    rpc_url: str,
    method: str,
    params: list,
    *,
    timeout: float,
) -> dict:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode("utf-8")
    req = request.Request(
        rpc_url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise RuntimeError(f"{method} failed: {payload['error']}")
    return payload["result"]
