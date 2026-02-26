"""TCGPlayer price source for Pokemon card market data.

TCGPlayer is the largest marketplace for Pokemon TCG cards.
Uses their public product pages to get market prices by card name and grade.
"""

import logging
import re

import httpx
from bs4 import BeautifulSoup

from src.models import CardGrade, DataSource, MarketPrice
from datetime import datetime

logger = logging.getLogger(__name__)

TCGPLAYER_SEARCH_URL = "https://www.tcgplayer.com/search/pokemon/product"
TCGPLAYER_BASE = "https://www.tcgplayer.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Map our grades to TCGPlayer condition strings
GRADE_TO_CONDITION = {
    CardGrade.PSA_10: "Near Mint",
    CardGrade.PSA_9: "Near Mint",
    CardGrade.PSA_8: "Lightly Played",
    CardGrade.PSA_7: "Moderately Played",
    CardGrade.CGC_10: "Near Mint",
    CardGrade.CGC_9_5: "Near Mint",
    CardGrade.CGC_9: "Near Mint",
    CardGrade.BGS_10: "Near Mint",
    CardGrade.BGS_9_5: "Near Mint",
    CardGrade.BGS_9: "Near Mint",
    CardGrade.UNGRADED: "Near Mint",
    CardGrade.UNKNOWN: "Near Mint",
}


def _normalize_card_name(name: str) -> str:
    """Extract the core card name from a Courtyard-style listing title.

    Courtyard names look like: 'Charizard VMAX 074/073 PSA 10'
    We want: 'Charizard VMAX 074/073'
    """
    # Remove grade info
    cleaned = re.sub(r"\b(PSA|CGC|BGS)\s*\d+\.?\d*\b", "", name, flags=re.IGNORECASE)
    # Remove extra whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _parse_price(text: str) -> float:
    """Extract a numeric price from text like '$12.50'."""
    match = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return 0.0


async def search_card_price(
    card_name: str,
    grade: CardGrade = CardGrade.UNKNOWN,
) -> MarketPrice | None:
    """Search TCGPlayer for a card and extract market price data.

    Scrapes the search results page to find matching cards and their prices.
    """
    query = _normalize_card_name(card_name)
    if not query:
        return None

    params = {
        "q": query,
        "view": "grid",
    }

    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(TCGPLAYER_SEARCH_URL, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Look for product listing cards
            product_cards = soup.select(
                ".search-result, .product-card, [data-testid='search-result'], "
                ".search-result__content"
            )

            if not product_cards:
                # Try broader selectors
                product_cards = soup.select("a[href*='/product/']")

            prices = []
            for card in product_cards[:5]:  # Check top 5 results
                # Look for market price
                price_el = card.select_one(
                    ".product-card__market-price, .search-result__market-price, "
                    "[data-testid='market-price'], .price-point__data"
                )
                if price_el:
                    price = _parse_price(price_el.get_text())
                    if price > 0:
                        prices.append(price)

            if not prices:
                logger.debug("TCGPlayer: no prices found for '%s'", query)
                return None

            avg_price = sum(prices) / len(prices)
            market_price = MarketPrice(
                card_name=card_name,
                grade=grade,
                avg_sale_price_usd=avg_price,
                last_sale_price_usd=prices[0],
                floor_price_usd=min(prices),
                num_recent_sales=len(prices),
                source=DataSource.TCGPLAYER,
                fetched_at=datetime.now(),
            )

            logger.info(
                "TCGPlayer price for '%s': $%.2f (from %d results)",
                query, avg_price, len(prices),
            )
            return market_price

        except httpx.HTTPStatusError as e:
            logger.warning("TCGPlayer search error %s for '%s'", e.response.status_code, query)
            return None
        except Exception as e:
            logger.warning("TCGPlayer error for '%s': %s", query, e)
            return None


async def get_card_detail_price(product_url: str) -> dict:
    """Fetch detailed pricing from a specific TCGPlayer product page.

    Returns a dict with market_price, low_price, and recent sales info.
    """
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(product_url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            result = {}

            # Market price
            market_el = soup.select_one(
                ".price-point__data, [data-testid='market-price'], .market-price"
            )
            if market_el:
                result["market_price"] = _parse_price(market_el.get_text())

            # Low price
            low_el = soup.select_one(
                ".price-point__data--low, [data-testid='low-price'], .low-price"
            )
            if low_el:
                result["low_price"] = _parse_price(low_el.get_text())

            return result

        except Exception as e:
            logger.warning("TCGPlayer detail error: %s", e)
            return {}
