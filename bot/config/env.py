import os
from abc import ABC
from typing import Final


class EnvKeys(ABC):
    """Secure environment configuration with validation"""

    # Telegram
    TOKEN: Final = os.environ.get('TOKEN')
    OWNER_ID: Final = os.environ.get('OWNER_ID')

    PAY_CURRENCY: Final = os.getenv("PAY_CURRENCY", "USD")
    MIN_AMOUNT: Final = int(os.getenv("MIN_AMOUNT", 20))
    MAX_AMOUNT: Final = int(os.getenv("MAX_AMOUNT", 10_000))

    # Links / UI
    CHANNEL_URL: Final = os.getenv("CHANNEL_URL")
    HELPER_ID: Final = os.getenv("HELPER_ID")
    RULES: Final = os.getenv("RULES")

    # Locale & logs
    BOT_LOCALE: Final = os.getenv("BOT_LOCALE", "en")
    BOT_LOGFILE: Final = os.getenv("BOT_LOGFILE", "logs/bot.log")
    BOT_AUDITFILE: Final = os.getenv("BOT_AUDITFILE", "logs/audit.log")
    LOG_TO_STDOUT: Final = os.getenv("LOG_TO_STDOUT", "1")
    LOG_TO_FILE: Final = os.getenv("LOG_TO_FILE", "1")
    DEBUG: Final = os.getenv("DEBUG", "0")

    # Redis
    REDIS_HOST: Final = os.getenv("REDIS_HOST")
    REDIS_PORT: Final = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: Final = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD: Final = os.getenv("REDIS_PASSWORD")

    # Database (for Docker)
    POSTGRES_DB: Final = os.getenv("POSTGRES_DB")
    POSTGRES_USER: Final = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: Final = os.getenv("POSTGRES_PASSWORD")
    DB_PORT: Final = int(os.getenv("DB_PORT", 5432))
    DB_DRIVER: Final = os.getenv("DB_DRIVER", "postgresql+psycopg2")

    # Monitoring
    MONITORING_HOST: Final = os.getenv("MONITORING_HOST", "localhost")
    MONITORING_PORT: Final = int(os.getenv("MONITORING_PORT", 9090))

    # Database (for manual deploy)
    DATABASE_URL: Final = "postgresql+psycopg2://user:password@localhost:5432/db_name"  # (setup if you deploy manually)
