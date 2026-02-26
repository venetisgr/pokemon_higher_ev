"""Polygon blockchain reader for Courtyard NFT on-chain data."""

import json
import logging

from web3 import Web3

from src.config import settings

logger = logging.getLogger(__name__)

# Minimal ERC-721 ABI for reading token data
ERC721_ABI = json.loads("""[
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "tokenURI",
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]""")


class PolygonReader:
    """Read on-chain data from the Courtyard ERC-721 contract on Polygon."""

    def __init__(self, rpc_url: str | None = None):
        self.rpc_url = rpc_url or settings.polygon_rpc_url
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(settings.courtyard_contract_address),
            abi=ERC721_ABI,
        )

    @property
    def is_connected(self) -> bool:
        try:
            return self.w3.is_connected()
        except Exception:
            return False

    def get_total_supply(self) -> int:
        """Get total number of minted Courtyard NFTs."""
        try:
            return self.contract.functions.totalSupply().call()
        except Exception as e:
            logger.warning("Failed to get total supply: %s", e)
            return 0

    def get_owner(self, token_id: int) -> str:
        """Get the current owner address of a token."""
        try:
            return self.contract.functions.ownerOf(token_id).call()
        except Exception as e:
            logger.warning("Failed to get owner of token %d: %s", token_id, e)
            return ""

    def get_token_uri(self, token_id: int) -> str:
        """Get the metadata URI for a token."""
        try:
            return self.contract.functions.tokenURI(token_id).call()
        except Exception as e:
            logger.warning("Failed to get tokenURI for %d: %s", token_id, e)
            return ""

    async def get_token_metadata(self, token_id: int) -> dict:
        """Fetch and parse the metadata JSON for a token.

        The tokenURI typically points to an IPFS or HTTPS endpoint
        containing the card details (name, grade, image, attributes).
        """
        import httpx

        uri = self.get_token_uri(token_id)
        if not uri:
            return {}

        # Convert IPFS URIs to gateway URLs
        if uri.startswith("ipfs://"):
            uri = uri.replace("ipfs://", "https://ipfs.io/ipfs/")

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(uri)
                resp.raise_for_status()
                metadata = resp.json()
                logger.info("Fetched metadata for token %d: %s", token_id, metadata.get("name", ""))
                return metadata
        except Exception as e:
            logger.warning("Failed to fetch metadata for token %d: %s", token_id, e)
            return {}

    def get_recent_transfers(self, token_id: int, from_block: int = 0) -> list[dict]:
        """Get transfer events for a specific token to track ownership history.

        Useful for detecting newly listed or recently transferred cards.
        """
        try:
            # Transfer event signature for ERC-721
            transfer_filter = self.contract.events.Transfer().get_logs(  # type: ignore[attr-defined]
                fromBlock=from_block or "latest",
                argument_filters={"tokenId": token_id},
            )
            return [
                {
                    "from": log["args"]["from"],
                    "to": log["args"]["to"],
                    "token_id": log["args"]["tokenId"],
                    "block": log["blockNumber"],
                    "tx_hash": log["transactionHash"].hex(),
                }
                for log in transfer_filter
            ]
        except Exception as e:
            logger.warning("Failed to get transfers for token %d: %s", token_id, e)
            return []
