"""Tests for the EV calculator."""

from datetime import datetime

from src.analysis.ev_calculator import (
    calculate_confidence,
    evaluate_listing,
    filter_opportunities,
    rank_opportunities,
)
from src.models import CardGrade, CardListing, DataSource, MarketPrice


def _make_listing(price: float = 10.0, name: str = "Charizard") -> CardListing:
    return CardListing(
        token_id="12345",
        name=name,
        listing_price_usd=price,
        grade=CardGrade.PSA_10,
        source=DataSource.COURTYARD,
    )


def _make_market_price(
    avg: float = 30.0,
    last: float = 28.0,
    sales: int = 5,
) -> MarketPrice:
    return MarketPrice(
        card_name="Charizard",
        grade=CardGrade.PSA_10,
        avg_sale_price_usd=avg,
        last_sale_price_usd=last,
        floor_price_usd=min(avg, last),
        num_recent_sales=sales,
        source=DataSource.OPENSEA,
        fetched_at=datetime.now(),
    )


def test_evaluate_listing_high_ev():
    listing = _make_listing(price=10.0)
    market = _make_market_price(avg=30.0, last=28.0)
    opp = evaluate_listing(listing, market)
    assert opp is not None
    assert opp.ev_ratio >= 2.0
    assert opp.potential_profit_usd > 0


def test_evaluate_listing_low_ev():
    listing = _make_listing(price=25.0)
    market = _make_market_price(avg=30.0, last=28.0)
    opp = evaluate_listing(listing, market)
    # 29/25 = 1.16x — below threshold
    assert opp is None


def test_evaluate_listing_suspiciously_high():
    listing = _make_listing(price=1.0)
    market = _make_market_price(avg=500.0, last=500.0)
    opp = evaluate_listing(listing, market)
    # 500x — above max threshold, should be filtered
    assert opp is None


def test_confidence_high_data():
    mp = _make_market_price(avg=30.0, last=29.0, sales=15)
    conf = calculate_confidence(mp)
    assert conf > 0.5


def test_confidence_low_data():
    mp = _make_market_price(avg=30.0, last=10.0, sales=1)
    conf = calculate_confidence(mp)
    assert conf < 0.5


def test_rank_opportunities():
    listing1 = _make_listing(price=10.0, name="Card A")
    listing2 = _make_listing(price=5.0, name="Card B")
    market1 = _make_market_price(avg=25.0, last=24.0, sales=8)
    market2 = _make_market_price(avg=20.0, last=19.0, sales=12)

    opp1 = evaluate_listing(listing1, market1)
    opp2 = evaluate_listing(listing2, market2)
    assert opp1 is not None
    assert opp2 is not None

    ranked = rank_opportunities([opp1, opp2])
    # Card B at $5 with $20 market should rank higher (3.9x vs 2.45x)
    assert ranked[0].listing.name == "Card B"


def test_filter_low_confidence():
    listing = _make_listing(price=10.0)
    market = _make_market_price(avg=25.0, last=5.0, sales=1)
    opp = evaluate_listing(listing, market)
    if opp:
        filtered = filter_opportunities([opp], min_confidence=0.8)
        assert len(filtered) == 0
