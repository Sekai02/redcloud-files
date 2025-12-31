"""
Anti-entropy protocol manager for chunkserver replication.

Runs background task that periodically reconciles chunk data with peers
to ensure full replication and repair missed gossip messages.
"""

import asyncio
import random
import logging
from typing import Optional, List

from common.constants import ANTI_ENTROPY_INTERVAL_SECONDS
from chunkserver.chunk_index import ChunkIndex
from chunkserver.chunk_storage import write_chunk, read_chunk, delete_chunk
from chunkserver.checksum_validator import compute_checksum

logger = logging.getLogger(__name__)


class ChunkAntiEntropyManager:
    """
    Manages periodic anti-entropy protocol for full chunk reconciliation.

    Reconciles chunk data with random peers every 30 seconds.
    """

    def __init__(self, chunk_index: ChunkIndex, gossip_manager):
        """
        Initialize the chunk anti-entropy manager.

        Args:
            chunk_index: ChunkIndex instance for metadata access
            gossip_manager: ChunkGossipManager instance for peer discovery
        """
        self.chunk_index = chunk_index
        self.gossip_manager = gossip_manager
        self.task: Optional[asyncio.Task] = None
        self.running = False
        self.client = None

    async def start(self):
        """Start the anti-entropy background task."""
        if self.running:
            logger.warning("Chunk anti-entropy manager already running")
            return

        from chunkserver.replication.chunk_replication_client import ChunkReplicationClient
        self.client = ChunkReplicationClient()

        self.running = True
        self.task = asyncio.create_task(self._anti_entropy_loop())
        logger.info(f"Chunk anti-entropy manager started [interval={ANTI_ENTROPY_INTERVAL_SECONDS}s]")

    async def stop(self):
        """Stop the anti-entropy background task."""
        if not self.running:
            return

        self.running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        if self.client:
            await self.client.close()

        logger.info("Chunk anti-entropy manager stopped")

    async def _anti_entropy_loop(self):
        """
        Main anti-entropy loop.

        Executes anti-entropy rounds every ANTI_ENTROPY_INTERVAL_SECONDS.
        """
        while self.running:
            try:
                await self._anti_entropy_round()
            except Exception as e:
                logger.error(f"Error in chunk anti-entropy round: {e}", exc_info=True)

            await asyncio.sleep(ANTI_ENTROPY_INTERVAL_SECONDS)

    async def _anti_entropy_round(self):
        """
        Execute one anti-entropy round.

        Steps:
        1. Select 1 random peer
        2. Exchange state summaries (all chunk IDs + tombstones)
        3. Calculate missing_from_me and missing_from_peer
        4. Fetch missing chunks from peer (with checksum validation)
        5. Push missing chunks to peer
        6. Exchange tombstones
        """
        peer_addresses = self.gossip_manager._discover_peers()

        if not peer_addresses:
            logger.debug("No chunkserver peers found for anti-entropy")
            return

        peer_address = random.choice(peer_addresses)

        try:
            logger.info(f"Starting chunk anti-entropy round with {peer_address}")

            my_chunk_ids = set(self.chunk_index.get_all_chunk_ids())
            my_tombstone_ids = set(self.chunk_index.get_all_tombstone_ids())

            peer_summary = await self.client.get_chunk_state_summary(peer_address)

            peer_chunk_ids = set(peer_summary.chunk_ids)
            peer_tombstone_ids = set(peer_summary.tombstone_ids)

            missing_from_me = peer_chunk_ids - my_chunk_ids - my_tombstone_ids
            missing_from_peer = my_chunk_ids - peer_chunk_ids - peer_tombstone_ids

            logger.info(
                f"Chunk anti-entropy with {peer_address}: "
                f"I need {len(missing_from_me)} chunks, "
                f"peer needs {len(missing_from_peer)} chunks"
            )

            if missing_from_me:
                await self._fetch_chunks_from_peer(peer_address, list(missing_from_me))

            if missing_from_peer:
                await self._push_chunks_to_peer(peer_address, list(missing_from_peer))

            await self._exchange_tombstones(
                peer_address,
                my_tombstone_ids,
                peer_tombstone_ids
            )

            logger.info(f"Completed chunk anti-entropy round with {peer_address}")

        except Exception as e:
            logger.warning(f"Chunk anti-entropy failed with {peer_address}: {e}")

    async def _fetch_chunks_from_peer(
        self,
        peer_address: str,
        chunk_ids: List[str]
    ) -> None:
        """
        Fetch missing chunks from peer.

        For each chunk:
        - Skip if locally tombstoned (prevent resurrection)
        - Fetch chunk data via streaming gRPC
        - Validate checksum
        - Write to disk
        - Update index

        Args:
            peer_address: Peer address in "IP:PORT" format
            chunk_ids: List of chunk IDs to fetch
        """
        logger.info(f"Fetching {len(chunk_ids)} chunks from {peer_address}")

        for chunk_id in chunk_ids:
            try:
                if self.chunk_index.is_tombstoned(chunk_id):
                    logger.debug(f"Skipping fetch of tombstoned chunk {chunk_id}")
                    continue

                chunk_data, metadata = await self.client.fetch_chunk_data(
                    peer_address,
                    chunk_id
                )

                computed_checksum = compute_checksum(chunk_data)
                if computed_checksum != metadata.checksum:
                    logger.error(
                        f"Checksum mismatch for chunk {chunk_id} from {peer_address}: "
                        f"expected {metadata.checksum}, got {computed_checksum}"
                    )
                    continue

                filepath = write_chunk(chunk_id, chunk_data)

                from chunkserver.chunk_index import ChunkIndexEntry
                entry = ChunkIndexEntry(
                    chunk_id=chunk_id,
                    file_id=metadata.file_id,
                    chunk_index=metadata.chunk_index,
                    size=metadata.total_size,
                    checksum=metadata.checksum,
                    filepath=filepath
                )
                self.chunk_index.add_chunk(entry)

                logger.info(
                    f"Successfully replicated chunk {chunk_id} from {peer_address} "
                    f"(size={metadata.total_size}, checksum={metadata.checksum[:8]}...)"
                )

            except Exception as e:
                logger.error(
                    f"Failed to fetch chunk {chunk_id} from {peer_address}: {e}",
                    exc_info=True
                )

    async def _push_chunks_to_peer(
        self,
        peer_address: str,
        chunk_ids: List[str]
    ) -> None:
        """
        Push chunks to peer.

        Uses streaming gRPC to transfer chunk data.

        Args:
            peer_address: Peer address in "IP:PORT" format
            chunk_ids: List of chunk IDs to push
        """
        logger.info(f"Pushing {len(chunk_ids)} chunks to {peer_address}")

        for chunk_id in chunk_ids:
            try:
                entry = self.chunk_index.get_chunk(chunk_id)
                if not entry:
                    logger.warning(f"Chunk {chunk_id} not found in index, skipping push")
                    continue

                chunk_data = read_chunk(chunk_id)

                success = await self.client.push_chunk_data(
                    peer_address,
                    chunk_id,
                    chunk_data,
                    entry
                )

                if success:
                    logger.info(f"Successfully pushed chunk {chunk_id} to {peer_address}")
                else:
                    logger.warning(f"Failed to push chunk {chunk_id} to {peer_address}")

            except Exception as e:
                logger.error(
                    f"Failed to push chunk {chunk_id} to {peer_address}: {e}",
                    exc_info=True
                )

    async def _exchange_tombstones(
        self,
        peer_address: str,
        my_tombstone_ids: set,
        peer_tombstone_ids: set
    ) -> None:
        """
        Exchange tombstones with peer to ensure deletion convergence.

        Args:
            peer_address: Peer address in "IP:PORT" format
            my_tombstone_ids: Set of my tombstone IDs
            peer_tombstone_ids: Set of peer's tombstone IDs
        """
        tombstones_to_push = my_tombstone_ids - peer_tombstone_ids

        if tombstones_to_push:
            logger.info(f"Pushing {len(tombstones_to_push)} tombstones to {peer_address}")

            tombstones = []
            for chunk_id in tombstones_to_push:
                tombstone = self.chunk_index.get_tombstone(chunk_id)
                if tombstone:
                    tombstones.append(tombstone)

            if tombstones:
                try:
                    success = await self.client.push_tombstones(peer_address, tombstones)
                    if success:
                        logger.info(f"Successfully pushed tombstones to {peer_address}")
                except Exception as e:
                    logger.error(f"Failed to push tombstones to {peer_address}: {e}")
