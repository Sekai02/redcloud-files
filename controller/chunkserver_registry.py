"""Registry for tracking chunkserver nodes and their status."""

import asyncio
import time
from typing import List, Dict, Any
from common.logging_config import get_logger
from controller.database import get_db_connection

logger = get_logger(__name__)


class ChunkserverRegistry:
    """Registry for tracking chunkserver nodes and their status"""

    def __init__(self):
        self.lock = asyncio.Lock()

    async def load_from_database(self):
        """
        Load chunkserver info from database on startup.
        Restores topology after controller restart.
        """
        async with self.lock:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT node_id, address, last_heartbeat, capacity_bytes, used_bytes, status
                    FROM chunkserver_nodes
                """)
                rows = cursor.fetchall()
                count = len(rows)
                logger.info(f"Loaded {count} chunkservers from database")
                return count

    async def update_chunkserver(
        self,
        node_id: str,
        address: str,
        capacity_bytes: int,
        used_bytes: int
    ):
        """Update chunkserver info from heartbeat"""
        async with self.lock:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO chunkserver_nodes
                    (node_id, address, last_heartbeat, capacity_bytes, used_bytes, status)
                    VALUES (?, ?, ?, ?, ?, 'active')
                """, (node_id, address, time.time(), capacity_bytes, used_bytes))
                conn.commit()

    async def mark_failed(self, node_id: str):
        """Mark chunkserver as failed"""
        async with self.lock:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE chunkserver_nodes
                    SET status = 'failed'
                    WHERE node_id = ?
                """, (node_id,))
                conn.commit()
                logger.warning(f"Marked chunkserver {node_id} as failed")

    async def mark_healthy(self, node_id: str):
        """Mark chunkserver as healthy (recovered)"""
        async with self.lock:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE chunkserver_nodes
                    SET status = 'active'
                    WHERE node_id = ?
                """, (node_id,))
                conn.commit()
                logger.info(f"Marked chunkserver {node_id} as healthy")

    async def get_healthy_servers(self) -> List[Dict[str, Any]]:
        """Get list of healthy (active) chunkservers only"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT node_id, address, capacity_bytes, used_bytes
                FROM chunkserver_nodes
                WHERE status = 'active'
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_all(self) -> List[Dict[str, Any]]:
        """Get all chunkservers (including failed)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT node_id, address, last_heartbeat, capacity_bytes, used_bytes, status
                FROM chunkserver_nodes
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    async def cleanup_stale_servers(self, timeout_seconds: int = 60):
        """
        Remove chunkservers that haven't sent heartbeat within timeout.
        """
        async with self.lock:
            cutoff_time = time.time() - timeout_seconds
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM chunkserver_nodes
                    WHERE last_heartbeat < ? AND status != 'failed'
                """, (cutoff_time,))
                deleted = cursor.rowcount
                conn.commit()
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} stale chunkservers")
                return deleted

    async def get_server_info(self, node_id: str) -> Dict[str, Any]:
        """Get info for a specific chunkserver"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT node_id, address, last_heartbeat, capacity_bytes, used_bytes, status
                FROM chunkserver_nodes
                WHERE node_id = ?
            """, (node_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
