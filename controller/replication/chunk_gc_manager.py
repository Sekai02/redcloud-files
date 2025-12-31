"""
Chunk garbage collection manager.

Runs background task that periodically identifies and safely deletes
orphaned chunks using a distributed quorum protocol.
"""

import asyncio
import logging
import json
from typing import Optional, List
from datetime import datetime

from common.constants import ANTI_ENTROPY_INTERVAL_SECONDS
from controller.database import get_db_connection
from controller.replication.controller_id import get_controller_id
from controller.replication.grpc_client import ReplicationClient
from controller.replication.gossip_manager import GossipManager
from controller.chunkserver_client import ChunkserverClient

logger = logging.getLogger(__name__)


class ChunkGCManager:
    """
    Manages periodic chunk garbage collection with distributed quorum.

    Safely deletes chunks only when all controllers agree they are unreferenced.
    """

    def __init__(self, gossip_manager: GossipManager):
        """
        Initialize the chunk GC manager.

        Args:
            gossip_manager: GossipManager instance for peer discovery
        """
        self.controller_id = get_controller_id()
        self.gossip_manager = gossip_manager
        self.replication_client = ReplicationClient()
        self.chunkserver_client = ChunkserverClient()
        self.task: Optional[asyncio.Task] = None
        self.running = False

    async def start(self):
        """Start the chunk GC background task."""
        if self.running:
            logger.warning("Chunk GC manager already running")
            return

        self.running = True
        self.task = asyncio.create_task(self._gc_loop())
        logger.info(
            f"Chunk GC manager started [interval={ANTI_ENTROPY_INTERVAL_SECONDS * 2}s, "
            f"controller_id={self.controller_id}]"
        )

    async def stop(self):
        """Stop the chunk GC background task."""
        if not self.running:
            return

        self.running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        await self.replication_client.close()

        logger.info("Chunk GC manager stopped")

    async def _gc_loop(self):
        """
        Main GC loop.

        Executes GC rounds every ANTI_ENTROPY_INTERVAL_SECONDS * 2.
        """
        while self.running:
            try:
                await self._gc_round()
            except Exception as e:
                logger.error(f"Error in chunk GC round: {e}", exc_info=True)

            await asyncio.sleep(ANTI_ENTROPY_INTERVAL_SECONDS * 2)

    async def _gc_round(self):
        """
        Execute one GC round.

        Identifies chunks marked for GC, queries all peers for liveness,
        and deletes chunks when quorum agrees they are unreferenced.
        """
        chunks_marked_for_gc = self._get_chunks_marked_for_gc()

        if not chunks_marked_for_gc:
            logger.debug("No chunks marked for GC")
            return

        peer_addresses = self.gossip_manager._discover_peers()

        if not peer_addresses:
            logger.debug("No peers found for GC quorum, skipping")
            return

        logger.info(
            f"Starting GC round: {len(chunks_marked_for_gc)} chunks to check, "
            f"{len(peer_addresses)} peers"
        )

        for chunk_id in chunks_marked_for_gc:
            try:
                should_delete = await self._check_gc_quorum(chunk_id, peer_addresses)

                if should_delete:
                    await self._delete_chunk(chunk_id)
                else:
                    logger.debug(
                        f"Chunk {chunk_id} still referenced, removing GC mark"
                    )
                    self._unmark_chunk_for_gc(chunk_id)

            except Exception as e:
                logger.error(f"Error processing chunk {chunk_id} for GC: {e}", exc_info=True)

    async def _check_gc_quorum(self, chunk_id: str, peer_addresses: List[str]) -> bool:
        """
        Check if all peers agree the chunk is unreferenced.

        Args:
            chunk_id: Chunk ID to check
            peer_addresses: List of peer addresses

        Returns:
            True if all peers report chunk as not live, False otherwise
        """
        local_is_live = self._is_chunk_live_locally(chunk_id)

        if local_is_live:
            logger.debug(f"Chunk {chunk_id} is live locally, cannot delete")
            return False

        for peer_address in peer_addresses:
            try:
                response = await self.replication_client.query_chunk_liveness(
                    peer_address,
                    chunk_id
                )

                if response.is_live:
                    logger.info(
                        f"Chunk {chunk_id} is live on peer {peer_address}, "
                        f"files={response.referenced_by_files}"
                    )
                    return False

            except Exception as e:
                logger.warning(
                    f"Failed to query chunk liveness from {peer_address}: {e}, "
                    f"aborting delete for safety"
                )
                return False

        logger.info(
            f"GC quorum reached for chunk {chunk_id}: "
            f"all {len(peer_addresses) + 1} controllers agree it's unreferenced"
        )
        return True

    async def _delete_chunk(self, chunk_id: str):
        """
        Delete chunk from chunkserver and update liveness table.

        Args:
            chunk_id: Chunk ID to delete
        """
        try:
            await self.chunkserver_client.delete_chunk(chunk_id)

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE chunk_liveness SET marked_for_gc = 0, referenced_by_files = '[]' WHERE chunk_id = ?",
                    (chunk_id,)
                )
                conn.commit()

            logger.info(f"Successfully deleted chunk {chunk_id} via distributed GC")

        except Exception as e:
            logger.error(f"Failed to delete chunk {chunk_id}: {e}", exc_info=True)
            raise

    def _get_chunks_marked_for_gc(self) -> List[str]:
        """
        Get chunks marked for garbage collection.

        Returns:
            List of chunk IDs marked for GC
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT chunk_id FROM chunk_liveness WHERE marked_for_gc = 1 LIMIT 10"
            )
            rows = cursor.fetchall()
            return [row[0] for row in rows]

    def _is_chunk_live_locally(self, chunk_id: str) -> bool:
        """
        Check if chunk is referenced by any files locally.

        Args:
            chunk_id: Chunk ID to check

        Returns:
            True if chunk is referenced, False otherwise
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM chunks WHERE chunk_id = ?",
                (chunk_id,)
            )
            count = cursor.fetchone()[0]
            return count > 0

    def _unmark_chunk_for_gc(self, chunk_id: str):
        """
        Remove GC mark from chunk (it's still referenced).

        Args:
            chunk_id: Chunk ID to unmark
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE chunk_liveness SET marked_for_gc = 0 WHERE chunk_id = ?",
                (chunk_id,)
            )
            conn.commit()

        logger.debug(f"Unmarked chunk {chunk_id} for GC")

    def mark_chunks_for_gc(self, chunk_ids: List[str]):
        """
        Mark chunks for garbage collection.

        Args:
            chunk_ids: List of chunk IDs to mark for GC
        """
        if not chunk_ids:
            return

        now = datetime.utcnow().isoformat()

        with get_db_connection() as conn:
            cursor = conn.cursor()

            for chunk_id in chunk_ids:
                cursor.execute(
                    """
                    INSERT INTO chunk_liveness (chunk_id, referenced_by_files, last_verified_at, marked_for_gc)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        marked_for_gc = 1,
                        last_verified_at = excluded.last_verified_at
                    """,
                    (chunk_id, json.dumps([]), now)
                )

            conn.commit()

        logger.info(f"Marked {len(chunk_ids)} chunks for distributed GC")
