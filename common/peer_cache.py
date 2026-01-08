"""
Persistent peer cache for DNS discovery fallback.

Provides cache-aside pattern for peer discovery, falling back to cached peers
when DNS resolution fails. Cache is persisted to JSON file and refreshed
periodically in background thread.
"""

import json
import logging
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from common.constants import (
    PEER_CACHE_REFRESH_INTERVAL_SECONDS,
    PEER_CACHE_STALE_THRESHOLD_SECONDS,
    DEFAULT_PEER_CACHE_PATH,
    CONTROLLER_SERVICE_NAME,
    CONTROLLER_PORT,
    CHUNKSERVER_SERVICE_NAME,
    CHUNKSERVER_PORT
)

logger = logging.getLogger(__name__)


@dataclass
class PeerCacheEntry:
    """
    Single peer cache entry.

    Attributes:
        address: Peer address in "IP:PORT" format
        last_seen: ISO8601 UTC timestamp of last successful DNS discovery
        dns_hostname: DNS alias used to discover this peer
    """
    address: str
    last_seen: str
    dns_hostname: str


class PeerCache:
    """
    Thread-safe persistent cache for discovered peers.

    Provides fallback mechanism when DNS resolution fails. Cache is updated
    periodically (every 30 seconds) in background thread and persisted to
    JSON file for recovery across restarts.

    Thread-safe for concurrent access from gossip and anti-entropy threads.
    """

    def __init__(self, cache_path: Optional[str] = None):
        """
        Initialize peer cache.

        Args:
            cache_path: Path to JSON cache file (default: /app/data/peer_cache.json)
        """
        self._cache_path = Path(cache_path or DEFAULT_PEER_CACHE_PATH)
        self._cache_lock = threading.RLock()
        self._file_lock = threading.Lock()
        self._refresh_lock = threading.Lock()

        self._cache: Dict[str, Dict] = {}
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._load_from_disk()

        logger.info(f"Peer cache initialized [path={self._cache_path}]")

    def get_cached_peers(self, hostname: str, port: int) -> List[str]:
        """
        Retrieve cached peer addresses for hostname:port.

        Args:
            hostname: DNS alias (e.g., 'controller', 'chunkserver')
            port: Service port number

        Returns:
            List of cached peer addresses in "IP:PORT" format.
            Returns empty list if no cached entries exist.
        """
        cache_key = self._make_cache_key(hostname, port)

        with self._cache_lock:
            if cache_key not in self._cache or not self._cache[cache_key].get('peers'):
                return []

            addresses = [entry['address'] for entry in self._cache[cache_key]['peers']]

            logger.debug(
                f"Cache hit for {hostname}:{port} -> {len(addresses)} peer(s)"
            )

            return addresses

    def update_cache(self, hostname: str, port: int, peers: List[str]) -> None:
        """
        Update cache with fresh DNS results.

        Args:
            hostname: DNS alias (e.g., 'controller', 'chunkserver')
            port: Service port number
            peers: List of peer addresses from DNS resolution
        """
        cache_key = self._make_cache_key(hostname, port)
        now = datetime.now(timezone.utc).isoformat()

        entries = [
            {
                'address': peer,
                'last_seen': now,
                'dns_hostname': hostname
            }
            for peer in peers
        ]

        with self._cache_lock:
            self._cache[cache_key] = {
                'peers': entries,
                'last_refresh': now
            }

        self._save_to_disk()

        logger.debug(
            f"Cache updated for {hostname}:{port} -> {len(peers)} peer(s)"
        )

    def start_background_refresh(self) -> None:
        """
        Start background thread that refreshes cache every 30 seconds.

        Thread is daemon and will be started only once (subsequent calls are no-op).
        Refreshes controller and chunkserver peer lists from DNS and prunes
        stale entries.
        """
        with self._refresh_lock:
            if self._refresh_thread is not None and self._refresh_thread.is_alive():
                return

            self._stop_event.clear()
            self._refresh_thread = threading.Thread(
                target=self._refresh_loop,
                daemon=True,
                name="PeerCacheRefresh"
            )
            self._refresh_thread.start()

            logger.info("Peer cache background refresh thread started")

    def stop_background_refresh(self) -> None:
        """
        Stop background refresh thread.

        Signals thread to stop and waits for clean shutdown.
        """
        self._stop_event.set()

        if self._refresh_thread and self._refresh_thread.is_alive():
            self._refresh_thread.join(timeout=5.0)
            logger.info("Peer cache background refresh thread stopped")

    def _refresh_loop(self) -> None:
        """
        Background thread main loop.

        Refreshes cache every PEER_CACHE_REFRESH_INTERVAL_SECONDS (30s).
        """
        while not self._stop_event.wait(timeout=PEER_CACHE_REFRESH_INTERVAL_SECONDS):
            try:
                self._refresh_all_peer_types()
            except Exception as e:
                logger.error(f"Error in cache refresh loop: {e}", exc_info=True)

    def _refresh_all_peer_types(self) -> None:
        """
        Refresh controller and chunkserver peer lists from DNS.

        Calls DNS discovery, updates cache, and prunes stale entries.
        """
        from common.dns_discovery import _discover_peers_dns_only

        peer_types = [
            (CONTROLLER_SERVICE_NAME, CONTROLLER_PORT),
            (CHUNKSERVER_SERVICE_NAME, CHUNKSERVER_PORT)
        ]

        for hostname, port in peer_types:
            try:
                peers = _discover_peers_dns_only(hostname, port)

                if peers:
                    self.update_cache(hostname, port, peers)
                    logger.debug(
                        f"Cache refresh: {hostname}:{port} -> {len(peers)} peer(s)"
                    )

                self._prune_stale_entries(hostname, port)

            except Exception as e:
                logger.warning(
                    f"Cache refresh failed for {hostname}:{port}: {e}"
                )

    def _prune_stale_entries(self, hostname: str, port: int) -> int:
        """
        Remove peer entries older than PEER_CACHE_STALE_THRESHOLD_SECONDS.

        Args:
            hostname: DNS alias
            port: Service port number

        Returns:
            Number of entries pruned
        """
        cache_key = self._make_cache_key(hostname, port)

        with self._cache_lock:
            if cache_key not in self._cache:
                return 0

            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(seconds=PEER_CACHE_STALE_THRESHOLD_SECONDS)

            original_count = len(self._cache[cache_key].get('peers', []))

            self._cache[cache_key]['peers'] = [
                entry for entry in self._cache[cache_key]['peers']
                if datetime.fromisoformat(entry['last_seen']) > cutoff
            ]

            pruned = original_count - len(self._cache[cache_key]['peers'])

            if pruned > 0:
                logger.info(
                    f"Pruned {pruned} stale peer(s) for {hostname}:{port} "
                    f"(older than {PEER_CACHE_STALE_THRESHOLD_SECONDS}s)"
                )
                self._save_to_disk()

            return pruned

    def _load_from_disk(self) -> bool:
        """
        Load cache from JSON file on startup.

        Returns:
            True if load succeeded, False if file missing or corrupted
        """
        if not self._cache_path.exists():
            logger.debug(f"Cache file not found at {self._cache_path}, starting with empty cache")
            return False

        try:
            with self._file_lock:
                with open(self._cache_path, 'r') as f:
                    data = json.load(f)

            with self._cache_lock:
                self._cache = data

            total_peers = sum(
                len(v.get('peers', []))
                for v in self._cache.values()
            )

            logger.info(
                f"Peer cache loaded from {self._cache_path} "
                f"({total_peers} total peer(s) across {len(self._cache)} type(s))"
            )

            return True

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(
                f"Failed to load peer cache from {self._cache_path}: {e}, "
                "starting with empty cache"
            )
            with self._cache_lock:
                self._cache = {}
            return False

    def _save_to_disk(self) -> None:
        """
        Persist cache to JSON file.

        Creates parent directories if needed. Continues with in-memory cache
        only if save fails (logs error).
        """
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)

            with self._cache_lock:
                data = dict(self._cache)

            with self._file_lock:
                with open(self._cache_path, 'w') as f:
                    json.dump(data, f, indent=2)

            logger.debug(f"Peer cache saved to {self._cache_path}")

        except (IOError, OSError) as e:
            logger.warning(
                f"Failed to save peer cache to {self._cache_path}: {e}, "
                "continuing with in-memory cache only"
            )

    @staticmethod
    def _make_cache_key(hostname: str, port: int) -> str:
        """
        Create cache key from hostname and port.

        Args:
            hostname: DNS alias
            port: Service port number

        Returns:
            Cache key string
        """
        return f"{hostname}:{port}"
