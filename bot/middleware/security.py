import hmac
import hashlib
import time
import secrets
from typing import Dict, Any, Callable, Awaitable
from collections import defaultdict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery, Message

from bot.i18n import localize
from bot.logger_mesh import audit_logger
from bot.monitoring import get_metrics


def check_suspicious_patterns(text: str) -> bool:
    """Checking for suspicious patterns"""
    if not text:
        return False

    suspicious = [
        # SQL injection
        r"(union.*select|select.*from|insert.*into|delete.*from)",
        # Script injection
        r"<script|javascript:|onerror=|onclick=",
        # Command injection
        r"(;|\||&&|`|\$\()",
        # Path traversal
        r"\.\.\/|\.\.\\",
        # Excessively long strings (possible DoS attack)
    ]

    # Length check
    if len(text) > 4096:
        return True

    import re
    for pattern in suspicious:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


class SecurityMiddleware(BaseMiddleware):
    """
    Middleware for additional security:
    - CSRF protection for critical operations
    - Callback data signature verification
    - Suspicious activity logging
    """

    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.critical_actions = {
            'buy_', 'pay_', 'delete_', 'admin', 'remove-admin',
            'fill-user-balance', 'set-admin'
        }

    def generate_token(self, user_id: int, action: str) -> str:
        """CSRF token generation"""
        timestamp = str(int(time.time()))
        data = f"{user_id}:{action}:{timestamp}"

        signature = hmac.new(
            self.secret_key.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()

        return f"{data}:{signature}"

    def verify_token(self, token: str, user_id: int, action: str, max_age: int = 3600) -> bool:
        """CSRF token validation"""
        try:
            parts = token.split(':')
            if len(parts) != 4:
                return False

            token_user_id, token_action, timestamp, signature = parts

            # Check user_id and action
            if str(user_id) != token_user_id or action != token_action:
                return False

            # Checking token lifetime
            if int(time.time()) - int(timestamp) > max_age:
                return False

            # Signature verification
            data = f"{token_user_id}:{token_action}:{timestamp}"
            expected_signature = hmac.new(
                self.secret_key.encode(),
                data.encode(),
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)

        except Exception:
            return False

    def is_critical_action(self, callback_data: str) -> bool:
        """Checking whether an action is critical"""
        if not callback_data:
            return False

        return any(
            callback_data.startswith(action)
            for action in self.critical_actions
        )

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        """Basic middleware logic"""

        # Get the user
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

            # Checking critical actions
            if self.is_critical_action(event.data):
                # Logging a critical action
                audit_logger.info(
                    f"Critical action: user={user.id}, action={event.data[:50]}"
                )

                # Check that the callback is not too old (protection against replay attacks)
                if hasattr(event.message, 'date'):
                    message_age = time.time() - event.message.date.timestamp()
                    if message_age > 3600:  # 1 hour
                        await event.answer(
                            localize("middleware.security.session_outdated"),
                            show_alert=True
                        )
                        return None

        # Check for suspicious patterns in the data
        if isinstance(event, CallbackQuery) and event.data:
            if check_suspicious_patterns(event.data):
                audit_logger.warning(
                    f"Suspicious callback data from user {user.id}: {event.data[:100]}"
                )
                # Track suspicious pattern detection
                metrics = get_metrics()
                if metrics:
                    metrics.track_event("security_suspicious_callback", user.id, {
                        "data_preview": event.data[:50],
                        "data_length": len(event.data)
                    })
                await event.answer(localize("middleware.security.invalid_data"), show_alert=True)
                return None

        if isinstance(event, Message) and event.text:
            if check_suspicious_patterns(event.text):
                audit_logger.warning(
                    f"Suspicious message from user {user.id}: {event.text[:100]}"
                )
                # Track suspicious pattern detection
                metrics = get_metrics()
                if metrics:
                    metrics.track_event("security_suspicious_message", user.id, {
                        "text_preview": event.text[:50],
                        "text_length": len(event.text)
                    })
                # We don't block messages, we just log them

        # Pass it on
        return await handler(event, data)


class AuthenticationMiddleware(BaseMiddleware):
    """
    Middleware for authentication and authorization verification
    """

    def __init__(self):
        self.blocked_users: set[int] = set()
        self.admin_cache: Dict[int, tuple[int, float]] = {}  # user_id: (role, timestamp)
        self.cache_ttl = 300  # 5 minutes

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        """Authentication Check"""

        user = None
        if isinstance(event, (Message, CallbackQuery)):
            user = event.from_user

        if not user:
            return await handler(event, data)

        # Checking blocked users (in-memory)
        if user.id in self.blocked_users:
            if isinstance(event, CallbackQuery):
                await event.answer(localize("middleware.security.blocked"), show_alert=True)
            return None

        # Check if user is banned in database
        from bot.database.methods import check_user_cached
        db_user = await check_user_cached(user.id)
        if db_user and db_user.get('is_banned', False):
            ban_reason = db_user.get('ban_reason', '')
            if isinstance(event, CallbackQuery):
                msg = localize("middleware.security.banned", reason=ban_reason) if ban_reason else localize("middleware.security.banned_no_reason")
                await event.answer(msg, show_alert=True)
            elif isinstance(event, Message):
                msg = localize("middleware.security.banned", reason=ban_reason) if ban_reason else localize("middleware.security.banned_no_reason")
                await event.answer(msg)

            audit_logger.warning(f"Banned user {user.id} attempted to interact")
            # Track banned user access attempt
            metrics = get_metrics()
            if metrics:
                metrics.track_event("security_banned_user_access", user.id, {
                    "ban_reason": ban_reason
                })
            return None

        # Check bot
        if user.is_bot:
            audit_logger.warning(f"Bot attempted to interact: {user.id}")
            return None

        # Add user information to the context
        data['user_id'] = user.id
        data['user_name'] = user.first_name

        # Role validation and caching for admin actions
        if isinstance(event, CallbackQuery):
            if event.data and any(event.data.startswith(x) for x in ['admin', 'console', 'broadcast']):
                role = await self.get_user_role_cached(user.id)
                if role <= 1:  # Not admin
                    await event.answer(localize("middleware.security.not_admin"), show_alert=True)
                    audit_logger.warning(f"Unauthorized admin access attempt by user {user.id}")
                    # Track unauthorized access attempt
                    metrics = get_metrics()
                    if metrics:
                        metrics.track_event("security_unauthorized_admin_access", user.id, {
                            "attempted_action": event.data[:50]
                        })
                    return None
                data['user_role'] = role

        return await handler(event, data)

    async def get_user_role_cached(self, user_id: int) -> int:
        """Getting a user role with caching"""
        # Check cache
        if user_id in self.admin_cache:
            role, timestamp = self.admin_cache[user_id]
            if time.time() - timestamp < self.cache_ttl:
                return role

        # Download from DB
        from bot.database.methods import check_role
        role = check_role(user_id) or 0

        # Refresh cache
        self.admin_cache[user_id] = (role, time.time())

        return role

    def block_user(self, user_id: int):
        """Block a user"""
        self.blocked_users.add(user_id)
        audit_logger.info(f"User {user_id} has been blocked")

    def unblock_user(self, user_id: int):
        """Unblock a user"""
        self.blocked_users.discard(user_id)
        audit_logger.info(f"User {user_id} has been unblocked")


class RateLimitMiddleware(BaseMiddleware):
    """
    Middleware for rate limiting to prevent spam and abuse.
    Tracks requests per user and applies limits.
    """

    def __init__(self, max_requests: int = 30, time_window: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed per time window
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        # user_id -> list of timestamps
        self.user_requests: Dict[int, list] = defaultdict(list)
        # user_id -> warning count
        self.warning_count: Dict[int, int] = defaultdict(int)

    def _cleanup_old_requests(self, user_id: int):
        """Remove timestamps older than time_window"""
        current_time = time.time()
        cutoff_time = current_time - self.time_window

        self.user_requests[user_id] = [
            ts for ts in self.user_requests[user_id]
            if ts > cutoff_time
        ]

    def check_rate_limit(self, user_id: int) -> tuple[bool, int]:
        """
        Check if user has exceeded rate limit.

        Args:
            user_id: User ID to check

        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        self._cleanup_old_requests(user_id)

        current_count = len(self.user_requests[user_id])
        remaining = max(0, self.max_requests - current_count)

        if current_count >= self.max_requests:
            return False, 0

        return True, remaining

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        """Rate limit check"""

        user = None
        if isinstance(event, (Message, CallbackQuery)):
            user = event.from_user

        if not user:
            return await handler(event, data)

        user_id = user.id

        # Check rate limit
        is_allowed, remaining = self.check_rate_limit(user_id)

        if not is_allowed:
            # Increment warning count
            self.warning_count[user_id] += 1
            warnings = self.warning_count[user_id]

            # Log rate limit violation
            audit_logger.warning(
                f"Rate limit exceeded by user {user_id} "
                f"(warnings: {warnings}, max: {self.max_requests}/{self.time_window}s)"
            )

            # Track rate limit event
            metrics = get_metrics()
            if metrics:
                metrics.track_event("security_rate_limit_exceeded", user_id, {
                    "warnings": warnings,
                    "max_requests": self.max_requests,
                    "time_window": self.time_window
                })

            # Send warning to user
            if isinstance(event, CallbackQuery):
                await event.answer(
                    localize("middleware.security.rate_limit"),
                    show_alert=True
                )
            elif isinstance(event, Message):
                await event.answer(
                    localize("middleware.security.rate_limit")
                )

            return None

        # Record this request
        self.user_requests[user_id].append(time.time())

        # Add rate limit info to data
        data['rate_limit_remaining'] = remaining

        return await handler(event, data)
