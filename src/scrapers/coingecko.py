"""CoinGecko price oracle for live crypto-to-USD conversion.

Replaces hardcoded ETH/MATIC prices with live market data.
Uses the free CoinGecko API (no key required, 10-30 calls/min).
"""

import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

COINGECKO_API = "https://api.coingecko.com/api/v3"

# Cache prices to avoid hammering the API
_cache: dict[str, tuple[float, float]] = {}  # {coin_id: (price_usd, timestamp)}
CACHE_TTL_SECONDS = 120  # 2 minutes


@dataclass
class CryptoPrice:
    symbol: str
    usd: float
    updated_at: float


# CoinGecko coin IDs for tokens we care about
COIN_IDS = {
    "ETH": "ethereum",
    "WETH": "ethereum",
    "MATIC": "matic-network",
    "POL": "matic-network",
    "USDC": "usd-coin",
    "USDT": "tether",
    "DAI": "dai",
}


def _get_cached(coin_id: str) -> float | None:
    """Return cached price if fresh enough."""
    if coin_id in _cache:
        price, ts = _cache[coin_id]
        if time.time() - ts < CACHE_TTL_SECONDS:
            return price
    return None


async def get_price(symbol: str) -> float:
    """Get the current USD price of a crypto token.

    Returns the price in USD. Falls back to hardcoded defaults
    if the API is unreachable to keep the tracker running.
    """
    symbol = symbol.upper()

    # Stablecoins are always ~$1
    if symbol in ("USDC", "USDT", "DAI"):
        return 1.0

    coin_id = COIN_IDS.get(symbol)
    if not coin_id:
        logger.warning("Unknown token symbol: %s — returning 0", symbol)
        return 0.0

    # Check cache
    cached = _get_cached(coin_id)
    if cached is not None:
        return cached

    # Fetch from CoinGecko
    url = f"{COINGECKO_API}/simple/price"
    params = {"ids": coin_id, "vs_currencies": "usd"}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            price = data.get(coin_id, {}).get("usd", 0.0)
            if price > 0:
                _cache[coin_id] = (price, time.time())
                logger.info("CoinGecko: %s = $%.2f", symbol, price)
                return price

        except Exception as e:
            logger.warning("CoinGecko API error for %s: %s — using fallback", symbol, e)

    # Fallback prices if API fails
    fallbacks = {"ETH": 2500.0, "WETH": 2500.0, "MATIC": 0.50, "POL": 0.50}
    fallback = fallbacks.get(symbol, 0.0)
    logger.warning("Using fallback price for %s: $%.2f", symbol, fallback)
    return fallback


async def get_multiple_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch USD prices for multiple tokens in a single API call."""
    result: dict[str, float] = {}
    coin_ids_to_fetch: list[str] = []
    symbol_to_coin: dict[str, str] = {}

    for symbol in symbols:
        sym = symbol.upper()
        if sym in ("USDC", "USDT", "DAI"):
            result[sym] = 1.0
            continue

        coin_id = COIN_IDS.get(sym)
        if not coin_id:
            result[sym] = 0.0
            continue

        cached = _get_cached(coin_id)
        if cached is not None:
            result[sym] = cached
        else:
            coin_ids_to_fetch.append(coin_id)
            symbol_to_coin[sym] = coin_id

    if not coin_ids_to_fetch:
        return result

    # Batch fetch
    url = f"{COINGECKO_API}/simple/price"
    params = {"ids": ",".join(set(coin_ids_to_fetch)), "vs_currencies": "usd"}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            now = time.time()
            for sym, coin_id in symbol_to_coin.items():
                price = data.get(coin_id, {}).get("usd", 0.0)
                if price > 0:
                    _cache[coin_id] = (price, now)
                    result[sym] = price
                else:
                    result[sym] = await get_price(sym)  # Fallback

            logger.info("CoinGecko batch: fetched %d prices", len(symbol_to_coin))

        except Exception as e:
            logger.warning("CoinGecko batch error: %s — using fallbacks", e)
            for sym in symbol_to_coin:
                result[sym] = await get_price(sym)  # Will use fallback

    return result
