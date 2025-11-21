import os
from pathlib import Path
from bot.config import EnvKeys


def dsn() -> str:
    if Path("/.dockerenv").exists() or os.getenv("POSTGRES_HOST"):
        # Running in Docker or with separate PostgreSQL env vars
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        user = os.getenv("POSTGRES_USER", "postgres")
        password = os.getenv("POSTGRES_PASSWORD", "")
        database = os.getenv("POSTGRES_DB", "telegram_shop")
        driver = os.getenv("DB_DRIVER", "postgresql+psycopg2")

        return f"{driver}://{user}:{password}@{host}:{port}/{database}"

    # Local development with hardcoded URL
    return EnvKeys.DATABASE_URL