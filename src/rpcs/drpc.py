"""dRPC endpoint helpers."""

import os

DRPC_NETWORKS = {
    "arc_testnet": "arc-testnet",
    "arbitrum": "arbitrum",
    "avalanche": "avalanche",
    "base": "base",
    "bsc": "bsc",
    "celo": "celo",
    "ethereum": "ethereum",
    "ink": "ink",
    "katana": "katana",
    "linea": "linea",
    "lisk": "lisk",
    "mantle": "mantle",
    "megaeth": "megaeth",
    "monad": "monad-mainnet",
    "optimism": "optimism",
    "plasma": "plasma",
    "plume": "plume",
    "polygon": "polygon",
    "scroll": "scroll",
    "tempo": "tempo-mainnet",
    "unichain": "unichain",
    "worldchain": "worldchain",
    "zksync": "zksync",
}


def api_key() -> str | None:
    """Return the configured dRPC API key."""
    return os.environ.get("DRPC_API_KEY")


def rpc_url(chain: str) -> str | None:
    """Build the dRPC URL for a supported chain."""
    key = api_key()
    network = DRPC_NETWORKS.get(chain)
    if not key or not network:
        return None
    return f"https://lb.drpc.live/{network}/{key}"
