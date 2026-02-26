# Pokemon EV Tracker

Track Pokemon cards on [Courtyard.io](https://courtyard.io) that are listed significantly below their market value (2-3x+ EV opportunities). Get Discord alerts when undervalued cards appear.

## How it works

1. **Scrapes Courtyard.io** for active Pokemon card listings (API + HTML fallback)
2. **Fetches market data** from OpenSea API for comparable sales and floor prices
3. **Reads on-chain data** from the Polygon blockchain (token metadata, ownership)
4. **Calculates EV** by comparing listing price vs fair market value
5. **Alerts via Discord** when a card is listed at 2-3x below market value

---

## Getting Started (Step by Step)

### Prerequisites

- **Python 3.10+** — check with `python3 --version`
- **pip** — comes with Python, check with `pip --version`
- **git** — to clone the repo

### Step 1: Clone the repository

```bash
git clone https://github.com/venetisgr/pokemon_higher_ev.git
cd pokemon_higher_ev
```

### Step 2: Create a virtual environment

```bash
python3 -m venv venv

# Activate it:
# macOS / Linux:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt.

### Step 3: Install dependencies

```bash
# Install the project and all dependencies
pip install -e ".[dev]"
```

This installs:
- `httpx` — async HTTP client for scraping
- `beautifulsoup4` — HTML parsing fallback
- `web3` — Polygon blockchain interaction
- `pydantic` / `pydantic-settings` — config and data validation
- `rich` — pretty terminal output (tables, colors)
- `click` — CLI framework
- `apscheduler` — task scheduling
- `discord-webhook` — Discord notifications
- `pytest` / `ruff` — testing and linting (dev only)

### Step 4: Configure environment variables

```bash
cp .env.example .env
```

Now open `.env` in your editor and fill in your keys:

```env
# REQUIRED — Discord webhook for alerts
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN

# REQUIRED — OpenSea API key for market price data
OPENSEA_API_KEY=your_key_here

# OPTIONAL — Polygon RPC (default public endpoint works, but is rate-limited)
POLYGON_RPC_URL=https://polygon-rpc.com

# OPTIONAL — Tweak EV thresholds (defaults shown)
MIN_EV_RATIO=2.0
MAX_EV_RATIO=10.0
SCAN_INTERVAL_SECONDS=300
```

### Step 5: Get your API keys

#### Discord Webhook URL

1. Open Discord and go to the server where you want alerts
2. Go to **Server Settings** > **Integrations** > **Webhooks**
3. Click **New Webhook**
4. Name it "Pokemon EV Tracker", choose a channel, and click **Copy Webhook URL**
5. Paste into `.env` as `DISCORD_WEBHOOK_URL`

#### OpenSea API Key

1. Go to [docs.opensea.io](https://docs.opensea.io/reference/api-keys)
2. Sign up and request an API key
3. Paste into `.env` as `OPENSEA_API_KEY`

#### Polygon RPC URL (optional but recommended)

The default public RPC (`https://polygon-rpc.com`) works but has rate limits. For reliable scanning, get a free endpoint:

1. Sign up at [Alchemy](https://www.alchemy.com/) or [Infura](https://www.infura.io/)
2. Create a new app, select **Polygon** as the network
3. Copy the HTTPS endpoint and paste into `.env` as `POLYGON_RPC_URL`

### Step 6: Verify your setup

```bash
pokemon-ev config
```

Expected output:
```
Current Configuration:
  Discord webhook: configured
  OpenSea API key: configured
  Polygon RPC: https://polygon-rpc.com
  EV threshold: 2.0x - 10.0x
  Scan interval: 300s
  Database: pokemon_ev.db
```

Make sure Discord webhook and OpenSea API key both show **configured**.

---

## Usage

### Run a single scan

```bash
pokemon-ev scan
```

This will:
1. Fetch all active Pokemon card listings from Courtyard
2. Look up each card's market value on OpenSea
3. Calculate the EV ratio (market value / listing price)
4. Display a table of any cards with 2x+ EV
5. Send Discord alerts for each opportunity found

### Run continuous monitoring

```bash
pokemon-ev watch
```

Scans every 5 minutes (configurable via `SCAN_INTERVAL_SECONDS`). Press `Ctrl+C` to stop.

### Enable verbose/debug logging

Add `-v` before any command to see detailed logs:

```bash
pokemon-ev -v scan
pokemon-ev -v watch
```

### View tracker statistics

```bash
pokemon-ev stats
```

Shows: active listings count, total alerts sent, average EV ratio.

### View alert history

```bash
# Last 20 alerts (default)
pokemon-ev history

# Last 50 alerts
pokemon-ev history -n 50
```

### Run as a module (alternative)

If the `pokemon-ev` command isn't available, you can run directly:

```bash
python -m src.cli scan
python -m src.cli watch
python -m src.cli stats
```

---

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_ev_calculator.py
pytest tests/test_db.py

# Lint the code
ruff check src/ tests/
```

---

## Configuration Reference

All settings are configured via environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_WEBHOOK_URL` | _(empty)_ | Discord webhook URL for sending alerts |
| `OPENSEA_API_KEY` | _(empty)_ | OpenSea API key for fetching market data |
| `POLYGON_RPC_URL` | `https://polygon-rpc.com` | Polygon RPC endpoint for on-chain data |
| `MIN_EV_RATIO` | `2.0` | Minimum EV ratio to trigger an alert (2.0 = card is worth 2x its listing) |
| `MAX_EV_RATIO` | `10.0` | Maximum EV ratio (above this is flagged as likely bad data) |
| `SCAN_INTERVAL_SECONDS` | `300` | Seconds between scans in `watch` mode |
| `COURTYARD_COLLECTION_SLUG` | `courtyard-nft` | OpenSea collection slug for Courtyard |
| `COURTYARD_CONTRACT_ADDRESS` | `0x251b...dcad` | Courtyard ERC-721 contract on Polygon |
| `DB_PATH` | `pokemon_ev.db` | Path to the SQLite database file |

---

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

---

## EV Calculation

A card is flagged as high EV when:

- **Market value / listing price >= 2.0x** (configurable via `MIN_EV_RATIO`)
- Market value is estimated from OpenSea recent sales (avg + last sale)
- A **confidence score** (0-100%) weights data quality (number of sales, price consistency, data freshness)
- Alerts are deduplicated — same card won't alert again within 24 hours

---

## Troubleshooting

### `pokemon-ev: command not found`

Make sure you installed with `pip install -e .` and your virtual environment is activated. Alternatively, run `python -m src.cli scan`.

### `Discord webhook: not set`

Your `.env` file is missing `DISCORD_WEBHOOK_URL` or the file isn't in the project root. Run `pokemon-ev config` to check.

### `No listings found`

Courtyard.io may have changed their page structure. Check the logs with `pokemon-ev -v scan` for details. The scraper tries an API call first, then falls back to HTML parsing.

### `Failed to fetch OpenSea listings`

Your `OPENSEA_API_KEY` may be invalid or rate-limited. Verify the key at [docs.opensea.io](https://docs.opensea.io/) and try again after a few minutes.

### Rate limiting

- OpenSea API: ~4 requests/second on the free tier. The scanner adds a 0.5s delay between lookups.
- Polygon RPC: The public endpoint is heavily rate-limited. Use Alchemy or Infura for reliable access.
- Courtyard: No known rate limits, but the scanner is conservative by default.
