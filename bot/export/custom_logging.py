import logging
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

# Import timezone manager for timezone-aware logging
from bot.config.timezone import get_localized_time

# Lazy import to avoid circular dependency
def get_metrics_lazy():
    from bot.monitoring.metrics import get_metrics
    return get_metrics()

# Create logs directory if it doesn't exist
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)


# Custom formatter that uses configured timezone from database
class TimezoneFormatter(logging.Formatter):
    """Logging formatter that uses timezone from bot_settings"""

    def formatTime(self, record, datefmt=None):
        """
        Format time using the configured timezone from database.

        Args:
            record: Log record
            datefmt: Date format string (optional)

        Returns:
            Formatted time string
        """
        dt = get_localized_time()
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


def _setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    """
    Setup a logger with rotating file handler

    Args:
        name: Logger name
        log_file: Path to log file
        level: Logging level

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Create rotating file handler (10MB max, keep 5 backups)
    handler = RotatingFileHandler(
        LOGS_DIR / log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )

    # Create formatter with timezone-aware timestamp using TimezoneFormatter
    tz_formatter = TimezoneFormatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S %Z'
    )

    handler.setFormatter(tz_formatter)
    logger.addHandler(handler)

    return logger


# Lazy-initialized loggers (created on first use to avoid database access during import)
_reference_code_logger: Optional[logging.Logger] = None
_orders_logger: Optional[logging.Logger] = None
_changes_logger: Optional[logging.Logger] = None


def _get_reference_code_logger() -> logging.Logger:
    """Get or create reference code logger"""
    global _reference_code_logger
    if _reference_code_logger is None:
        _reference_code_logger = _setup_logger('reference_code', 'reference_code.log')
    return _reference_code_logger


def _get_orders_logger() -> logging.Logger:
    """Get or create orders logger"""
    global _orders_logger
    if _orders_logger is None:
        _orders_logger = _setup_logger('orders', 'orders.log')
    return _orders_logger


def _get_changes_logger() -> logging.Logger:
    """Get or create changes logger"""
    global _changes_logger
    if _changes_logger is None:
        _changes_logger = _setup_logger('changes', 'changes.log')
    return _changes_logger


def initialize_export_loggers() -> None:
    """
    Explicitly initialize all export loggers.
    This can be called after database is ready to ensure loggers are created.
    """
    _get_reference_code_logger()
    _get_orders_logger()
    _get_changes_logger()


def log_reference_code_creation(code: str, created_by: int, created_by_username: str,
                                 expires_at: Optional[datetime], max_uses: Optional[int],
                                 note: Optional[str], is_admin: bool):
    """
    Log reference code creation

    Args:
        code: The reference code
        created_by: Telegram ID of creator
        created_by_username: Username of creator
        expires_at: Expiration datetime
        max_uses: Maximum number of uses
        note: Optional note
        is_admin: Whether this is an admin code
    """
    code_type = "ADMIN" if is_admin else "USER"
    expiry = expires_at.strftime('%Y-%m-%d %H:%M:%S') if expires_at else "NO_EXPIRY"
    uses = str(max_uses) if max_uses else "UNLIMITED"
    note_text = note if note else "NO_NOTE"

    _get_reference_code_logger().info(
        f"CODE_CREATED | Code: {code} | Type: {code_type} | "
        f"Creator: @{created_by_username} (ID: {created_by}) | "
        f"Expires: {expiry} | Max Uses: {uses} | Note: {note_text}"
    )


def log_reference_code_usage(code: str, used_by: int, used_by_username: str,
                             referred_by: int, referred_by_username: str):
    """
    Log reference code usage

    Args:
        code: The reference code used
        used_by: Telegram ID of user who used the code
        used_by_username: Username of user who used the code
        referred_by: Telegram ID of code creator
        referred_by_username: Username of code creator
    """
    _get_reference_code_logger().info(
        f"CODE_USED | Code: {code} | "
        f"Used By: @{used_by_username} (ID: {used_by}) | "
        f"Referred By: @{referred_by_username} (ID: {referred_by})"
    )


def log_reference_code_deactivation(code: str, deactivated_by: int,
                                    deactivated_by_username: str, reason: str):
    """
    Log reference code deactivation

    Args:
        code: The reference code
        deactivated_by: Telegram ID of admin who deactivated
        deactivated_by_username: Username of admin
        reason: Reason for deactivation
    """
    _get_reference_code_logger().info(
        f"CODE_DEACTIVATED | Code: {code} | "
        f"Deactivated By: @{deactivated_by_username} (ID: {deactivated_by}) | "
        f"Reason: {reason}"
    )


def log_order_creation(order_id: int, buyer_id: int, buyer_username: str,
                       items_summary: str, total_price: float, payment_method: str,
                       delivery_address: str, phone_number: str,
                       bitcoin_address: Optional[str] = None, order_code: Optional[str] = None):
    """
    Log order creation

    Args:
        order_id: Order ID
        buyer_id: Buyer's Telegram ID
        buyer_username: Buyer's username
        items_summary: Summary of items purchased (e.g., "Item1 x2, Item2 x1")
        total_price: Total order price
        payment_method: Payment method (bitcoin/cash)
        delivery_address: Delivery address
        phone_number: Phone number
        bitcoin_address: Bitcoin address if applicable
        order_code: Order code (e.g., ECBDJI) if applicable
    """
    btc_info = f" | BTC Address: {bitcoin_address}" if bitcoin_address else ""

    # Use order code if available, otherwise fallback to ID
    identifier = f"Code: {order_code}" if order_code else f"ID: {order_id}"

    _get_orders_logger().info(
        f"ORDER_CREATED | {identifier} | "
        f"Buyer: @{buyer_username} (ID: {buyer_id}) | "
        f"Items: {items_summary} | Total Price: {total_price} | "
        f"Payment: {payment_method} | "
        f"Phone: {phone_number} | Address: {delivery_address}{btc_info}"
    )


def log_order_completion(order_id: int, buyer_id: int, buyer_username: str,
                        items_summary: str, total: float, completed_by: Optional[int] = None,
                        completed_by_username: Optional[str] = None, order_code: Optional[str] = None):
    """
    Log order completion

    Args:
        order_id: Order ID
        buyer_id: Buyer's Telegram ID
        buyer_username: Buyer's username
        items_summary: Summary of all items with quantities (e.g., "lol x 2, item2 x 1")
        total: Order total
        completed_by: Admin who marked as completed (for cash orders)
        completed_by_username: Admin username
        order_code: Order code (e.g., ECBDJI) if applicable
    """
    completer_info = ""
    if completed_by:
        completer_info = f" | Completed By: @{completed_by_username} (ID: {completed_by})"

    # Use order code if available, otherwise fallback to ID
    identifier = f"Code: {order_code}" if order_code else f"ID: {order_id}"

    _get_orders_logger().info(
        f"ORDER_COMPLETED | {identifier} | "
        f"Buyer: @{buyer_username} (ID: {buyer_id}) | "
        f"Items: {items_summary} | Total: {total}{completer_info}"
    )


def log_order_cancellation(order_id: int, buyer_id: int, buyer_username: str,
                           items_summary: str, total: float, reason: str,
                           canceled_by: Optional[int] = None,
                           canceled_by_username: Optional[str] = None,
                           order_code: Optional[str] = None):
    """
    Log order cancellation

    Args:
        order_id: Order ID
        buyer_id: Buyer's Telegram ID
        buyer_username: Buyer's username
        items_summary: Summary of all items with quantities (e.g., "lol x 2, item2 x 1")
        total: Order total
        reason: Reason for cancellation (e.g., "Reservation expired", "Canceled by admin")
        canceled_by: Admin who canceled (for manual cancellations)
        canceled_by_username: Admin username
        order_code: Order code (e.g., ECBDJI) if applicable
    """
    canceler_info = ""
    if canceled_by:
        canceler_info = f" | Canceled By: @{canceled_by_username} (ID: {canceled_by})"

    # Use order code if available, otherwise fallback to ID
    identifier = f"Code: {order_code}" if order_code else f"ID: {order_id}"

    _get_orders_logger().info(
        f"ORDER_CANCELED | {identifier} | "
        f"Buyer: @{buyer_username} (ID: {buyer_id}) | "
        f"Items: {items_summary} | Total: {total} | "
        f"Reason: {reason}{canceler_info}"
    )


def log_customer_info_change(user_id: int, username: str, attribute: str,
                             old_value: str, new_value: str):
    """
    Log customer information changes

    Args:
        user_id: User's Telegram ID
        username: User's username
        attribute: Changed attribute (ADDRESS/PHONE/NOTE)
        old_value: Old value
        new_value: New value
    """
    _get_changes_logger().info(
        f"@{username} (ID: {user_id}) CHANGED {attribute} | "
        f"Old: {old_value} | New: {new_value}"
    )


def log_bonus_payment(user_id: int, username: str, amount: float, total_bonus: float):
    """
    Log reference bonus payment

    Args:
        user_id: User's Telegram ID
        username: User's username
        amount: Bonus amount received
        total_bonus: Total bonus balance
    """
    _get_reference_code_logger().info(
        f"BONUS_PAID | User: @{username} (ID: {user_id}) | "
        f"Amount: {amount} | Total Bonus: {total_bonus}"
    )

    # Track referral bonus payment metrics
    metrics = get_metrics_lazy()
    if metrics:
        metrics.track_event("referral_bonus_paid", user_id, {
            "amount": amount,
            "total_bonus": total_bonus
        })
        metrics.track_conversion("referral_program", "bonus_paid", user_id)


def log_bitcoin_address_assigned(address: str, order_id: int, buyer_id: int,
                                 buyer_username: str, order_code: Optional[str] = None):
    """
    Log Bitcoin address assignment

    Args:
        address: Bitcoin address
        order_id: Order ID
        buyer_id: Buyer's Telegram ID
        buyer_username: Buyer's username
        order_code: Order code (e.g., ECBDJI) if applicable
    """
    # Use order code if available, otherwise fallback to ID
    identifier = f"Code: {order_code}" if order_code else f"ID: {order_id}"

    _get_orders_logger().info(
        f"BTC_ADDRESS_ASSIGNED | Address: {address} | "
        f"Order {identifier} | Buyer: @{buyer_username} (ID: {buyer_id})"
    )


def log_inventory_update(item_name: str, old_stock: int, new_stock: int,
                         updated_by: int, updated_by_username: str, method: str):
    """
    Log inventory updates

    Args:
        item_name: Item name
        old_stock: Old stock count
        new_stock: New stock count
        updated_by: User who updated
        updated_by_username: Username
        method: Update method (CLI/TELEGRAM)
    """
    _get_changes_logger().info(
        f"INVENTORY_UPDATE | Item: {item_name} | "
        f"Old Stock: {old_stock} | New Stock: {new_stock} | "
        f"Updated By: @{updated_by_username} (ID: {updated_by}) | Method: {method}"
    )
