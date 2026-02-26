# Pokemon EV Tracker

Track Pokemon cards on [Courtyard.io](https://courtyard.io) that are listed significantly below their market value (2-3x+ EV opportunities).

## How it works

1. **Scrapes Courtyard.io** for active Pokemon card listings (API + HTML fallback)
2. **Fetches market data** from OpenSea API for comparable sales and floor prices
3. **Reads on-chain data** from the Polygon blockchain (token metadata, ownership)
4. **Calculates EV** by comparing listing price vs fair market value
5. **Alerts via Discord** when a card is listed at 2-3x below market value

## Setup

```bash
# Clone and install
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your API keys and Discord webhook URL
```

### Required API keys

| Key | Source | Required |
|-----|--------|----------|
| `DISCORD_WEBHOOK_URL` | Discord server settings > Integrations | For alerts |
| `OPENSEA_API_KEY` | [OpenSea API](https://docs.opensea.io/) | For market data |
| `POLYGON_RPC_URL` | [Alchemy](https://alchemy.com) / [Infura](https://infura.io) | For on-chain data |

## Usage

```bash
# Single scan
pokemon-ev scan

# Continuous monitoring
pokemon-ev watch

# View stats
pokemon-ev stats

# Alert history
pokemon-ev history -n 50

# Show config
pokemon-ev config
```

## Architecture

```
src/
├── scrapers/
│   ├── courtyard.py    # Courtyard.io scraper (API + HTML)
│   └── opensea.py      # OpenSea API client for market data
├── blockchain/
│   └── polygon.py      # Polygon on-chain reader (ERC-721)
├── analysis/
│   └── ev_calculator.py # EV calculation and opportunity ranking
├── alerts/
│   └── discord.py      # Discord webhook notifications
├── db/
│   └── store.py        # SQLite persistence layer
├── models.py           # Shared data models
├── config.py           # Settings (from .env)
├── tracker.py          # Main orchestrator
└── cli.py              # CLI interface
```

## EV Calculation

A card is flagged as high EV when:

- **Market value / listing price >= 2.0x** (configurable via `MIN_EV_RATIO`)
- Market value is estimated from OpenSea recent sales (avg + last sale)
- A **confidence score** (0-100%) weights data quality (number of sales, price consistency, data freshness)
- Alerts are deduplicated — same card won't alert again within 24 hours
