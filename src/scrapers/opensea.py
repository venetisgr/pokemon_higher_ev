"""OpenSea API client for Courtyard NFT market data."""

import logging
from datetime import datetime

import httpx

from src.config import settings
from src.models import CardGrade, DataSource, MarketPrice

logger = logging.getLogger(__name__)

OPENSEA_API_V2 = "https://api.opensea.io/api/v2"


def _build_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if settings.opensea_api_key:
        headers["X-API-KEY"] = settings.opensea_api_key
    return headers


async def get_collection_stats() -> dict:
    """Fetch collection-level stats (floor price, volume, etc.)."""
    url = f"{OPENSEA_API_V2}/collections/{settings.courtyard_collection_slug}/stats"
    async with httpx.AsyncClient(headers=_build_headers(), timeout=30) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "Collection stats: floor=%.2f, volume=%.2f",
                data.get("total", {}).get("floor_price", 0),
                data.get("total", {}).get("volume", 0),
            )
            return data
        except Exception as e:
            logger.warning("Failed to fetch collection stats: %s", e)
            return {}


async def get_nft_details(token_id: str) -> dict:
    """Fetch details for a specific Courtyard NFT by token ID."""
    chain = "matic"  # Polygon
    url = (
        f"{OPENSEA_API_V2}/chain/{chain}/contract/"
        f"{settings.courtyard_contract_address}/nfts/{token_id}"
    )
    async with httpx.AsyncClient(headers=_build_headers(), timeout=30) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Failed to fetch NFT %s details: %s", token_id, e)
            return {}


async def get_listings_for_collection(
    limit: int = 50,
    next_cursor: str = "",
) -> tuple[list[dict], str]:
    """Fetch active listings from OpenSea for the Courtyard collection.

    Returns (listings, next_cursor) for pagination.
    """
    url = f"{OPENSEA_API_V2}/listings/collection/{settings.courtyard_collection_slug}/all"
    params = {"limit": min(limit, 100)}
    if next_cursor:
        params["next"] = next_cursor

    async with httpx.AsyncClient(headers=_build_headers(), timeout=30) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            listings = data.get("listings", [])
            cursor = data.get("next", "")
            logger.info("Fetched %d OpenSea listings", len(listings))
            return listings, cursor
        except Exception as e:
            logger.warning("Failed to fetch OpenSea listings: %s", e)
            return [], ""


async def get_recent_sales(
    token_id: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Fetch recent sales/events for a specific NFT or the collection."""
    chain = "matic"

    if token_id:
        url = (
            f"{OPENSEA_API_V2}/events/chain/{chain}/contract/"
            f"{settings.courtyard_contract_address}/nfts/{token_id}"
        )
    else:
        url = f"{OPENSEA_API_V2}/events/collection/{settings.courtyard_collection_slug}"

    params = {"event_type": "sale", "limit": min(limit, 50)}

    async with httpx.AsyncClient(headers=_build_headers(), timeout=30) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            events = data.get("asset_events", [])
            logger.info("Fetched %d recent sales", len(events))
            return events
        except Exception as e:
            logger.warning("Failed to fetch recent sales: %s", e)
            return []


async def estimate_market_price(
    card_name: str,
    grade: CardGrade,
    token_id: str | None = None,
) -> MarketPrice | None:
    """Estimate the fair market value of a card using OpenSea data.

    Looks at recent sales of the specific token and similar cards in the collection.
    """
    sales = await get_recent_sales(token_id=token_id, limit=20)

    if not sales:
        return None

    # Collect unique token symbols to batch-fetch prices
    from src.scrapers.coingecko import get_multiple_prices

    symbols_needed = set()
    for sale in sales:
        payment = sale.get("payment", {})
        symbol = payment.get("symbol", "USDC")
        symbols_needed.add(symbol.upper())

    crypto_prices = await get_multiple_prices(list(symbols_needed))

    prices = []
    for sale in sales:
        payment = sale.get("payment", {})
        quantity = float(payment.get("quantity", 0))
        decimals = int(payment.get("decimals", 18))
        if quantity > 0:
            token_amount = quantity / (10**decimals)
            symbol = payment.get("symbol", "USDC").upper()
            usd_rate = crypto_prices.get(symbol, 0.0)
            if usd_rate > 0:
                prices.append(token_amount * usd_rate)

    if not prices:
        return None

    avg_price = sum(prices) / len(prices)
    last_price = prices[0] if prices else 0
    floor = min(prices) if prices else 0

    return MarketPrice(
        card_name=card_name,
        grade=grade,
        avg_sale_price_usd=avg_price,
        last_sale_price_usd=last_price,
        floor_price_usd=floor,
        num_recent_sales=len(prices),
        source=DataSource.OPENSEA,
        fetched_at=datetime.now(),
    )
