"""Unit tests for peer cache functionality."""

import json
import socket
import tempfile
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from common.peer_cache import PeerCache, PeerCacheEntry
from common.constants import PEER_CACHE_STALE_THRESHOLD_SECONDS


class TestPeerCacheEntry:
    """Test PeerCacheEntry dataclass."""

    def test_peer_cache_entry_creation(self):
        entry = PeerCacheEntry(
            address="10.0.1.5:8001",
            last_seen="2026-01-07T10:30:45.123456Z",
            dns_hostname="controller"
        )

        assert entry.address == "10.0.1.5:8001"
        assert entry.last_seen == "2026-01-07T10:30:45.123456Z"
        assert entry.dns_hostname == "controller"


class TestPeerCacheOperations:
    """Test basic cache operations."""

    def test_cache_stores_peer_entries(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        peers = ["10.0.1.5:8001", "10.0.1.6:8001"]
        cache.update_cache("controller", 8001, peers)

        cached_peers = cache.get_cached_peers("controller", 8001)
        assert cached_peers == peers

    def test_cache_returns_stored_peers(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        cache.update_cache("controller", 8001, ["10.0.1.5:8001"])
        result = cache.get_cached_peers("controller", 8001)

        assert result == ["10.0.1.5:8001"]

    def test_cache_returns_empty_for_missing_hostname(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        result = cache.get_cached_peers("nonexistent", 9999)
        assert result == []

    def test_cache_handles_multiple_hostnames(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        cache.update_cache("controller", 8001, ["10.0.1.5:8001"])
        cache.update_cache("chunkserver", 50051, ["10.0.2.10:50051"])

        controller_peers = cache.get_cached_peers("controller", 8001)
        chunkserver_peers = cache.get_cached_peers("chunkserver", 50051)

        assert controller_peers == ["10.0.1.5:8001"]
        assert chunkserver_peers == ["10.0.2.10:50051"]

    def test_cache_overwrites_existing_entries(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        cache.update_cache("controller", 8001, ["10.0.1.5:8001"])
        cache.update_cache("controller", 8001, ["10.0.1.6:8001", "10.0.1.7:8001"])

        cached_peers = cache.get_cached_peers("controller", 8001)
        assert cached_peers == ["10.0.1.6:8001", "10.0.1.7:8001"]

    def test_cache_handles_empty_peer_list(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        cache.update_cache("controller", 8001, [])
        cached_peers = cache.get_cached_peers("controller", 8001)

        assert cached_peers == []


class TestStaleEntryExpiration:
    """Test stale entry pruning."""

    def test_prune_removes_old_entries(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        old_time = (datetime.now(timezone.utc) - timedelta(seconds=PEER_CACHE_STALE_THRESHOLD_SECONDS + 100)).isoformat()

        cache._cache["controller:8001"] = {
            "peers": [
                {"address": "10.0.1.5:8001", "last_seen": old_time, "dns_hostname": "controller"}
            ],
            "last_refresh": old_time
        }

        pruned = cache._prune_stale_entries("controller", 8001)

        assert pruned == 1
        assert cache.get_cached_peers("controller", 8001) == []

    def test_prune_keeps_fresh_entries(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        fresh_time = datetime.now(timezone.utc).isoformat()

        cache._cache["controller:8001"] = {
            "peers": [
                {"address": "10.0.1.5:8001", "last_seen": fresh_time, "dns_hostname": "controller"}
            ],
            "last_refresh": fresh_time
        }

        pruned = cache._prune_stale_entries("controller", 8001)

        assert pruned == 0
        assert cache.get_cached_peers("controller", 8001) == ["10.0.1.5:8001"]

    def test_prune_handles_empty_cache(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        pruned = cache._prune_stale_entries("controller", 8001)
        assert pruned == 0

    def test_prune_mixed_old_and_fresh_entries(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        old_time = (datetime.now(timezone.utc) - timedelta(seconds=PEER_CACHE_STALE_THRESHOLD_SECONDS + 100)).isoformat()
        fresh_time = datetime.now(timezone.utc).isoformat()

        cache._cache["controller:8001"] = {
            "peers": [
                {"address": "10.0.1.5:8001", "last_seen": old_time, "dns_hostname": "controller"},
                {"address": "10.0.1.6:8001", "last_seen": fresh_time, "dns_hostname": "controller"}
            ],
            "last_refresh": fresh_time
        }

        pruned = cache._prune_stale_entries("controller", 8001)

        assert pruned == 1
        assert cache.get_cached_peers("controller", 8001) == ["10.0.1.6:8001"]


class TestPersistence:
    """Test cache persistence to disk."""

    def test_save_and_load_roundtrip(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache1 = PeerCache(cache_path=str(cache_file))

        cache1.update_cache("controller", 8001, ["10.0.1.5:8001", "10.0.1.6:8001"])
        cache1.update_cache("chunkserver", 50051, ["10.0.2.10:50051"])

        cache2 = PeerCache(cache_path=str(cache_file))

        controller_peers = cache2.get_cached_peers("controller", 8001)
        chunkserver_peers = cache2.get_cached_peers("chunkserver", 50051)

        assert len(controller_peers) == 2
        assert "10.0.1.5:8001" in controller_peers
        assert "10.0.1.6:8001" in controller_peers
        assert chunkserver_peers == ["10.0.2.10:50051"]

    def test_load_handles_missing_file(self, tmp_path):
        cache_file = tmp_path / "nonexistent.json"
        cache = PeerCache(cache_path=str(cache_file))

        result = cache.get_cached_peers("controller", 8001)
        assert result == []

    def test_load_handles_corrupted_json(self, tmp_path):
        cache_file = tmp_path / "corrupted.json"

        with open(cache_file, 'w') as f:
            f.write("{ invalid json content }")

        cache = PeerCache(cache_path=str(cache_file))
        result = cache.get_cached_peers("controller", 8001)

        assert result == []

    def test_save_creates_parent_directories(self, tmp_path):
        cache_file = tmp_path / "nested" / "dir" / "cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        cache.update_cache("controller", 8001, ["10.0.1.5:8001"])

        assert cache_file.exists()
        assert cache_file.parent.exists()


class TestThreadSafety:
    """Test thread safety for concurrent access."""

    def test_concurrent_reads(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        cache.update_cache("controller", 8001, ["10.0.1.5:8001"])

        results = []

        def read_cache():
            for _ in range(100):
                peers = cache.get_cached_peers("controller", 8001)
                results.append(peers)

        threads = [threading.Thread(target=read_cache) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r == ["10.0.1.5:8001"] for r in results)

    def test_concurrent_read_write(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        def writer():
            for i in range(50):
                cache.update_cache("controller", 8001, [f"10.0.1.{i}:8001"])
                time.sleep(0.001)

        def reader():
            for _ in range(50):
                cache.get_cached_peers("controller", 8001)
                time.sleep(0.001)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_refresh_thread_starts_once(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        cache.start_background_refresh()
        thread1 = cache._refresh_thread

        cache.start_background_refresh()
        thread2 = cache._refresh_thread

        assert thread1 is thread2
        assert thread1.is_alive()

        cache.stop_background_refresh()


class TestFallbackIntegration:
    """Test integration with DNS discovery fallback."""

    def test_background_refresh_thread_lifecycle(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        cache.start_background_refresh()
        assert cache._refresh_thread is not None
        assert cache._refresh_thread.is_alive()

        cache.stop_background_refresh()
        time.sleep(0.5)

        assert not cache._refresh_thread.is_alive()


class TestCacheKeyGeneration:
    """Test cache key generation."""

    def test_make_cache_key(self):
        key = PeerCache._make_cache_key("controller", 8001)
        assert key == "controller:8001"

    def test_different_ports_different_keys(self):
        key1 = PeerCache._make_cache_key("controller", 8000)
        key2 = PeerCache._make_cache_key("controller", 8001)
        assert key1 != key2

    def test_different_hostnames_different_keys(self):
        key1 = PeerCache._make_cache_key("controller", 8001)
        key2 = PeerCache._make_cache_key("chunkserver", 8001)
        assert key1 != key2


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_update_cache_with_duplicate_peers(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        peers = ["10.0.1.5:8001", "10.0.1.5:8001", "10.0.1.6:8001"]
        cache.update_cache("controller", 8001, peers)

        cached_peers = cache.get_cached_peers("controller", 8001)
        assert cached_peers == peers

    def test_cache_persists_across_instances(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"

        cache1 = PeerCache(cache_path=str(cache_file))
        cache1.update_cache("controller", 8001, ["10.0.1.5:8001"])
        del cache1

        cache2 = PeerCache(cache_path=str(cache_file))
        cached_peers = cache2.get_cached_peers("controller", 8001)

        assert cached_peers == ["10.0.1.5:8001"]

    def test_cache_handles_special_characters_in_hostname(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = PeerCache(cache_path=str(cache_file))

        cache.update_cache("service-name_v2", 8001, ["10.0.1.5:8001"])
        cached_peers = cache.get_cached_peers("service-name_v2", 8001)

        assert cached_peers == ["10.0.1.5:8001"]


@pytest.fixture
def tmp_path():
    """Provide temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
