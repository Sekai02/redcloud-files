"""Integration tests for controller and chunkserver peer synchronization."""

import asyncio
import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from controller.database import get_db_connection, init_database
from controller.gossip.gossip_service import GossipService
from controller.gossip.peer_registry import PeerRegistry
from controller.chunkserver_registry import ChunkserverRegistry
from controller.vector_clock import VectorClock


@pytest.fixture
def test_db(monkeypatch):
    """
    Create a temporary test database for each test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        monkeypatch.setattr("controller.database.DATABASE_PATH", str(db_path))
        monkeypatch.setattr("controller.config.DATABASE_PATH", str(db_path))
        init_database()
        yield db_path


class TestPeerRegistryDatabaseLoading:
    """Test peer registry database loading functionality."""

    @pytest.mark.asyncio
    async def test_load_from_empty_database(self, test_db):
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        
        count = await peer_registry.load_from_database()
        
        assert count == 0
        assert len(peer_registry.peers) == 0

    @pytest.mark.asyncio
    async def test_load_from_database_with_peers(self, test_db):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO controller_nodes (node_id, address, last_seen, vector_clock)
                VALUES (?, ?, ?, ?)
            """, ("node-2", "10.0.1.2:8000", time.time(), "{}"))
            cursor.execute("""
                INSERT INTO controller_nodes (node_id, address, last_seen, vector_clock)
                VALUES (?, ?, ?, ?)
            """, ("node-3", "10.0.1.3:8000", time.time(), "{}"))
            conn.commit()
        
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        count = await peer_registry.load_from_database()
        
        assert count == 2
        assert "node-2" in peer_registry.peers
        assert "node-3" in peer_registry.peers
        assert peer_registry.peers["node-2"]["address"] == "10.0.1.2:8000"

    @pytest.mark.asyncio
    async def test_load_excludes_self(self, test_db):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO controller_nodes (node_id, address, last_seen, vector_clock)
                VALUES (?, ?, ?, ?)
            """, ("node-1", "10.0.1.1:8000", time.time(), "{}"))
            cursor.execute("""
                INSERT INTO controller_nodes (node_id, address, last_seen, vector_clock)
                VALUES (?, ?, ?, ?)
            """, ("node-2", "10.0.1.2:8000", time.time(), "{}"))
            conn.commit()
        
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        count = await peer_registry.load_from_database()
        
        assert count == 1
        assert "node-1" not in peer_registry.peers
        assert "node-2" in peer_registry.peers


class TestPeerRegistryPersistence:
    """Test peer registry database persistence functionality."""

    @pytest.mark.asyncio
    async def test_persist_to_database(self, test_db):
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        
        await peer_registry.add_peer("node-2", "10.0.1.2:8000")
        await peer_registry.add_peer("node-3", "10.0.1.3:8000")
        
        await peer_registry.persist_to_database()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT node_id, address FROM controller_nodes ORDER BY node_id")
            rows = cursor.fetchall()
        
        assert len(rows) == 2
        assert rows[0]["node_id"] == "node-2"
        assert rows[1]["node_id"] == "node-3"

    @pytest.mark.asyncio
    async def test_persist_overwrites_existing(self, test_db):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO controller_nodes (node_id, address, last_seen, vector_clock)
                VALUES (?, ?, ?, ?)
            """, ("node-2", "10.0.1.99:8000", time.time() - 1000, "{}"))
            conn.commit()
        
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        await peer_registry.add_peer("node-2", "10.0.1.2:8000")
        await peer_registry.persist_to_database()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT address FROM controller_nodes WHERE node_id = ?", ("node-2",))
            row = cursor.fetchone()
        
        assert row["address"] == "10.0.1.2:8000"


class TestPeerRegistryTTL:
    """Test peer registry TTL-based cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_stale_peers(self, test_db):
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        
        old_time = time.time() - 200
        recent_time = time.time()
        
        peer_registry.peers["node-2"] = {"address": "10.0.1.2:8000", "last_seen": old_time}
        peer_registry.peers["node-3"] = {"address": "10.0.1.3:8000", "last_seen": recent_time}
        
        removed = await peer_registry.cleanup_stale_peers(120)
        
        assert removed == 1
        assert "node-2" not in peer_registry.peers
        assert "node-3" in peer_registry.peers

    @pytest.mark.asyncio
    async def test_cleanup_no_stale_peers(self, test_db):
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        
        await peer_registry.add_peer("node-2", "10.0.1.2:8000")
        await peer_registry.add_peer("node-3", "10.0.1.3:8000")
        
        removed = await peer_registry.cleanup_stale_peers(120)
        
        assert removed == 0
        assert len(peer_registry.peers) == 2


class TestGossipPeerSynchronization:
    """Test gossip service synchronizing peers to memory."""

    @pytest.mark.asyncio
    async def test_gossip_adds_peer_to_memory(self, test_db):
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        gossip_service = GossipService("node-1", peer_registry)
        
        await gossip_service._store_entity(
            entity_type="controller_peer",
            data={
                "node_id": "node-2",
                "address": "10.0.1.2:8000",
                "last_seen": time.time()
            }
        )
        
        assert "node-2" in peer_registry.peers
        assert peer_registry.peers["node-2"]["address"] == "10.0.1.2:8000"

    @pytest.mark.asyncio
    async def test_gossip_adds_peer_to_database(self, test_db):
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        gossip_service = GossipService("node-1", peer_registry)
        
        await gossip_service._store_entity(
            entity_type="controller_peer",
            data={
                "node_id": "node-2",
                "address": "10.0.1.2:8000",
                "last_seen": time.time()
            }
        )
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT node_id, address FROM controller_nodes WHERE node_id = ?", ("node-2",))
            row = cursor.fetchone()
        
        assert row is not None
        assert row["node_id"] == "node-2"
        assert row["address"] == "10.0.1.2:8000"

    @pytest.mark.asyncio
    async def test_gossip_removes_peer_from_memory(self, test_db):
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        gossip_service = GossipService("node-1", peer_registry)
        
        await peer_registry.add_peer("node-2", "10.0.1.2:8000")
        
        await gossip_service._store_entity(
            entity_type="controller_peer_remove",
            data={"node_id": "node-2"}
        )
        
        assert "node-2" not in peer_registry.peers

    @pytest.mark.asyncio
    async def test_gossip_removes_peer_from_database(self, test_db):
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        gossip_service = GossipService("node-1", peer_registry)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO controller_nodes (node_id, address, last_seen, vector_clock)
                VALUES (?, ?, ?, ?)
            """, ("node-2", "10.0.1.2:8000", time.time(), "{}"))
            conn.commit()
        
        await gossip_service._store_entity(
            entity_type="controller_peer_remove",
            data={"node_id": "node-2"}
        )
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM controller_nodes WHERE node_id = ?", ("node-2",))
            row = cursor.fetchone()
        
        assert row["count"] == 0


