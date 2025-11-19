import asyncio
import logging
from datetime import datetime
from sqlalchemy import func

from bot.database import Database
from bot.database.models.main import BitcoinAddress

logger = logging.getLogger(__name__)


class RecoveryManager:
    """Disaster Recovery Manager"""

    def __init__(self, bot):
        self.bot = bot
        self.recovery_tasks = []
        self.running = False

    async def start(self):
        """Starting the recovery system"""
        logger.info("Starting recovery manager...")
        self.running = True

        # Restore interrupted mailings
        self.recovery_tasks.append(
            asyncio.create_task(self._safe_run(self.recover_interrupted_broadcasts()))
        )

        # Periodic status checks
        self.recovery_tasks.append(
            asyncio.create_task(self._safe_run(self.periodic_health_check()))
        )

    async def stop(self):
        """Stopping the recovery system"""
        self.running = False
        for task in self.recovery_tasks:
            task.cancel()
        await asyncio.gather(*self.recovery_tasks, return_exceptions=True)
        logger.info("Recovery manager stopped")

    async def _safe_run(self, coro):
        """Safe startup of coroutine with error handling"""
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Recovery task error: {e}", exc_info=True)

    async def recover_interrupted_broadcasts(self):
        """Restore interrupted mailings"""
        # Loading state from Redis at startup
        try:
            from bot.caching.cache import get_cache_manager

            cache = get_cache_manager()
            if cache:
                broadcast_state = await cache.get("broadcast:interrupted")
                if broadcast_state:
                    logger.info(f"Found interrupted broadcast: {broadcast_state}")
                    # Continue mailing from where left off
                    await self._resume_broadcast(broadcast_state)
        except Exception as e:
            logger.error(f"Error recovering broadcasts: {e}")

    async def _resume_broadcast(self, state: dict):
        """Resuming an interrupted broadcast"""
        try:
            from bot.caching.cache import get_cache_manager

            logger.info(f"Attempting to resume broadcast from state: {state}")

            # Validate state has required fields
            if not all(key in state for key in ['user_ids', 'sent_count', 'message_text']):
                logger.error("Invalid broadcast state, missing required fields")
                return

            user_ids = state['user_ids']
            sent_count = state['sent_count']
            message_text = state['message_text']

            # Calculate remaining users
            remaining_users = user_ids[sent_count:]

            if not remaining_users:
                logger.info("Broadcast already completed, nothing to resume")
                # Clear the interrupted state
                cache = get_cache_manager()
                if cache:
                    await cache.delete("broadcast:interrupted")
                return

            logger.info(f"Resuming broadcast: {len(remaining_users)} users remaining")

            # Import broadcast function
            try:
                from bot.handlers.admin.broadcast_handler import send_broadcast_to_users

                # Resume broadcast for remaining users
                success_count = await send_broadcast_to_users(
                    bot=self.bot,
                    user_ids=remaining_users,
                    message_text=message_text
                )

                logger.info(f"Resumed broadcast completed: {success_count} messages sent")

                # Clear the interrupted state on successful completion
                cache = get_cache_manager()
                if cache:
                    await cache.delete("broadcast:interrupted")
                    await cache.delete("broadcast:state")

            except ImportError:
                logger.error("Could not import broadcast function, cannot resume")
            except Exception as e:
                logger.error(f"Error during broadcast resume: {e}")

        except Exception as e:
            logger.error(f"Failed to resume broadcast: {e}", exc_info=True)

    async def periodic_health_check(self):
        """Periodic system health checks with recovery actions"""
        consecutive_db_failures = 0
        consecutive_redis_failures = 0

        while self.running:
            try:
                # Check database connection
                try:
                    with Database().session() as s:
                        from sqlalchemy import text
                        s.execute(text("SELECT 1"))
                    consecutive_db_failures = 0
                except Exception as e:
                    consecutive_db_failures += 1
                    logger.error(f"Database health check failed (#{consecutive_db_failures}): {e}")

                    # Attempt recovery after 3 consecutive failures
                    if consecutive_db_failures >= 3:
                        logger.warning("Database connection lost, attempting recovery...")
                        await self.recover_database_connection()

                # Check Redis
                try:
                    from bot.caching.cache import get_cache_manager
                    cache = get_cache_manager()
                    if cache:
                        await cache.set("health:check", "ok", ttl=60)
                        consecutive_redis_failures = 0
                except Exception as e:
                    consecutive_redis_failures += 1
                    logger.error(f"Redis health check failed (#{consecutive_redis_failures}): {e}")

                # Check Telegram API
                try:
                    me = await self.bot.get_me()
                    logger.debug(f"Health check passed: Bot @{me.username} is alive")
                except Exception as e:
                    logger.error(f"Telegram API check failed: {e}")

                # Check Bitcoin address pool (every check)
                await self.check_bitcoin_address_pool()

            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)

            # Wait 60 seconds before the next check
            await asyncio.sleep(60)

    async def recover_database_connection(self):
        """Attempt to recover database connection with exponential backoff"""
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4, 8, 16 seconds
                logger.info(f"Database recovery attempt {attempt + 1}/{max_attempts}, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)

                # Try to reconnect
                db = Database()
                with db.session() as s:
                    from sqlalchemy import text
                    s.execute(text("SELECT 1"))

                logger.info("Database connection recovered successfully!")
                return True

            except Exception as e:
                logger.error(f"Database recovery attempt {attempt + 1} failed: {e}")

                if attempt == max_attempts - 1:
                    logger.critical("Database connection recovery failed after all attempts!")
                    # Could trigger critical alert here
                    return False

        return False

    async def check_bitcoin_address_pool(self):
        """Check Bitcoin address pool and alert if low"""
        try:
            with Database().session() as s:
                # Check available Bitcoin addresses using SQLAlchemy ORM
                available = s.query(func.count(BitcoinAddress.address)).filter(
                    BitcoinAddress.is_used == False
                ).scalar()

                if available < 5:
                    logger.critical(f"CRITICAL: Bitcoin address pool critically low! Only {available} addresses available")
                    # Could send notification to admin here
                elif available < 10:
                    logger.warning(f"WARNING: Bitcoin address pool running low: {available} addresses available")

        except Exception as e:
            logger.error(f"Error checking Bitcoin address pool: {e}")


class StateManager:
    """Save state manager for recovery"""

    def __init__(self):
        self.state_file = "data/bot_state.json"

    async def save_broadcast_state(self, user_ids: list, sent_count: int,
                                   message_text: str, start_time: datetime):
        """Saving the mailing status"""
        import json
        from pathlib import Path

        Path("data").mkdir(exist_ok=True)

        state = {
            "user_ids": user_ids,
            "sent_count": sent_count,
            "message_text": message_text,
            "start_time": start_time.isoformat(),
            "timestamp": datetime.now().isoformat()
        }

        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f)

            # Also save in Redis for quick access
            from bot.caching.cache import get_cache_manager
            cache = get_cache_manager()
            if cache:
                await cache.set("broadcast:state", state, ttl=3600)
        except Exception as e:
            logger.error(f"Failed to save broadcast state: {e}")
