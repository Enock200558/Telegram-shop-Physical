import logging
from datetime import datetime
from typing import Optional
import pytz
from pytz.exceptions import UnknownTimeZoneError

logger = logging.getLogger(__name__)

# Cache for timezone to avoid DB queries on every log entry
_cached_timezone: Optional[str] = None
_cached_tz_object: Optional[pytz.tzinfo.BaseTzInfo] = None


def get_timezone() -> str:
    """
    Get the configured timezone from bot_settings.

    Returns:
        Timezone string (e.g., "UTC", "Europe/Moscow")
        Falls back to "UTC" if not found in database.
    """
    global _cached_timezone

    if _cached_timezone is not None:
        return _cached_timezone

    # Import here to avoid circular imports
    from bot.database.methods.read import get_bot_setting

    try:
        timezone_str = get_bot_setting('timezone', default='UTC', value_type=str)
        # Validate timezone
        try:
            pytz.timezone(timezone_str)
            _cached_timezone = timezone_str
            logger.debug(f"Timezone loaded from database: {timezone_str}")
        except UnknownTimeZoneError:
            logger.warning(f"Invalid timezone '{timezone_str}' in database, falling back to UTC")
            _cached_timezone = "UTC"
    except Exception as e:
        # This can happen if database tables don't exist yet
        # Just use UTC as default and don't log error (normal on first startup)
        logger.debug(f"Could not read timezone from database (this is normal on first startup): {e}")
        _cached_timezone = "UTC"

    return _cached_timezone


def get_timezone_object() -> pytz.tzinfo.BaseTzInfo:
    """
    Get the pytz timezone object.

    Returns:
        pytz timezone object for the configured timezone
    """
    global _cached_tz_object

    if _cached_tz_object is not None:
        return _cached_tz_object

    timezone_str = get_timezone()
    _cached_tz_object = pytz.timezone(timezone_str)
    return _cached_tz_object


def get_localized_time() -> datetime:
    """
    Get current time in the configured timezone.

    Returns:
        Timezone-aware datetime object in the configured timezone
    """
    tz = get_timezone_object()
    return datetime.now(tz)


def reload_timezone() -> None:
    """
    Reload timezone from database, clearing the cache.

    This function should be called when timezone setting is updated
    to apply changes without restarting the bot (hot reload).
    """
    global _cached_timezone, _cached_tz_object

    _cached_timezone = None
    _cached_tz_object = None

    # Force reload
    new_timezone = get_timezone()
    logger.info(f"Timezone reloaded: {new_timezone}")


def validate_timezone(tz: str) -> bool:
    """
    Validate if a timezone string is valid.

    Args:
        tz: Timezone string to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        pytz.timezone(tz)
        return True
    except UnknownTimeZoneError:
        return False
