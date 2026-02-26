"""Scraper for Courtyard.io Pokemon card listings."""

import logging
import re

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.models import CardGrade, CardListing, DataSource

logger = logging.getLogger(__name__)

# Known Courtyard marketplace API patterns (discovered via network inspection)
# These may change — the scraper is designed to be resilient to layout changes.
MARKETPLACE_URL = f"{settings.courtyard_base_url}/api/v1/marketplace"
BROWSE_URL = f"{settings.courtyard_base_url}/browse"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html",
}


def _parse_grade(text: str) -> CardGrade:
    """Extract card grade from listing text."""
    text = text.upper().strip()
    patterns = [
        (r"PSA\s*10", CardGrade.PSA_10),
        (r"PSA\s*9", CardGrade.PSA_9),
        (r"PSA\s*8", CardGrade.PSA_8),
        (r"PSA\s*7", CardGrade.PSA_7),
        (r"CGC\s*10", CardGrade.CGC_10),
        (r"CGC\s*9\.5", CardGrade.CGC_9_5),
        (r"CGC\s*9", CardGrade.CGC_9),
        (r"BGS\s*10", CardGrade.BGS_10),
        (r"BGS\s*9\.5", CardGrade.BGS_9_5),
        (r"BGS\s*9", CardGrade.BGS_9),
    ]
    for pattern, grade in patterns:
        if re.search(pattern, text):
            return grade
    return CardGrade.UNKNOWN


def _parse_price(price_text: str) -> float:
    """Extract numeric price from text like '$12.50' or '12.50 USDC'."""
    cleaned = re.sub(r"[^\d.]", "", price_text)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


async def fetch_listings_api(
    category: str = "pokemon",
    limit: int = 100,
    sort_by: str = "price_asc",
) -> list[CardListing]:
    """Try fetching listings from Courtyard's internal API.

    This attempts known API patterns. If the API structure changes,
    it falls back gracefully and logs the issue.
    """
    listings: list[CardListing] = []

    params = {
        "category": category,
        "limit": limit,
        "sort": sort_by,
        "status": "listed",
    }

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        try:
            resp = await client.get(MARKETPLACE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            items = data if isinstance(data, list) else data.get("items", data.get("results", []))

            for item in items:
                name = item.get("name", item.get("title", "Unknown"))
                price = item.get("price", item.get("listing_price", 0))
                token_id = str(item.get("token_id", item.get("id", "")))
                grade_str = item.get("grade", item.get("grading", ""))
                image = item.get("image_url", item.get("image", ""))
                url = item.get("url", f"{settings.courtyard_base_url}/token/{token_id}")

                listing = CardListing(
                    token_id=token_id,
                    name=name,
                    listing_price_usd=float(price) if price else 0.0,
                    grade=_parse_grade(str(grade_str)),
                    image_url=image,
                    listing_url=url,
                    source=DataSource.COURTYARD,
                )
                if listing.listing_price_usd > 0:
                    listings.append(listing)

            logger.info("Fetched %d listings from Courtyard API", len(listings))

        except httpx.HTTPStatusError as e:
            logger.warning("Courtyard API returned %s — falling back to HTML scraping", e.response.status_code)
        except Exception as e:
            logger.warning("Courtyard API error: %s — falling back to HTML scraping", e)

    return listings


async def fetch_listings_html(
    category: str = "pokemon",
    max_pages: int = 5,
) -> list[CardListing]:
    """Scrape listings from Courtyard's browse page as a fallback.

    Parses the HTML to extract card names, prices, grades, and links.
    """
    listings: list[CardListing] = []

    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for page in range(1, max_pages + 1):
            try:
                url = f"{BROWSE_URL}?category={category}&page={page}&sort=price_asc"
                resp = await client.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                # Look for card listing elements — adapt selectors as needed
                card_elements = soup.select(
                    "[data-testid='card-listing'], .card-listing, .listing-card, "
                    ".marketplace-item, article[class*='card']"
                )

                if not card_elements:
                    # Try broader selector
                    card_elements = soup.find_all("a", href=re.compile(r"/token/\d+"))

                for el in card_elements:
                    name_el = el.select_one(
                        "[data-testid='card-name'], .card-name, h3, h4, .title"
                    )
                    price_el = el.select_one(
                        "[data-testid='card-price'], .card-price, .price, span[class*='price']"
                    )

                    name = name_el.get_text(strip=True) if name_el else el.get_text(strip=True)[:80]
                    price_text = price_el.get_text(strip=True) if price_el else "0"

                    href = el.get("href", "")
                    if isinstance(href, list):
                        href = href[0] if href else ""

                    token_match = re.search(r"/token/(\d+)", str(href))
                    token_id = token_match.group(1) if token_match else ""

                    img_el = el.select_one("img")
                    image_url = img_el.get("src", "") if img_el else ""
                    if isinstance(image_url, list):
                        image_url = image_url[0] if image_url else ""

                    listing = CardListing(
                        token_id=token_id,
                        name=name,
                        listing_price_usd=_parse_price(price_text),
                        grade=_parse_grade(name),
                        image_url=image_url,
                        listing_url=f"{settings.courtyard_base_url}{href}" if href else "",
                        source=DataSource.COURTYARD,
                    )
                    if listing.listing_price_usd > 0 and listing.token_id:
                        listings.append(listing)

                logger.info("Scraped page %d: found %d cards", page, len(card_elements))

                if not card_elements:
                    break

            except Exception as e:
                logger.warning("Error scraping page %d: %s", page, e)
                break

    logger.info("Total scraped from HTML: %d listings", len(listings))
    return listings


async def get_listings(category: str = "pokemon", limit: int = 100) -> list[CardListing]:
    """Get card listings from Courtyard — tries API first, falls back to HTML scraping."""
    listings = await fetch_listings_api(category=category, limit=limit)
    if not listings:
        listings = await fetch_listings_html(category=category)
    return listings
