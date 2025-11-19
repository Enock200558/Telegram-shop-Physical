import logging
import threading
import time
from pathlib import Path
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from bot.payments.bitcoin import load_bitcoin_addresses_from_file

logger = logging.getLogger(__name__)


class BitcoinAddressFileHandler(FileSystemEventHandler):
    """
    Handler for file system events on btc_addresses.txt
    Implements debouncing to prevent multiple rapid reloads
    """

    def __init__(self, file_path: str, debounce_seconds: float = 2.0):
        """
        Initialize the file handler

        Args:
            file_path: Path to btc_addresses.txt file
            debounce_seconds: Minimum time between reloads (default: 2 seconds)
        """
        super().__init__()
        self.file_path = Path(file_path).resolve()
        self.file_name = self.file_path.name
        self.debounce_seconds = debounce_seconds
        self.last_reload_time = 0
        self._reload_lock = threading.Lock()

        logger.info(f"BitcoinAddressFileHandler initialized for {self.file_path}")

    def on_modified(self, event):
        """
        Called when a file is modified

        Args:
            event: FileSystemEvent object
        """
        # Only process file modification events (not directory events)
        if event.is_directory:
            return

        # Check if this is our target file
        event_path = Path(event.src_path).resolve()
        if event_path != self.file_path:
            return

        # Debounce: check if enough time has passed since last reload
        current_time = time.time()
        with self._reload_lock:
            time_since_last_reload = current_time - self.last_reload_time

            if time_since_last_reload < self.debounce_seconds:
                logger.debug(
                    f"Debouncing file change event (last reload was "
                    f"{time_since_last_reload:.1f}s ago, minimum is {self.debounce_seconds}s)"
                )
                return

            # Update last reload time
            self.last_reload_time = current_time

        # Reload addresses from file
        self._reload_addresses()

    def _reload_addresses(self):
        """
        Reload Bitcoin addresses from file
        This method is called after debouncing
        """
        try:
            logger.info(f"📥 Detected change in {self.file_name}, reloading Bitcoin addresses...")

            loaded_count = load_bitcoin_addresses_from_file()

            if loaded_count > 0:
                logger.info(f"✅ Successfully loaded {loaded_count} new Bitcoin address(es)")
            else:
                logger.info("ℹ️  No new Bitcoin addresses to load")

        except Exception as e:
            logger.error(f"❌ Error reloading Bitcoin addresses: {e}", exc_info=True)


class BitcoinAddressFileWatcher:
    """
    File system watcher for btc_addresses.txt
    Monitors the file for changes and automatically reloads addresses
    """

    def __init__(self, file_path: str = "btc_addresses.txt", debounce_seconds: float = 2.0):
        """
        Initialize the file watcher

        Args:
            file_path: Path to btc_addresses.txt file (default: "btc_addresses.txt")
            debounce_seconds: Minimum time between reloads (default: 2 seconds)
        """
        self.file_path = Path(file_path).resolve()
        self.watch_directory = self.file_path.parent
        self.debounce_seconds = debounce_seconds

        # Create watchdog observer and event handler
        self.observer: Optional[Observer] = None
        self.event_handler: Optional[BitcoinAddressFileHandler] = None

        self._started = False
        self._start_lock = threading.Lock()

        logger.info(f"BitcoinAddressFileWatcher created for {self.file_path}")

    def start(self):
        """
        Start watching the Bitcoin addresses file

        Returns:
            bool: True if started successfully, False if already running
        """
        with self._start_lock:
            if self._started:
                logger.warning("File watcher is already running")
                return False

            # Verify file exists
            if not self.file_path.exists():
                logger.warning(
                    f"Bitcoin addresses file not found at {self.file_path}. "
                    f"Watcher will monitor directory for file creation."
                )

            # Create event handler and observer
            self.event_handler = BitcoinAddressFileHandler(
                str(self.file_path),
                self.debounce_seconds
            )
            self.observer = Observer()

            # Schedule the observer to watch the directory containing the file
            self.observer.schedule(
                self.event_handler,
                str(self.watch_directory),
                recursive=False
            )

            # Start the observer thread
            self.observer.start()
            self._started = True

            logger.info(
                f"🔍 File watcher started for {self.file_path.name} "
                f"(debounce: {self.debounce_seconds}s)"
            )
            return True

    def stop(self, timeout: float = 5.0):
        """
        Stop watching the Bitcoin addresses file

        Args:
            timeout: Maximum time to wait for observer thread to stop (seconds)

        Returns:
            bool: True if stopped successfully, False if not running
        """
        with self._start_lock:
            if not self._started:
                logger.warning("File watcher is not running")
                return False

            if self.observer:
                logger.info("Stopping file watcher...")
                self.observer.stop()
                self.observer.join(timeout=timeout)

                # Check if thread stopped
                if self.observer.is_alive():
                    logger.warning(
                        f"File watcher thread did not stop within {timeout}s timeout"
                    )
                else:
                    logger.info("✅ File watcher stopped successfully")

                self.observer = None

            self.event_handler = None
            self._started = False
            return True

    def is_running(self) -> bool:
        """
        Check if the file watcher is currently running

        Returns:
            bool: True if running, False otherwise
        """
        return self._started and self.observer is not None and self.observer.is_alive()

    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()
        return False


# Global singleton instance
_watcher_instance: Optional[BitcoinAddressFileWatcher] = None
_watcher_lock = threading.Lock()


def get_file_watcher() -> BitcoinAddressFileWatcher:
    """
    Get the global file watcher instance (singleton pattern)

    Returns:
        BitcoinAddressFileWatcher: The global file watcher instance
    """
    global _watcher_instance

    with _watcher_lock:
        if _watcher_instance is None:
            _watcher_instance = BitcoinAddressFileWatcher()
        return _watcher_instance


def start_file_watcher() -> bool:
    """
    Start the global file watcher instance

    Returns:
        bool: True if started successfully
    """
    watcher = get_file_watcher()
    return watcher.start()


def stop_file_watcher(timeout: float = 5.0) -> bool:
    """
    Stop the global file watcher instance

    Args:
        timeout: Maximum time to wait for watcher to stop

    Returns:
        bool: True if stopped successfully
    """
    global _watcher_instance

    with _watcher_lock:
        if _watcher_instance is not None:
            result = _watcher_instance.stop(timeout)
            _watcher_instance = None
            return result
        return False
