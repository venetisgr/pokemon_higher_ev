"""PriceCharting price source for Pokemon card market data.

PriceCharting tracks historical prices for graded Pokemon cards
across multiple marketplaces (eBay, PWCC, etc). Good for PSA/CGC graded cards.
"""

import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from src.models import CardGrade, DataSource, MarketPrice

logger = logging.getLogger(__name__)

PRICECHARTING_SEARCH_URL = "https://www.pricecharting.com/search-products"
PRICECHARTING_BASE = "https://www.pricecharting.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# PriceCharting uses grade-specific pages like /game/charizard-psa-10
GRADE_SUFFIX = {
    CardGrade.PSA_10: "psa-10",
    CardGrade.PSA_9: "psa-9",
    CardGrade.PSA_8: "psa-8",
    CardGrade.PSA_7: "psa-7",
    CardGrade.CGC_10: "cgc-10",
    CardGrade.CGC_9_5: "cgc-9.5",
    CardGrade.CGC_9: "cgc-9",
    CardGrade.BGS_10: "bgs-10",
    CardGrade.BGS_9_5: "bgs-9.5",
    CardGrade.BGS_9: "bgs-9",
}


def _normalize_card_name(name: str) -> str:
    """Strip grade info and normalize for PriceCharting search."""
    cleaned = re.sub(r"\b(PSA|CGC|BGS)\s*\d+\.?\d*\b", "", name, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _parse_price(text: str) -> float:
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
    """Search PriceCharting for a card and extract price data.

    PriceCharting is especially good for graded cards — it tracks
    PSA 10, PSA 9, etc. separately with historical price trends.
    """
    query = _normalize_card_name(card_name)
    grade_str = GRADE_SUFFIX.get(grade, "")
    if grade_str:
        query = f"{query} {grade_str}"

    params = {
        "q": query,
        "type": "pokemon",
    }

    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(PRICECHARTING_SEARCH_URL, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # PriceCharting search results are in a table
            rows = soup.select(
                "#games_table tr, .search-results tr, table.hoverable tr"
            )

            prices = []
            for row in rows[:5]:
                # Look for price cells
                price_cells = row.select("td.price, td[class*='price'], .js-price")
                for cell in price_cells:
                    price = _parse_price(cell.get_text())
                    if price > 0:
                        prices.append(price)
                        break  # One price per row

            if not prices:
                # Try a different selector — PriceCharting may show prices in spans
                price_spans = soup.select("span.price, .js-price, [data-price]")
                for span in price_spans[:10]:
                    price = _parse_price(span.get_text())
                    if price > 0:
                        prices.append(price)

            if not prices:
                logger.debug("PriceCharting: no prices found for '%s'", query)
                return None

            avg_price = sum(prices) / len(prices)
            market_price = MarketPrice(
                card_name=card_name,
                grade=grade,
                avg_sale_price_usd=avg_price,
                last_sale_price_usd=prices[0],
                floor_price_usd=min(prices),
                num_recent_sales=len(prices),
                source=DataSource.PRICECHARTING,
                fetched_at=datetime.now(),
            )

            logger.info(
                "PriceCharting price for '%s': $%.2f (from %d results)",
                query, avg_price, len(prices),
            )
            return market_price

        except httpx.HTTPStatusError as e:
            logger.warning(
                "PriceCharting search error %s for '%s'", e.response.status_code, query
            )
            return None
        except Exception as e:
            logger.warning("PriceCharting error for '%s': %s", query, e)
            return None


async def get_price_history(product_path: str) -> list[dict]:
    """Fetch historical price data from a PriceCharting product page.

    Returns a list of {date, price} dicts for trend analysis.
    """
    url = f"{PRICECHARTING_BASE}{product_path}"

    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            history = []

            # PriceCharting embeds chart data in script tags
            scripts = soup.select("script")
            for script in scripts:
                text = script.get_text()
                if "priceData" in text or "chart" in text.lower():
                    # Extract data points from JavaScript
                    date_price_pairs = re.findall(
                        r"\[(\d+),\s*([\d.]+)\]", text
                    )
                    for timestamp, price in date_price_pairs:
                        history.append({
                            "timestamp": int(timestamp),
                            "price": float(price),
                        })

            logger.info("PriceCharting: found %d historical data points", len(history))
            return history

        except Exception as e:
            logger.warning("PriceCharting history error: %s", e)
            return []
