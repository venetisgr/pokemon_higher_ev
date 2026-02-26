"""Main tracker orchestrator — coordinates scraping, analysis, and alerts."""

import asyncio
import logging

from rich.console import Console
from rich.table import Table

from src.alerts.discord import send_alert, send_batch_alert
from src.analysis.ev_calculator import evaluate_listing, filter_opportunities, rank_opportunities
from src.config import settings
from src.db.store import Database
from src.models import EVOpportunity
from src.scrapers.courtyard import get_listings
from src.scrapers.opensea import estimate_market_price

logger = logging.getLogger(__name__)
console = Console()


async def scan_once(db: Database) -> list[EVOpportunity]:
    """Run a single scan cycle: fetch listings, evaluate EV, alert on opportunities."""

    # Step 1: Fetch listings from Courtyard
    console.print("[bold blue]Fetching Courtyard listings...[/]")
    listings = await get_listings(category="pokemon", limit=100)

    if not listings:
        console.print("[yellow]No listings found — check connection or selectors[/]")
        return []

    console.print(f"[green]Found {len(listings)} listings[/]")

    # Step 2: Store listings
    active_ids = set()
    for listing in listings:
        db.upsert_listing(listing)
        active_ids.add(listing.token_id)
    db.mark_inactive_listings(active_ids)

    # Step 3: Evaluate each listing for EV
    console.print("[bold blue]Evaluating market prices...[/]")
    opportunities: list[EVOpportunity] = []

    for listing in listings:
        # Skip if recently alerted
        if db.was_recently_alerted(listing.token_id, hours=24):
            continue

        # Get market price estimate
        market_price = await estimate_market_price(
            card_name=listing.name,
            grade=listing.grade,
            token_id=listing.token_id,
        )

        if not market_price:
            continue

        db.save_market_price(market_price)

        # Evaluate
        opportunity = evaluate_listing(listing, market_price)
        if opportunity:
            opportunities.append(opportunity)

        # Rate limit API calls
        await asyncio.sleep(0.5)

    # Step 4: Rank and filter
    opportunities = filter_opportunities(opportunities)
    opportunities = rank_opportunities(opportunities)

    if not opportunities:
        console.print("[yellow]No high EV opportunities found this scan[/]")
        return []

    console.print(f"[bold green]Found {len(opportunities)} high EV opportunities![/]")

    # Step 5: Display results
    _print_opportunities_table(opportunities)

    # Step 6: Send Discord alerts
    for opp in opportunities:
        discord_sent = await send_alert(opp)
        db.record_alert(opp, discord_sent=discord_sent)

    return opportunities


def _print_opportunities_table(opportunities: list[EVOpportunity]):
    """Print a rich table of opportunities to the console."""
    table = Table(title="High EV Pokemon Cards", show_lines=True)
    table.add_column("Card", style="bold")
    table.add_column("Grade", style="cyan")
    table.add_column("Listed", justify="right", style="red")
    table.add_column("Market", justify="right", style="green")
    table.add_column("EV", justify="right", style="bold yellow")
    table.add_column("Profit", justify="right", style="bold green")
    table.add_column("Conf", justify="right")

    for opp in opportunities[:20]:
        table.add_row(
            opp.listing.name[:40],
            opp.listing.grade.value,
            f"${opp.listing.listing_price_usd:.2f}",
            f"${opp.market_price.avg_sale_price_usd:.2f}",
            opp.ev_multiplier_str,
            opp.profit_str,
            f"{opp.confidence * 100:.0f}%",
        )

    console.print(table)


async def run_continuous(db: Database):
    """Run the tracker in a continuous loop."""
    console.print(
        f"[bold]Starting continuous scan (every {settings.scan_interval_seconds}s)...[/]"
    )

    while True:
        try:
            await scan_once(db)
        except Exception as e:
            logger.error("Scan error: %s", e, exc_info=True)
            console.print(f"[red]Scan error: {e}[/]")

        console.print(
            f"[dim]Next scan in {settings.scan_interval_seconds}s...[/]"
        )
        await asyncio.sleep(settings.scan_interval_seconds)
