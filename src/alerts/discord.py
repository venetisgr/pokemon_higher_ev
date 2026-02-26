"""Discord webhook alerts for high EV Pokemon card opportunities."""

import logging

import httpx

from src.config import settings
from src.models import EVOpportunity

logger = logging.getLogger(__name__)


def _build_embed(opp: EVOpportunity) -> dict:
    """Build a Discord embed for an EV opportunity alert."""
    # Color based on EV ratio: green for 2x+, gold for 3x+
    if opp.ev_ratio >= 3.0:
        color = 0xFFD700  # Gold
    elif opp.ev_ratio >= 2.5:
        color = 0xFF8C00  # Dark orange
    else:
        color = 0x00FF00  # Green

    fields = [
        {
            "name": "Listing Price",
            "value": f"${opp.listing.listing_price_usd:.2f}",
            "inline": True,
        },
        {
            "name": "Market Value",
            "value": f"${opp.market_price.avg_sale_price_usd:.2f}",
            "inline": True,
        },
        {
            "name": "EV Ratio",
            "value": f"**{opp.ev_multiplier_str}**",
            "inline": True,
        },
        {
            "name": "Potential Profit",
            "value": f"**{opp.profit_str}**",
            "inline": True,
        },
        {
            "name": "Confidence",
            "value": f"{opp.confidence * 100:.0f}%",
            "inline": True,
        },
        {
            "name": "Grade",
            "value": opp.listing.grade.value,
            "inline": True,
        },
    ]

    embed = {
        "title": f"Pokemon Card: {opp.listing.name}",
        "color": color,
        "fields": fields,
        "footer": {"text": f"Token #{opp.listing.token_id} | {opp.market_price.source.value}"},
    }

    if opp.listing.listing_url:
        embed["url"] = opp.listing.listing_url

    if opp.listing.image_url:
        embed["thumbnail"] = {"url": opp.listing.image_url}

    return embed


async def send_alert(opportunity: EVOpportunity) -> bool:
    """Send a Discord webhook alert for a high EV opportunity."""
    if not settings.discord_webhook_url:
        logger.warning("Discord webhook URL not configured — skipping alert")
        return False

    embed = _build_embed(opportunity)
    payload = {
        "username": "Pokemon EV Tracker",
        "embeds": [embed],
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(settings.discord_webhook_url, json=payload)
            resp.raise_for_status()
            logger.info("Sent Discord alert for %s (%.1fx)", opportunity.listing.name, opportunity.ev_ratio)
            return True
        except httpx.HTTPStatusError as e:
            logger.error("Discord webhook error %s: %s", e.response.status_code, e.response.text)
            return False
        except Exception as e:
            logger.error("Failed to send Discord alert: %s", e)
            return False


async def send_batch_alert(opportunities: list[EVOpportunity]) -> int:
    """Send alerts for multiple opportunities. Returns count of successful sends."""
    if not opportunities:
        return 0

    # Send summary first
    summary = (
        f"**Found {len(opportunities)} high EV opportunities!**\n"
        f"Best: {opportunities[0].listing.name} at {opportunities[0].ev_multiplier_str}"
    )

    if settings.discord_webhook_url:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                await client.post(
                    settings.discord_webhook_url,
                    json={"username": "Pokemon EV Tracker", "content": summary},
                )
            except Exception as e:
                logger.warning("Failed to send summary: %s", e)

    # Send individual embeds (Discord limit: 10 embeds per message)
    sent = 0
    for opp in opportunities[:10]:
        if await send_alert(opp):
            sent += 1

    return sent
