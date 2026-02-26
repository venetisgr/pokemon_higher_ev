"""Tests for the database layer."""

import tempfile
from datetime import datetime

from src.db.store import Database
from src.models import CardGrade, CardListing, DataSource, EVOpportunity, MarketPrice


def _make_db() -> Database:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    return Database(db_path=f.name)


def test_upsert_and_get_listings():
    db = _make_db()
    listing = CardListing(
        token_id="100",
        name="Pikachu",
        listing_price_usd=15.0,
        grade=CardGrade.PSA_9,
        source=DataSource.COURTYARD,
    )
    db.upsert_listing(listing)

    active = db.get_active_listings()
    assert len(active) == 1
    assert active[0].name == "Pikachu"
    assert active[0].listing_price_usd == 15.0
    db.close()


def test_upsert_updates_price():
    db = _make_db()
    listing = CardListing(
        token_id="100",
        name="Pikachu",
        listing_price_usd=15.0,
        grade=CardGrade.PSA_9,
    )
    db.upsert_listing(listing)

    listing.listing_price_usd = 12.0
    db.upsert_listing(listing)

    active = db.get_active_listings()
    assert len(active) == 1
    assert active[0].listing_price_usd == 12.0
    db.close()


def test_mark_inactive():
    db = _make_db()
    for i in range(3):
        db.upsert_listing(
            CardListing(token_id=str(i), name=f"Card {i}", listing_price_usd=10.0)
        )

    db.mark_inactive_listings({"0", "2"})
    active = db.get_active_listings()
    assert len(active) == 2
    assert {a.token_id for a in active} == {"0", "2"}
    db.close()


def test_alert_dedup():
    db = _make_db()
    listing = CardListing(token_id="200", name="Mewtwo", listing_price_usd=20.0)
    market = MarketPrice(
        card_name="Mewtwo",
        grade=CardGrade.PSA_10,
        avg_sale_price_usd=50.0,
        last_sale_price_usd=48.0,
    )
    opp = EVOpportunity(
        listing=listing,
        market_price=market,
        ev_ratio=2.45,
        potential_profit_usd=29.0,
        confidence=0.7,
    )

    assert not db.was_recently_alerted("200")
    db.record_alert(opp, discord_sent=True)
    assert db.was_recently_alerted("200")
    db.close()


def test_stats():
    db = _make_db()
    db.upsert_listing(
        CardListing(token_id="1", name="Bulbasaur", listing_price_usd=5.0)
    )
    stats = db.get_stats()
    assert stats["active_listings"] == 1
    assert stats["total_alerts"] == 0
    db.close()
