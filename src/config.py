from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Discord
    discord_webhook_url: str = ""

    # OpenSea
    opensea_api_key: str = ""

    # Polygon
    polygon_rpc_url: str = "https://polygon-rpc.com"

    # Courtyard
    courtyard_collection_slug: str = "courtyard-nft"
    courtyard_contract_address: str = "0x251be3a17af4892035c37ebf5890f4a4d889dcad"
    courtyard_base_url: str = "https://courtyard.io"

    # EV thresholds
    min_ev_ratio: float = 2.0
    max_ev_ratio: float = 10.0

    # Scanning
    scan_interval_seconds: int = 300

    # Database
    db_path: str = "pokemon_ev.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
