"""EV (Expected Value) calculator for Pokemon card opportunities.

Compares listing prices against fair market values from multiple sources
(OpenSea, TCGPlayer, PriceCharting) to identify cards listed significantly
below their market value.
"""

import logging
from datetime import datetime

from src.config import settings
from src.models import CardListing, EVOpportunity, MarketPrice

logger = logging.getLogger(__name__)


def calculate_confidence(market_price: MarketPrice, num_sources: int = 1) -> float:
    """Calculate a confidence score (0.0-1.0) for the market price estimate.

    Higher confidence when:
    - More recent sales data available
    - Multiple data sources agree (num_sources)
    - Avg and last sale price are close together
    """
    score = 0.0

    # More sales = more confidence
    if market_price.num_recent_sales >= 10:
        score += 0.3
    elif market_price.num_recent_sales >= 5:
        score += 0.2
    elif market_price.num_recent_sales >= 2:
        score += 0.15
    elif market_price.num_recent_sales >= 1:
        score += 0.1

    # Consistency between avg and last sale
    if market_price.last_sale_price_usd > 0 and market_price.avg_sale_price_usd > 0:
        ratio = min(market_price.last_sale_price_usd, market_price.avg_sale_price_usd) / max(
            market_price.last_sale_price_usd, market_price.avg_sale_price_usd
        )
        score += ratio * 0.2  # Up to 0.2 for perfect consistency

    # Floor price exists and is reasonable
    if market_price.floor_price_usd > 0:
        score += 0.1

    # Recency of data
    age_hours = (datetime.now() - market_price.fetched_at).total_seconds() / 3600
    if age_hours < 1:
        score += 0.1
    elif age_hours < 6:
        score += 0.05
    elif age_hours < 24:
        score += 0.025

    # Multiple sources agreeing is a strong signal
    if num_sources >= 3:
        score += 0.3
    elif num_sources >= 2:
        score += 0.2
    elif num_sources == 1:
        score += 0.05

    return min(score, 1.0)


def aggregate_market_prices(prices: list[MarketPrice]) -> MarketPrice | None:
    """Combine market price estimates from multiple sources into one.

    Uses a weighted average: sources with more sales data get more weight.
    The result is a single MarketPrice with combined confidence.
    """
    valid = [p for p in prices if p.avg_sale_price_usd > 0]
    if not valid:
        return None

    if len(valid) == 1:
        return valid[0]

    # Weight by number of recent sales (more data = more trust)
    total_weight = sum(max(p.num_recent_sales, 1) for p in valid)
    weighted_avg = sum(
        p.avg_sale_price_usd * max(p.num_recent_sales, 1) for p in valid
    ) / total_weight

    # Last sale: take the most recent
    most_recent = max(valid, key=lambda p: p.fetched_at)
    last_sale = most_recent.last_sale_price_usd

    # Floor: take the lowest floor across sources
    floors = [p.floor_price_usd for p in valid if p.floor_price_usd > 0]
    floor = min(floors) if floors else 0.0

    total_sales = sum(p.num_recent_sales for p in valid)
    sources_str = ", ".join(p.source.value for p in valid)

    logger.info(
        "Aggregated %d sources (%s): avg=$%.2f, last=$%.2f, floor=$%.2f, sales=%d",
        len(valid), sources_str, weighted_avg, last_sale, floor, total_sales,
    )

    return MarketPrice(
        card_name=valid[0].card_name,
        grade=valid[0].grade,
        avg_sale_price_usd=weighted_avg,
        last_sale_price_usd=last_sale,
        floor_price_usd=floor,
        num_recent_sales=total_sales,
        source=most_recent.source,
        fetched_at=most_recent.fetched_at,
    )


def evaluate_listing(
    listing: CardListing,
    market_price: MarketPrice,
    num_sources: int = 1,
) -> EVOpportunity | None:
    """Evaluate whether a listing is a high EV opportunity.

    Returns an EVOpportunity if the card's market value is significantly
    higher than the listing price (within configured thresholds).
    """
    if listing.listing_price_usd <= 0 or market_price.avg_sale_price_usd <= 0:
        return None

    # Use the more conservative estimate: average of avg and last sale
    if market_price.last_sale_price_usd > 0:
        estimated_value = (market_price.avg_sale_price_usd + market_price.last_sale_price_usd) / 2
    else:
        estimated_value = market_price.avg_sale_price_usd

    ev_ratio = estimated_value / listing.listing_price_usd
    potential_profit = estimated_value - listing.listing_price_usd
    confidence = calculate_confidence(market_price, num_sources=num_sources)

    # Check if within EV thresholds
    if ev_ratio < settings.min_ev_ratio:
        return None

    if ev_ratio > settings.max_ev_ratio:
        # Suspiciously high — might be bad data
        logger.warning(
            "Skipping %s: EV ratio %.1fx seems too high (possible data error)",
            listing.name,
            ev_ratio,
        )
        return None

    opportunity = EVOpportunity(
        listing=listing,
        market_price=market_price,
        ev_ratio=ev_ratio,
        potential_profit_usd=potential_profit,
        confidence=confidence,
    )

    logger.info(
        "Found opportunity: %s — listed $%.2f, market $%.2f, EV %.1fx, confidence %.0f%% (%d sources)",
        listing.name,
        listing.listing_price_usd,
        estimated_value,
        ev_ratio,
        confidence * 100,
        num_sources,
    )

    return opportunity


def rank_opportunities(opportunities: list[EVOpportunity]) -> list[EVOpportunity]:
    """Rank opportunities by a combined score of EV ratio and confidence.

    Best opportunities: high EV ratio + high confidence + high absolute profit.
    """
    def score(opp: EVOpportunity) -> float:
        # Weighted score: EV ratio matters most, confidence is a multiplier
        return opp.ev_ratio * opp.confidence * (1 + opp.potential_profit_usd / 100)

    return sorted(opportunities, key=score, reverse=True)


def filter_opportunities(
    opportunities: list[EVOpportunity],
    min_confidence: float = 0.3,
    min_profit_usd: float = 5.0,
) -> list[EVOpportunity]:
    """Filter out low-confidence or low-profit opportunities."""
    return [
        opp
        for opp in opportunities
        if opp.confidence >= min_confidence and opp.potential_profit_usd >= min_profit_usd
    ]
