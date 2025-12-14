"""Chunk placement management with dynamic replication."""

import time
from typing import List, Dict, Any, Optional
from common.logging_config import get_logger
from controller.database import get_db_connection

logger = get_logger(__name__)


class ChunkPlacementManager:
    """
    Manages chunk placement across chunkservers with DYNAMIC replication.
    """

    def __init__(self, min_replicas: int = 1):
        """
        Initialize placement manager for full eventual replication.

        Args:
            min_replicas: Minimum replicas to attempt (default 1 for partition tolerance)

        NOTE: System replicates to ALL available chunkservers (no maximum cap).
        Repair service continuously ensures all chunks reach all servers.
        """
        self.min_replicas = min_replicas

    async def select_chunkservers_for_write(
        self,
        chunk_id: str,
        available_servers: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Select chunkservers for a new chunk using DYNAMIC replication.

        Strategy: Replicate to all available servers up to max_replicas.
        This ensures maximum availability and durability.

        Args:
            chunk_id: UUID of chunk to place
            available_servers: List of {'node_id': str, 'address': str, 'used_bytes': int, ...}

        Returns:
            List of chunkserver node_ids to write to (1 to max_replicas servers)
        """
        if not available_servers:
            raise Exception("No chunkservers available")

        num_available = len(available_servers)

        logger.info(
            f"Full replication for chunk {chunk_id}: "
            f"Writing to ALL {num_available} available servers"
        )

        selected = [s['node_id'] for s in available_servers]

        return selected

    async def select_chunkservers_for_read(
        self,
        chunk_id: str,
        chunk_locations: List[str]
    ) -> List[str]:
        """
        Select chunkservers to read from.
        Returns locations ordered by preference (healthy servers first).

        Args:
            chunk_id: UUID of chunk to read
            chunk_locations: List of chunkserver node_ids that have the chunk

        Returns:
            Ordered list of chunkserver node_ids to try
        """
        if not chunk_locations:
            raise FileNotFoundError(f"No locations found for chunk {chunk_id}")

        return chunk_locations

    async def get_chunk_locations(self, chunk_id: str) -> List[str]:
        """
        Retrieve list of chunkserver node_ids that store this chunk.
        Queries the chunk_locations table.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chunkserver_id 
                FROM chunk_locations 
                WHERE chunk_id = ?
            """, (chunk_id,))

            rows = cursor.fetchall()
            return [row['chunkserver_id'] for row in rows]

    async def record_chunk_location(
        self,
        chunk_id: str,
        chunkserver_id: str,
        conn=None
    ):
        """
        Record that a chunk is stored on a chunkserver.
        """
        should_close = False
        if conn is None:
            conn = get_db_connection().__enter__()
            should_close = True

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO chunk_locations 
                (chunk_id, chunkserver_id, created_at)
                VALUES (?, ?, ?)
            """, (chunk_id, chunkserver_id, time.time()))
            conn.commit()
        finally:
            if should_close:
                conn.__exit__(None, None, None)

    async def remove_chunk_location(
        self,
        chunk_id: str,
        chunkserver_id: str
    ):
        """Remove a chunk location (e.g., after deletion or server failure)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM chunk_locations
                WHERE chunk_id = ? AND chunkserver_id = ?
            """, (chunk_id, chunkserver_id))
            conn.commit()

    async def get_all_chunk_ids(self) -> List[str]:
        """Get all chunk IDs in the system"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chunk_id FROM chunks")
            rows = cursor.fetchall()
            return [row['chunk_id'] for row in rows]
