"""
Gossip protocol manager for chunkserver peer-to-peer replication.

Runs background task that periodically sends chunk summaries to random peers
for rapid propagation of chunk metadata.
"""

import asyncio
import random
import logging
import socket
from typing import Optional, List

from common.constants import GOSSIP_INTERVAL_SECONDS, CHUNKSERVER_PORT
from common.dns_discovery import discover_chunkserver_peers
from common.protocol import ChunkGossipMessage, ChunkSummary, TombstoneEntry
from chunkserver.chunk_index import ChunkIndex

logger = logging.getLogger(__name__)


class ChunkGossipManager:
    """
    Manages periodic gossip protocol for chunk metadata propagation.

    Sends chunk summaries and tombstones to random peers every 2 seconds.
    """

    def __init__(self, chunk_index: ChunkIndex):
        """
        Initialize the chunk gossip manager.

        Args:
            chunk_index: ChunkIndex instance for metadata access
        """
        self.chunk_index = chunk_index
        self.my_address = self._get_my_address()
        self.task: Optional[asyncio.Task] = None
        self.running = False
        self.client = None

    async def start(self):
        """Start the gossip background task."""
        if self.running:
            logger.warning("Chunk gossip manager already running")
            return

        from chunkserver.replication.chunk_replication_client import ChunkReplicationClient
        self.client = ChunkReplicationClient()

        self.running = True
        self.task = asyncio.create_task(self._gossip_loop())
        logger.info(
            f"Chunk gossip manager started [interval={GOSSIP_INTERVAL_SECONDS}s, address={self.my_address}]"
        )

    async def stop(self):
        """Stop the gossip background task."""
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

        logger.info("Chunk gossip manager stopped")

    async def _gossip_loop(self):
        """
        Main gossip loop.

        Executes gossip rounds every GOSSIP_INTERVAL_SECONDS.
        """
        while self.running:
            try:
                await self._gossip_round()
            except Exception as e:
                logger.error(f"Error in chunk gossip round: {e}", exc_info=True)

            await asyncio.sleep(GOSSIP_INTERVAL_SECONDS)

    async def _gossip_round(self):
        """
        Execute one gossip round.

        Steps:
        1. Discover peers via DNS
        2. Select 2 random peers (fan_out=2)
        3. Send recent chunk summaries + tombstones
        4. Receive peer's missing chunk list
        """
        peer_addresses = self._discover_peers()

        if not peer_addresses:
            logger.debug("No chunkserver peers found for gossip")
            return

        selected_peers = self._select_peers(peer_addresses, fan_out=2)

        recent_chunks = self._get_recent_chunk_summaries(limit=100)
        recent_tombstones = self._get_recent_tombstones(limit=50)

        gossip_message = ChunkGossipMessage(
            sender_address=self.my_address,
            chunk_summaries=recent_chunks,
            tombstones=recent_tombstones
        )

        for peer_address in selected_peers:
            try:
                response = await self.client.send_chunk_gossip(peer_address, gossip_message)

                if response.missing_chunk_ids:
                    logger.info(
                        f"Peer {peer_address} is missing {len(response.missing_chunk_ids)} chunks, "
                        f"will be fetched via anti-entropy"
                    )

                logger.debug(
                    f"Chunk gossip sent to {peer_address}: "
                    f"{len(recent_chunks)} chunks, {len(recent_tombstones)} tombstones"
                )

            except Exception as e:
                logger.warning(f"Chunk gossip failed to {peer_address}: {e}")

    def _discover_peers(self) -> List[str]:
        """
        Discover peer chunkservers via DNS.

        Returns:
            List of peer addresses in "IP:PORT" format, excluding self
        """
        try:
            peers = discover_chunkserver_peers()

            peer_addresses = [p for p in peers if p != self.my_address]

            return peer_addresses

        except Exception as e:
            logger.warning(f"DNS discovery failed for chunkservers: {e}")
            return []

    def _select_peers(self, peer_addresses: List[str], fan_out: int) -> List[str]:
        """
        Select random peers for gossip.

        Args:
            peer_addresses: List of available peer addresses
            fan_out: Number of peers to select (default: 2)

        Returns:
            List of selected peer addresses
        """
        if len(peer_addresses) <= fan_out:
            return peer_addresses

        return random.sample(peer_addresses, fan_out)

    def _get_my_address(self) -> str:
        """
        Get this chunkserver's address in IP:PORT format.

        Returns:
            Address string like "10.0.1.5:50051"
        """
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            return f"{ip}:{CHUNKSERVER_PORT}"
        except Exception as e:
            logger.warning(f"Failed to get my address: {e}")
            return f"unknown:{CHUNKSERVER_PORT}"

    def _get_recent_chunk_summaries(self, limit: int) -> List[ChunkSummary]:
        """
        Get summaries of recently added chunks.

        Args:
            limit: Maximum number of summaries to return

        Returns:
            List of ChunkSummary objects
        """
        all_chunk_ids = self.chunk_index.get_all_chunk_ids()

        recent_ids = all_chunk_ids[-limit:] if len(all_chunk_ids) > limit else all_chunk_ids

        summaries = []
        for chunk_id in recent_ids:
            entry = self.chunk_index.get_chunk(chunk_id)
            if entry:
                summaries.append(ChunkSummary(
                    chunk_id=entry.chunk_id,
                    checksum=entry.checksum,
                    size=entry.size
                ))

        return summaries

    def _get_recent_tombstones(self, limit: int) -> List[TombstoneEntry]:
        """
        Get recent tombstone entries.

        Args:
            limit: Maximum number of tombstones to return

        Returns:
            List of TombstoneEntry objects
        """
        all_tombstone_ids = self.chunk_index.get_all_tombstone_ids()

        recent_ids = all_tombstone_ids[-limit:] if len(all_tombstone_ids) > limit else all_tombstone_ids

        tombstones = []
        for chunk_id in recent_ids:
            tombstone = self.chunk_index.get_tombstone(chunk_id)
            if tombstone:
                tombstones.append(tombstone)

        return tombstones
