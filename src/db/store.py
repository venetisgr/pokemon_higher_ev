"""SQLite storage for tracking listings, prices, and alert history."""

import json
import logging
import sqlite3
from datetime import datetime

from src.config import settings
from src.models import CardGrade, CardListing, DataSource, EVOpportunity, MarketPrice

logger = logging.getLogger(__name__)


class Database:
    """SQLite database for persisting card data and tracking alert history."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS listings (
                token_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                listing_price_usd REAL NOT NULL,
                grade TEXT DEFAULT 'Unknown',
                set_name TEXT DEFAULT '',
                card_number TEXT DEFAULT '',
                image_url TEXT DEFAULT '',
                listing_url TEXT DEFAULT '',
                seller TEXT DEFAULT '',
                source TEXT DEFAULT 'courtyard',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS market_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_name TEXT NOT NULL,
                grade TEXT NOT NULL,
                avg_sale_price_usd REAL NOT NULL,
                last_sale_price_usd REAL DEFAULT 0,
                floor_price_usd REAL DEFAULT 0,
                num_recent_sales INTEGER DEFAULT 0,
                source TEXT DEFAULT 'opensea',
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_id TEXT NOT NULL,
                card_name TEXT NOT NULL,
                listing_price_usd REAL NOT NULL,
                market_price_usd REAL NOT NULL,
                ev_ratio REAL NOT NULL,
                potential_profit_usd REAL NOT NULL,
                confidence REAL NOT NULL,
                alerted_at TEXT NOT NULL,
                discord_sent INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_listings_active ON listings(is_active);
            CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(listing_price_usd);
            CREATE INDEX IF NOT EXISTS idx_alerts_token ON alerts(token_id);
            CREATE INDEX IF NOT EXISTS idx_market_prices_name ON market_prices(card_name, grade);
        """)
        self.conn.commit()

    def upsert_listing(self, listing: CardListing):
        """Insert or update a card listing."""
        now = datetime.now().isoformat()
        self.conn.execute(
            """
            INSERT INTO listings (token_id, name, listing_price_usd, grade, set_name,
                card_number, image_url, listing_url, seller, source, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(token_id) DO UPDATE SET
                listing_price_usd = excluded.listing_price_usd,
                last_seen_at = excluded.last_seen_at,
                is_active = 1
            """,
            (
                listing.token_id,
                listing.name,
                listing.listing_price_usd,
                listing.grade.value,
                listing.set_name,
                listing.card_number,
                listing.image_url,
                listing.listing_url,
                listing.seller,
                listing.source.value,
                now,
                now,
            ),
        )
        self.conn.commit()

    def save_market_price(self, mp: MarketPrice):
        """Record a market price observation."""
        self.conn.execute(
            """
            INSERT INTO market_prices (card_name, grade, avg_sale_price_usd,
                last_sale_price_usd, floor_price_usd, num_recent_sales, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mp.card_name,
                mp.grade.value,
                mp.avg_sale_price_usd,
                mp.last_sale_price_usd,
                mp.floor_price_usd,
                mp.num_recent_sales,
                mp.source.value,
                mp.fetched_at.isoformat(),
            ),
        )
        self.conn.commit()

    def record_alert(self, opp: EVOpportunity, discord_sent: bool = False):
        """Record that an alert was sent for an opportunity."""
        self.conn.execute(
            """
            INSERT INTO alerts (token_id, card_name, listing_price_usd, market_price_usd,
                ev_ratio, potential_profit_usd, confidence, alerted_at, discord_sent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opp.listing.token_id,
                opp.listing.name,
                opp.listing.listing_price_usd,
                opp.market_price.avg_sale_price_usd,
                opp.ev_ratio,
                opp.potential_profit_usd,
                opp.confidence,
                opp.found_at.isoformat(),
                1 if discord_sent else 0,
            ),
        )
        self.conn.commit()

    def was_recently_alerted(self, token_id: str, hours: int = 24) -> bool:
        """Check if we already alerted for this token recently (avoid spam)."""
        row = self.conn.execute(
            """
            SELECT COUNT(*) as cnt FROM alerts
            WHERE token_id = ? AND alerted_at > datetime('now', ?)
            """,
            (token_id, f"-{hours} hours"),
        ).fetchone()
        return row["cnt"] > 0

    def mark_inactive_listings(self, active_token_ids: set[str]):
        """Mark listings not in the active set as inactive (sold or delisted)."""
        if not active_token_ids:
            return
        placeholders = ",".join("?" for _ in active_token_ids)
        self.conn.execute(
            f"UPDATE listings SET is_active = 0 WHERE token_id NOT IN ({placeholders})",
            list(active_token_ids),
        )
        self.conn.commit()

    def get_active_listings(self) -> list[CardListing]:
        """Get all currently active listings from the database."""
        rows = self.conn.execute(
            "SELECT * FROM listings WHERE is_active = 1 ORDER BY listing_price_usd ASC"
        ).fetchall()
        return [
            CardListing(
                token_id=r["token_id"],
                name=r["name"],
                listing_price_usd=r["listing_price_usd"],
                grade=CardGrade.from_string(r["grade"]),
                set_name=r["set_name"],
                card_number=r["card_number"],
                image_url=r["image_url"],
                listing_url=r["listing_url"],
                seller=r["seller"],
                source=DataSource(r["source"]),
            )
            for r in rows
        ]

    def get_alert_history(self, limit: int = 50) -> list[dict]:
        """Get recent alert history."""
        rows = self.conn.execute(
            "SELECT * FROM alerts ORDER BY alerted_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Get summary statistics."""
        active = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM listings WHERE is_active = 1"
        ).fetchone()
        total_alerts = self.conn.execute("SELECT COUNT(*) as cnt FROM alerts").fetchone()
        avg_ev = self.conn.execute(
            "SELECT AVG(ev_ratio) as avg_ev FROM alerts"
        ).fetchone()
        return {
            "active_listings": active["cnt"],
            "total_alerts": total_alerts["cnt"],
            "avg_ev_ratio": round(avg_ev["avg_ev"] or 0, 2),
        }

    def close(self):
        self.conn.close()
