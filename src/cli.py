"""CLI interface for the Pokemon EV Tracker."""

import asyncio
import logging
import sys

import click
from rich.console import Console
from rich.logging import RichHandler

from src.config import settings
from src.db.store import Database

console = Console()


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def main(verbose: bool):
    """Pokemon EV Tracker — find undervalued Pokemon cards on Courtyard.io"""
    _setup_logging(verbose)


@main.command()
def scan():
    """Run a single scan for high EV opportunities."""
    from src.tracker import scan_once

    db = Database()
    try:
        opportunities = asyncio.run(scan_once(db))
        if opportunities:
            console.print(f"\n[bold green]Done! Found {len(opportunities)} opportunities.[/]")
        else:
            console.print("\n[yellow]No opportunities found. Try again later.[/]")
    finally:
        db.close()


@main.command()
def watch():
    """Run continuous scanning with alerts."""
    from src.tracker import run_continuous

    db = Database()
    try:
        asyncio.run(run_continuous(db))
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/]")
    finally:
        db.close()


@main.command()
def stats():
    """Show tracker statistics."""
    db = Database()
    try:
        s = db.get_stats()
        console.print(f"[bold]Active listings:[/] {s['active_listings']}")
        console.print(f"[bold]Total alerts:[/] {s['total_alerts']}")
        console.print(f"[bold]Avg EV ratio:[/] {s['avg_ev_ratio']}x")
    finally:
        db.close()


@main.command()
@click.option("-n", "--limit", default=20, help="Number of alerts to show")
def history(limit: int):
    """Show recent alert history."""
    from rich.table import Table

    db = Database()
    try:
        alerts = db.get_alert_history(limit=limit)
        if not alerts:
            console.print("[yellow]No alerts yet.[/]")
            return

        table = Table(title="Alert History")
        table.add_column("Card")
        table.add_column("Listed", justify="right")
        table.add_column("Market", justify="right")
        table.add_column("EV", justify="right")
        table.add_column("Profit", justify="right")
        table.add_column("When")

        for a in alerts:
            table.add_row(
                a["card_name"][:35],
                f"${a['listing_price_usd']:.2f}",
                f"${a['market_price_usd']:.2f}",
                f"{a['ev_ratio']:.1f}x",
                f"${a['potential_profit_usd']:.2f}",
                a["alerted_at"][:16],
            )

        console.print(table)
    finally:
        db.close()


@main.command()
def config():
    """Show current configuration."""
    console.print("[bold]Current Configuration:[/]")
    console.print(f"  Discord webhook: {'configured' if settings.discord_webhook_url else '[red]not set[/]'}")
    console.print(f"  OpenSea API key: {'configured' if settings.opensea_api_key else '[red]not set[/]'}")
    console.print(f"  Polygon RPC: {settings.polygon_rpc_url}")
    console.print(f"  EV threshold: {settings.min_ev_ratio}x - {settings.max_ev_ratio}x")
    console.print(f"  Scan interval: {settings.scan_interval_seconds}s")
    console.print(f"  Database: {settings.db_path}")


if __name__ == "__main__":
    main()
