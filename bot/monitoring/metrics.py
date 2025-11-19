import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from collections import defaultdict

from bot.logger_mesh import logger


class MetricsCollector:
    """Metrics builder for analytics"""

    def __init__(self):
        # Initializing all attributes
        self.events: Dict[str, int] = defaultdict(int)
        self.timings: Dict[str, List[float]] = defaultdict(list)
        self.errors: Dict[str, int] = defaultdict(int)
        self.conversions: Dict[str, Dict] = {}
        self.start_time = datetime.now()
        self.last_flush = datetime.now()

    def track_event(self, event_name: str, user_id: Optional[int] = None,
                    metadata: Optional[Dict] = None):
        """Event Tracking"""
        self.events[event_name] += 1

        # Saving detailed information for important business events
        important_events = [
            # Order lifecycle
            "order_created", "order_reserved", "order_completed",
            "order_cancelled", "order_expired",
            # Cart operations
            "cart_add", "cart_remove", "cart_view", "cart_clear", "checkout_start",
            # Payment events
            "payment_bitcoin_initiated", "payment_cash_initiated",
            "payment_bonus_applied", "payment_completed",
            # Referral system
            "referral_code_created", "referral_code_used", "referral_bonus_paid",
            # Inventory
            "inventory_reserved", "inventory_released", "inventory_deducted",
            # Shop navigation
            "shop_view", "category_view", "item_view",
            # Admin operations
            "broadcast_started", "broadcast_completed", "user_updated", "shop_updated",
            "admin_role_assigned", "admin_role_revoked", "admin_bonus_granted",
            "shop_stats_viewed", "admin_referral_code_created",
            # Security events
            "security_suspicious_callback", "security_suspicious_message",
            "security_rate_limit_exceeded", "security_unauthorized_admin_access",
            # Cache events
            "cache_hit", "cache_miss", "cache_stats_reported"
        ]

        if event_name in important_events:
            event_data = {
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "metadata": metadata or {}
            }
            self._save_event(event_name, event_data)

    def track_timing(self, operation: str, duration: float):
        """Tracking the time of an operation"""
        self.timings[operation].append(duration)

        # Hold only the last 1000 measurements
        if len(self.timings[operation]) > 1000:
            self.timings[operation] = self.timings[operation][-1000:]

    def track_error(self, error_type: str, error_msg: str = None):
        """Error Tracking"""
        self.errors[error_type] += 1

        if error_msg:
            logger.error(f"Metric error [{error_type}]: {error_msg}")

    def track_conversion(self, funnel: str, step: str, user_id: int):
        """Tracking conversions in the funnel"""
        if funnel not in self.conversions:
            self.conversions[funnel] = defaultdict(set)

        self.conversions[funnel][step].add(user_id)

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Getting a metrics summary"""
        uptime = (datetime.now() - self.start_time).total_seconds()

        # Calculation of average times
        avg_timings = {}
        for op, times in self.timings.items():
            if times:
                avg_timings[op] = {
                    "avg": sum(times) / len(times),
                    "min": min(times),
                    "max": max(times),
                    "count": len(times)
                }

        # Conversion calculation for all funnels
        conversion_rates = {}
        for funnel, steps in self.conversions.items():
            if funnel == "customer_journey":
                # Modern conversion funnel: shop → category → item → cart → checkout → payment → order
                shop_view = len(steps.get("shop_view", set()))
                category_view = len(steps.get("category_view", set()))
                item_view = len(steps.get("item_view", set()))
                cart_add = len(steps.get("cart_add", set()))
                checkout_start = len(steps.get("checkout_start", set()))
                payment_initiated = len(steps.get("payment_initiated", set()))
                order_completed = len(steps.get("order_completed", set()))

                conversion_rates[funnel] = {
                    "shop_to_category": (category_view / shop_view * 100) if shop_view else 0,
                    "category_to_item": (item_view / category_view * 100) if category_view else 0,
                    "item_to_cart": (cart_add / item_view * 100) if item_view else 0,
                    "cart_to_checkout": (checkout_start / cart_add * 100) if cart_add else 0,
                    "checkout_to_payment": (payment_initiated / checkout_start * 100) if checkout_start else 0,
                    "payment_to_order": (order_completed / payment_initiated * 100) if payment_initiated else 0,
                    "total_conversion": (order_completed / shop_view * 100) if shop_view else 0,
                    "users": {
                        "shop_view": shop_view,
                        "category_view": category_view,
                        "item_view": item_view,
                        "cart_add": cart_add,
                        "checkout_start": checkout_start,
                        "payment_initiated": payment_initiated,
                        "order_completed": order_completed
                    }
                }
            elif funnel == "referral_program":
                # Referral funnel
                code_created = len(steps.get("code_created", set()))
                code_used = len(steps.get("code_used", set()))
                bonus_paid = len(steps.get("bonus_paid", set()))

                conversion_rates[funnel] = {
                    "code_usage_rate": (code_used / code_created * 100) if code_created else 0,
                    "bonus_payment_rate": (bonus_paid / code_used * 100) if code_used else 0,
                    "users": {
                        "code_created": code_created,
                        "code_used": code_used,
                        "bonus_paid": bonus_paid
                    }
                }

        return {
            "uptime_seconds": uptime,
            "events": dict(self.events),
            "timings": avg_timings,
            "errors": dict(self.errors),
            "conversions": conversion_rates,
            "timestamp": datetime.now().isoformat()
        }

    def _save_event(self, event_name: str, event_data: Dict):
        """Saving the event for further analysis"""
        try:
            logger.debug(f"Analytics event: {event_name} - {event_data}")
        except Exception as e:
            logger.error(f"Failed to save event to DB: {e}")

    def get_customer_journey_analytics(self) -> Dict[str, Any]:
        """
        Customer Journey Analytics: timing and conversions
        Tracks: time from cart to checkout, abandoned carts, conversion rates
        """
        analytics = {
            "cart_metrics": {
                "total_cart_adds": self.events.get("cart_add", 0),
                "total_checkouts": self.events.get("checkout_start", 0),
                "abandoned_carts": max(0, self.events.get("cart_add", 0) - self.events.get("checkout_start", 0)),
                "cart_to_checkout_rate": (
                    self.events.get("checkout_start", 0) / self.events.get("cart_add", 1) * 100
                ) if self.events.get("cart_add", 0) > 0 else 0
            },
            "order_metrics": {
                "orders_created": self.events.get("order_created", 0),
                "orders_completed": self.events.get("order_completed", 0),
                "orders_cancelled": self.events.get("order_cancelled", 0),
                "orders_expired": self.events.get("order_expired", 0),
                "completion_rate": (
                    self.events.get("order_completed", 0) / self.events.get("order_created", 1) * 100
                ) if self.events.get("order_created", 0) > 0 else 0,
                "cancellation_rate": (
                    self.events.get("order_cancelled", 0) / self.events.get("order_created", 1) * 100
                ) if self.events.get("order_created", 0) > 0 else 0
            },
            "navigation_funnel": {
                "shop_views": self.events.get("shop_view", 0),
                "category_views": self.events.get("category_view", 0),
                "item_views": self.events.get("item_view", 0),
                "items_added_to_cart": self.events.get("cart_add", 0)
            }
        }
        return analytics

    def get_referral_analytics(self) -> Dict[str, Any]:
        """
        Referral Program Analytics
        Tracks: code effectiveness, earnings, ROI
        """
        analytics = {
            "codes_created": self.events.get("referral_code_created", 0),
            "codes_used": self.events.get("referral_code_used", 0),
            "bonuses_paid": self.events.get("referral_bonus_paid", 0),
            "usage_rate": (
                self.events.get("referral_code_used", 0) / self.events.get("referral_code_created", 1) * 100
            ) if self.events.get("referral_code_created", 0) > 0 else 0,
            "bonus_payment_rate": (
                self.events.get("referral_bonus_paid", 0) / self.events.get("referral_code_used", 1) * 100
            ) if self.events.get("referral_code_used", 0) > 0 else 0
        }
        return analytics

    def get_payment_analytics(self) -> Dict[str, Any]:
        """
        Payment Preferences Analytics
        Tracks: Bitcoin vs Cash, bonus usage
        """
        bitcoin_payments = self.events.get("payment_bitcoin_initiated", 0)
        cash_payments = self.events.get("payment_cash_initiated", 0)
        total_payments = bitcoin_payments + cash_payments

        analytics = {
            "payment_methods": {
                "bitcoin": {
                    "count": bitcoin_payments,
                    "percentage": (bitcoin_payments / total_payments * 100) if total_payments > 0 else 0
                },
                "cash": {
                    "count": cash_payments,
                    "percentage": (cash_payments / total_payments * 100) if total_payments > 0 else 0
                },
                "total": total_payments
            },
            "bonus_usage": {
                "bonus_applied_count": self.events.get("payment_bonus_applied", 0),
                "bonus_usage_rate": (
                    self.events.get("payment_bonus_applied", 0) / total_payments * 100
                ) if total_payments > 0 else 0
            },
            "completion": {
                "payments_completed": self.events.get("payment_completed", 0),
                "completion_rate": (
                    self.events.get("payment_completed", 0) / total_payments * 100
                ) if total_payments > 0 else 0
            }
        }
        return analytics

    def get_inventory_analytics(self) -> Dict[str, Any]:
        """
        Inventory Analytics
        Tracks: reservations, releases, deductions
        """
        analytics = {
            "inventory_reserved": self.events.get("inventory_reserved", 0),
            "inventory_released": self.events.get("inventory_released", 0),
            "inventory_deducted": self.events.get("inventory_deducted", 0),
            "reservation_success_rate": (
                self.events.get("inventory_deducted", 0) / self.events.get("inventory_reserved", 1) * 100
            ) if self.events.get("inventory_reserved", 0) > 0 else 0
        }
        return analytics

    def export_to_prometheus(self):
        """Exporting metrics in Prometheus format"""
        lines = []

        # Events
        for event, count in self.events.items():
            # Clearing the event name for Prometheus (replacing invalid characters)
            clean_event = event.replace("-", "_").replace("/", "_").replace(" ", "_")
            lines.append(f'bot_events_total{{event="{clean_event}"}} {count}')

        # Errors
        for error, count in self.errors.items():
            clean_error = error.replace("-", "_").replace("/", "_").replace(" ", "_")
            lines.append(f'bot_errors_total{{type="{clean_error}"}} {count}')

        # Timers
        for op, times in self.timings.items():
            if times:
                avg_time = sum(times) / len(times)
                clean_op = op.replace("-", "_").replace("/", "_").replace(" ", "_")
                lines.append(f'bot_operation_duration_seconds{{operation="{clean_op}"}} {avg_time}')

        # Add uptime
        uptime = (datetime.now() - self.start_time).total_seconds()
        lines.append(f'bot_uptime_seconds {uptime}')

        return "\n".join(lines)


class AnalyticsMiddleware:
    """Middleware for analytics collection"""

    def __init__(self, metrics: MetricsCollector):
        self.metrics = metrics

    async def __call__(self, handler, event, data):
        start_time = time.time()

        # Retrieve event information
        user_id = None
        event_type = None

        try:
            if hasattr(event, 'from_user') and event.from_user:
                user_id = event.from_user.id
        except AttributeError:
            # from_user may not exist or may be deleted
            pass

        # Determine event type - check attributes but handle test mocks properly
        try:
            # Try to access text attribute to see if it exists and has a value
            text_value = getattr(event, 'text', None)
            if text_value is not None and text_value != "":
                event_type = "message"
                if text_value and text_value.startswith('/'):
                    event_type = f"command_{text_value.split()[0][1:]}"
            elif hasattr(event, 'data'):  # CallbackQuery (including data=None)
                event_type = event.data.split('_')[0] if event.data else "unknown"
        except AttributeError:
            # If we can't access text (deleted attribute), check for data
            if hasattr(event, 'data'):
                event_type = event.data.split('_')[0] if event.data else "unknown"

        # Event Tracking
        if event_type:
            self.metrics.track_event(f"bot_{event_type}", user_id)

        try:
            result = await handler(event, data)

            # Run time tracking
            duration = time.time() - start_time
            if event_type:
                self.metrics.track_timing(f"handler_{event_type}", duration)

            return result

        except Exception as e:
            # Tracking errors
            self.metrics.track_error(type(e).__name__, str(e))
            raise


# Global instance of metrics
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics() -> Optional[MetricsCollector]:
    """Getting a global metrics collector"""
    return _metrics_collector


def init_metrics() -> MetricsCollector:
    """Initialization of the metrics collector"""
    global _metrics_collector
    _metrics_collector = MetricsCollector()
    logger.info("Metrics collector initialized")
    return _metrics_collector
