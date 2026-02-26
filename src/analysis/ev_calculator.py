"""EV (Expected Value) calculator for Pokemon card opportunities.

Compares listing prices against fair market values from multiple sources
to identify cards listed significantly below their market value.
"""

import logging
from datetime import datetime

from src.config import settings
from src.models import CardListing, EVOpportunity, MarketPrice

logger = logging.getLogger(__name__)


def calculate_confidence(market_price: MarketPrice) -> float:
    """Calculate a confidence score (0.0-1.0) for the market price estimate.

    Higher confidence when:
    - More recent sales data available
    - Multiple data sources agree
    - Avg and last sale price are close together
    """
    score = 0.0

    # More sales = more confidence
    if market_price.num_recent_sales >= 10:
        score += 0.4
    elif market_price.num_recent_sales >= 5:
        score += 0.3
    elif market_price.num_recent_sales >= 2:
        score += 0.2
    elif market_price.num_recent_sales >= 1:
        score += 0.1

    # Consistency between avg and last sale
    if market_price.last_sale_price_usd > 0 and market_price.avg_sale_price_usd > 0:
        ratio = min(market_price.last_sale_price_usd, market_price.avg_sale_price_usd) / max(
            market_price.last_sale_price_usd, market_price.avg_sale_price_usd
        )
        score += ratio * 0.3  # Up to 0.3 for perfect consistency

    # Floor price exists and is reasonable
    if market_price.floor_price_usd > 0:
        score += 0.15

    # Recency of data
    age_hours = (datetime.now() - market_price.fetched_at).total_seconds() / 3600
    if age_hours < 1:
        score += 0.15
    elif age_hours < 6:
        score += 0.1
    elif age_hours < 24:
        score += 0.05

    return min(score, 1.0)


def evaluate_listing(
    listing: CardListing,
    market_price: MarketPrice,
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
    confidence = calculate_confidence(market_price)

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
        "Found opportunity: %s — listed $%.2f, market $%.2f, EV %.1fx, confidence %.0f%%",
        listing.name,
        listing.listing_price_usd,
        estimated_value,
        ev_ratio,
        confidence * 100,
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