class TestChunkserverRegistryLoading:
    """Test chunkserver registry database loading."""

    @pytest.mark.asyncio
    async def test_load_from_empty_database(self, test_db):
        registry = ChunkserverRegistry()
        
        count = await registry.load_from_database()
        
        assert count == 0

    @pytest.mark.asyncio
    async def test_load_from_database_with_servers(self, test_db):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chunkserver_nodes 
                (node_id, address, last_heartbeat, capacity_bytes, used_bytes, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("cs-1", "10.0.2.1:9000", time.time(), 1000000, 500000, "active"))
            cursor.execute("""
                INSERT INTO chunkserver_nodes 
                (node_id, address, last_heartbeat, capacity_bytes, used_bytes, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("cs-2", "10.0.2.2:9000", time.time(), 1000000, 300000, "active"))
            conn.commit()
        
        registry = ChunkserverRegistry()
        count = await registry.load_from_database()
        
        assert count == 2

    @pytest.mark.asyncio
    async def test_cleanup_stale_servers(self, test_db):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chunkserver_nodes 
                (node_id, address, last_heartbeat, capacity_bytes, used_bytes, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("cs-1", "10.0.2.1:9000", time.time() - 200, 1000000, 500000, "active"))
            cursor.execute("""
                INSERT INTO chunkserver_nodes 
                (node_id, address, last_heartbeat, capacity_bytes, used_bytes, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("cs-2", "10.0.2.2:9000", time.time(), 1000000, 300000, "active"))
            conn.commit()
        
        registry = ChunkserverRegistry()
        deleted = await registry.cleanup_stale_servers(60)
        
        assert deleted == 1
        
        servers = await registry.get_healthy_servers()
        assert len(servers) == 1
        assert servers[0]["node_id"] == "cs-2"


class TestConsistencyChecker:
    """Test database-memory consistency checking."""

    @pytest.mark.asyncio
    async def test_consistency_check_syncs_missing_peers(self, test_db):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO controller_nodes (node_id, address, last_seen, vector_clock)
                VALUES (?, ?, ?, ?)
            """, ("node-2", "10.0.1.2:8000", time.time(), "{}"))
            conn.commit()
        
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        gossip_service = GossipService("node-1", peer_registry)
        
        await gossip_service._check_peer_consistency()
        
        assert "node-2" in peer_registry.peers
        assert peer_registry.peers["node-2"]["address"] == "10.0.1.2:8000"

    @pytest.mark.asyncio
    async def test_consistency_check_passes_when_synced(self, test_db):
        peer_registry = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        gossip_service = GossipService("node-1", peer_registry)
        
        await peer_registry.add_peer("node-2", "10.0.1.2:8000")
        await peer_registry.persist_to_database()
        
        await gossip_service._check_peer_consistency()
        
        assert "node-2" in peer_registry.peers


class TestMeshFormation:
    """Test 3-controller mesh network formation."""

    @pytest.mark.asyncio
    async def test_three_controller_mesh_via_gossip(self, test_db):
        peer_registry_1 = PeerRegistry("node-1", "10.0.1.1:8000", "controller")
        peer_registry_2 = PeerRegistry("node-2", "10.0.1.2:8000", "controller")
        peer_registry_3 = PeerRegistry("node-3", "10.0.1.3:8000", "controller")
        
        gossip_service_1 = GossipService("node-1", peer_registry_1)
        gossip_service_2 = GossipService("node-2", peer_registry_2)
        gossip_service_3 = GossipService("node-3", peer_registry_3)
        
        await peer_registry_1.add_peer("node-2", "10.0.1.2:8000")
        
        await gossip_service_2._store_entity(
            entity_type="controller_peer",
            data={"node_id": "node-1", "address": "10.0.1.1:8000", "last_seen": time.time()}
        )
        
        await gossip_service_3._store_entity(
            entity_type="controller_peer",
            data={"node_id": "node-1", "address": "10.0.1.1:8000", "last_seen": time.time()}
        )
        await gossip_service_3._store_entity(
            entity_type="controller_peer",
            data={"node_id": "node-2", "address": "10.0.1.2:8000", "last_seen": time.time()}
        )
        
        assert "node-2" in peer_registry_1.peers
        assert "node-1" in peer_registry_2.peers
        assert "node-1" in peer_registry_3.peers
        assert "node-2" in peer_registry_3.peers
