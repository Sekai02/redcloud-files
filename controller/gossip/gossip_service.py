"""Gossip service for state synchronization between controllers."""

import asyncio
import aiohttp
import json
import time
from typing import List, Dict, Any, Optional
from common.logging_config import get_logger
from controller.vector_clock import VectorClock
from controller.conflict_resolver import ConflictResolver
from controller.database import get_db_connection
from controller.gossip.peer_registry import PeerRegistry

logger = get_logger(__name__)


class GossipService:
    """
    Implements gossip protocol for state synchronization between controllers.

    Responsibilities:
    - Periodically exchange state with random peers
    - Push updates to peers
    - Pull updates from peers
    - Track which nodes have received which updates
    """

    def __init__(
        self,
        node_id: str,
        peer_registry: PeerRegistry,
        gossip_interval: int = 5,
        anti_entropy_interval: int = 30,
        fanout: int = 2
    ):
        self.node_id = node_id
        self.peer_registry = peer_registry
        self.gossip_interval = gossip_interval
        self.anti_entropy_interval = anti_entropy_interval
        self.fanout = fanout
        self.running = False
        self.vector_clock = VectorClock({node_id: 0})

    async def start(self):
        """Start gossip background tasks"""
        self.running = True
        asyncio.create_task(self._gossip_loop())
        asyncio.create_task(self._anti_entropy_loop())
        logger.info("Gossip service started")

    async def stop(self):
        """Stop gossip background tasks"""
        self.running = False
        logger.info("Gossip service stopped")

    async def _gossip_loop(self):
        """Push-based gossip: send updates to random peers"""
        while self.running:
            try:
                updates = await self._get_pending_updates()

                if updates:
                    peers = self.peer_registry.get_random_peers(self.fanout)
                    for peer in peers:
                        try:
                            await self._send_updates_to_peer(peer["address"], updates)
                            await self._mark_updates_gossiped(
                                [u["log_id"] for u in updates],
                                peer["node_id"]
                            )
                        except Exception as e:
                            logger.warning(f"Failed to gossip to {peer['address']}: {e}")

                await asyncio.sleep(self.gossip_interval)
            except Exception as e:
                logger.error(f"Gossip loop error: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _anti_entropy_loop(self):
        """
        Pull-based anti-entropy: periodically sync with random peer.

        PARTITION HANDLING:
        - If peer unreachable, try next peer
        - When partition heals, this loop automatically syncs state
        - No manual intervention needed
        """
        while self.running:
            try:
                await asyncio.sleep(self.anti_entropy_interval)

                peers = self.peer_registry.get_random_peers(1)
                if not peers:
                    continue

                peer = peers[0]
                try:
                    await self._sync_with_peer(peer["address"])
                except Exception as e:
                    logger.warning(f"Anti-entropy with {peer['address']} failed: {e}")

            except Exception as e:
                logger.error(f"Anti-entropy error: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _get_pending_updates(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get updates that haven't been fully propagated"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT log_id, entity_type, entity_id, operation, data, vector_clock, timestamp, gossiped_to
                FROM gossip_log
                ORDER BY log_id DESC
                LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()
            updates = []
            for row in rows:
                updates.append({
                    "log_id": row["log_id"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "operation": row["operation"],
                    "data": json.loads(row["data"]),
                    "vector_clock": json.loads(row["vector_clock"]),
                    "timestamp": row["timestamp"],
                    "gossiped_to": json.loads(row["gossiped_to"]) if row["gossiped_to"] else []
                })

            return updates

    async def _send_updates_to_peer(self, peer_address: str, updates: List[Dict[str, Any]]):
        """Send updates to peer via HTTP"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://{peer_address}/internal/gossip/receive",
                json={
                    "sender_node_id": self.node_id,
                    "updates": updates
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    logger.debug(f"Sent {len(updates)} updates to {peer_address}")
                else:
                    raise Exception(f"Peer returned status {resp.status}")

    async def _mark_updates_gossiped(self, log_ids: List[int], peer_node_id: str):
        """Mark updates as gossiped to a specific peer"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for log_id in log_ids:
                cursor.execute("SELECT gossiped_to FROM gossip_log WHERE log_id = ?", (log_id,))
                row = cursor.fetchone()
                if row:
                    gossiped_to = json.loads(row["gossiped_to"]) if row["gossiped_to"] else []
                    if peer_node_id not in gossiped_to:
                        gossiped_to.append(peer_node_id)
                        cursor.execute(
                            "UPDATE gossip_log SET gossiped_to = ? WHERE log_id = ?",
                            (json.dumps(gossiped_to), log_id)
                        )
            conn.commit()

    async def _sync_with_peer(self, peer_address: str):
        """Full state sync with a peer"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://{peer_address}/internal/gossip/state-summary",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    peer_summary = await resp.json()
                    logger.debug(f"Synced state summary from {peer_address}")

    async def receive_gossip(self, sender_node_id: str, updates: List[Dict[str, Any]]):
        """
        Receive and apply gossip updates from peer.
        Called by internal HTTP endpoint.
        """
        logger.debug(f"Received {len(updates)} updates from {sender_node_id}")
        for update in updates:
            try:
                await self._apply_update(update)
            except Exception as e:
                logger.error(f"Failed to apply update {update.get('entity_id')}: {e}", exc_info=True)

    async def _apply_update(self, update: Dict[str, Any]):
        """
        Apply a single update with conflict resolution.

        Update format:
        {
            'entity_type': 'file' | 'user' | 'chunk' | 'tag',
            'entity_id': str,
            'operation': 'create' | 'update' | 'delete',
            'data': {...},
            'vector_clock': {...},
            'timestamp': float
        }
        """
        entity_type = update['entity_type']
        entity_id = update['entity_id']
        operation = update['operation']
        remote_data = update['data']
        remote_vc = VectorClock(update['vector_clock'])

        local_entity = await self._fetch_local_entity(entity_type, entity_id)

        if local_entity is None:
            await self._store_entity(entity_type, remote_data)
            logger.debug(f"Applied {operation} for {entity_type}:{entity_id} from gossip")
        else:
            resolution = ConflictResolver.resolve(local_entity, remote_data)

            if resolution['action'] == 'take_remote':
                await self._store_entity(entity_type, remote_data)
                logger.info(f"Resolved conflict for {entity_type}:{entity_id} - took remote ({resolution['reason']})")
            else:
                logger.debug(f"Resolved conflict for {entity_type}:{entity_id} - kept local ({resolution['reason']})")

    async def _fetch_local_entity(self, entity_type: str, entity_id: str) -> Optional[Dict[str, Any]]:
        """Fetch local version of an entity"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if entity_type == 'file':
                cursor.execute("SELECT * FROM files WHERE file_id = ?", (entity_id,))
            elif entity_type == 'user':
                cursor.execute("SELECT * FROM users WHERE user_id = ?", (entity_id,))
            elif entity_type == 'chunk':
                cursor.execute("SELECT * FROM chunks WHERE chunk_id = ?", (entity_id,))
            elif entity_type == 'chunkserver':
                cursor.execute("SELECT * FROM chunkserver_nodes WHERE node_id = ?", (entity_id,))
            elif entity_type == 'controller_peer':
                cursor.execute("SELECT * FROM controller_nodes WHERE node_id = ?", (entity_id,))
            else:
                return None

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def _store_entity(self, entity_type: str, data: Dict[str, Any]):
        """Store or update an entity"""
        if entity_type == 'user':
            from controller.repositories.user_repository import UserRepository, User
            from datetime import datetime

            user = User(
                user_id=data['user_id'],
                username=data['username'],
                password_hash=data['password_hash'],
                api_key=data.get('api_key'),
                created_at=datetime.fromisoformat(data['created_at']),
                key_updated_at=datetime.fromisoformat(data['key_updated_at']) if data.get('key_updated_at') else None,
                vector_clock=VectorClock.from_json(data.get('vector_clock', '{}')) if data.get('vector_clock') else None,
                last_modified_by=data.get('last_modified_by'),
                version=data.get('version', 0)
            )
            UserRepository.merge_user(user)
            return

        with get_db_connection() as conn:
            cursor = conn.cursor()

            if entity_type == 'file':
                cursor.execute("""
                    INSERT OR REPLACE INTO files
                    (file_id, name, size, owner_id, created_at, deleted, vector_clock, last_modified_by, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data['file_id'], data['name'], data['size'], data['owner_id'],
                    data['created_at'], data.get('deleted', 0),
                    data.get('vector_clock', '{}'), data.get('last_modified_by'),
                    data.get('version', 0)
                ))
            elif entity_type == 'chunk':
                cursor.execute("""
                    INSERT OR REPLACE INTO chunks
                    (chunk_id, file_id, chunk_index, size, checksum, vector_clock, last_modified_by, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data['chunk_id'], data['file_id'], data['chunk_index'],
                    data['size'], data['checksum'],
                    data.get('vector_clock', '{}'), data.get('last_modified_by'),
                    data.get('version', 0)
                ))
            elif entity_type == 'chunkserver':
                cursor.execute("""
                    INSERT OR REPLACE INTO chunkserver_nodes
                    (node_id, address, last_heartbeat, capacity_bytes, used_bytes, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    data['node_id'], data['address'], data['last_heartbeat'],
                    data.get('capacity_bytes'), data.get('used_bytes'),
                    data.get('status', 'active')
                ))
            elif entity_type == 'controller_peer':
                cursor.execute("""
                    INSERT OR REPLACE INTO controller_nodes
                    (node_id, address, last_seen, vector_clock)
                    VALUES (?, ?, ?, ?)
                """, (
                    data['node_id'], data['address'], data.get('last_seen', time.time()),
                    data.get('vector_clock', '{}')
                ))

            conn.commit()

    async def add_to_gossip_log(
        self,
        entity_type: str,
        entity_id: str,
        operation: str,
        data: Dict[str, Any]
    ):
        """Add an update to the gossip log for propagation"""
        self.vector_clock = self.vector_clock.increment(self.node_id)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO gossip_log 
                (entity_type, entity_id, operation, data, vector_clock, timestamp, gossiped_to)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                entity_type, entity_id, operation,
                json.dumps(data),
                self.vector_clock.to_json(),
                time.time(),
                json.dumps([])
            ))
            conn.commit()

        logger.debug(f"Added to gossip log: {entity_type}:{entity_id} ({operation})")
