"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admin_id: int
    logs_channel_id: str | None
    log_level: str
    hashids_salt: str
    database_url: str
    price_weekly_rub: int
    price_monthly_rub: int
    price_forever_rub: int
    gramads_api_key: str


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required env var: {name}")
    return value


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def load_settings() -> Settings:
    return Settings(
        bot_token=_required("BOT_TOKEN"),
        admin_id=_int("ADMIN_ID", 0),
        logs_channel_id=os.getenv("LOGS_CHANNEL_ID"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        hashids_salt=os.getenv("HASHIDS_SALT", "secret"),
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/database.db"),
        price_weekly_rub=_int("PRICE_WEEKLY_RUB", 100),
        price_monthly_rub=_int("PRICE_MONTHLY_RUB", 150),
        price_forever_rub=_int("PRICE_FOREVER_RUB", 200),
        gramads_api_key=_required("GRAMADS_API_KEY")
    )


settings = load_settings()
