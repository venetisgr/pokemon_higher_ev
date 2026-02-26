"""Shared data models for the Pokemon EV tracker."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CardGrade(Enum):
    PSA_10 = "PSA 10"
    PSA_9 = "PSA 9"
    PSA_8 = "PSA 8"
    PSA_7 = "PSA 7"
    CGC_10 = "CGC 10"
    CGC_9_5 = "CGC 9.5"
    CGC_9 = "CGC 9"
    BGS_10 = "BGS 10"
    BGS_9_5 = "BGS 9.5"
    BGS_9 = "BGS 9"
    UNGRADED = "Ungraded"
    UNKNOWN = "Unknown"

    @classmethod
    def from_string(cls, s: str) -> "CardGrade":
        s_upper = s.strip().upper()
        for member in cls:
            if member.value.upper() == s_upper:
                return member
        return cls.UNKNOWN


class DataSource(Enum):
    COURTYARD = "courtyard"
    OPENSEA = "opensea"
    POLYGON = "polygon"
    TCGPLAYER = "tcgplayer"
    PRICECHARTING = "pricecharting"


@dataclass
class CardListing:
    """A card currently listed for sale on Courtyard."""

    token_id: str
    name: str
    listing_price_usd: float
    grade: CardGrade = CardGrade.UNKNOWN
    set_name: str = ""
    card_number: str = ""
    image_url: str = ""
    listing_url: str = ""
    seller: str = ""
    listed_at: datetime | None = None
    source: DataSource = DataSource.COURTYARD


@dataclass
class MarketPrice:
    """Fair market value data for a card from various sources."""

    card_name: str
    grade: CardGrade
    avg_sale_price_usd: float
    last_sale_price_usd: float = 0.0
    floor_price_usd: float = 0.0
    num_recent_sales: int = 0
    source: DataSource = DataSource.OPENSEA
    fetched_at: datetime = field(default_factory=datetime.now)


@dataclass
class EVOpportunity:
    """A card listing identified as a high EV opportunity."""

    listing: CardListing
    market_price: MarketPrice
    ev_ratio: float  # market_value / listing_price
    potential_profit_usd: float
    confidence: float  # 0.0-1.0 based on data quality
    found_at: datetime = field(default_factory=datetime.now)

    @property
    def ev_multiplier_str(self) -> str:
        return f"{self.ev_ratio:.1f}x"

    @property
    def profit_str(self) -> str:
        return f"${self.potential_profit_usd:.2f}"
