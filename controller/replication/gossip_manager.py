"""
Gossip protocol manager.

Runs background task that periodically sends gossip messages to random peers
for rapid propagation of operations.
"""

import asyncio
import random
import logging
import socket
from typing import Optional

from common.constants import GOSSIP_INTERVAL_SECONDS, REPLICATION_PORT
from common.dns_discovery import discover_controller_peers
from common.protocol import GossipMessage
from controller.replication.controller_id import get_controller_id
from controller.replication.operation_log import get_recent_operation_summaries
from controller.replication.grpc_client import ReplicationClient
from controller.database import get_db_connection

logger = logging.getLogger(__name__)


class GossipManager:
    """
    Manages periodic gossip protocol execution.

    Sends gossip messages to random peers every GOSSIP_INTERVAL_SECONDS.
    """

    def __init__(self):
        """Initialize the gossip manager."""
        self.controller_id = get_controller_id()
        self.client = ReplicationClient()
        self.task: Optional[asyncio.Task] = None
        self.running = False

    async def start(self):
        """Start the gossip background task."""
        if self.running:
            logger.warning("Gossip manager already running")
            return

        self.running = True
        self.task = asyncio.create_task(self._gossip_loop())
        logger.info(
            f"Gossip manager started [interval={GOSSIP_INTERVAL_SECONDS}s, "
            f"controller_id={self.controller_id}]"
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

        await self.client.close()

        logger.info("Gossip manager stopped")

    async def _gossip_loop(self):
        """
        Main gossip loop.

        Executes gossip rounds every GOSSIP_INTERVAL_SECONDS.
        """
        while self.running:
            try:
                await self._gossip_round()
            except Exception as e:
                logger.error(f"Error in gossip round: {e}", exc_info=True)

            await asyncio.sleep(GOSSIP_INTERVAL_SECONDS)

    async def _gossip_round(self):
        """
        Execute one gossip round.

        Discovers peers, selects random subset, sends gossip messages.
        """
        peer_addresses = self._discover_peers()

        if not peer_addresses:
            logger.debug("No peers found for gossip")
            return

        selected_peers = self._select_peers(peer_addresses, fan_out=2)

        my_vector_clock = self._get_current_vector_clock()
        operation_summaries = get_recent_operation_summaries(limit=100)

        my_address = self._get_my_address()

        gossip_message = GossipMessage(
            sender_id=self.controller_id,
            sender_address=my_address,
            vector_clock=my_vector_clock,
            operation_summaries=operation_summaries
        )

        for peer_address in selected_peers:
            try:
                response = await self.client.send_gossip(peer_address, gossip_message)

                self._update_peer_state(peer_address, response.peer_id, response.vector_clock)

                if response.missing_operation_ids:
                    logger.info(
                        f"Peer {peer_address} is missing {len(response.missing_operation_ids)} operations, "
                        f"will be fetched via anti-entropy"
                    )

                logger.debug(
                    f"Gossip sent to {peer_address}: "
                    f"{len(operation_summaries)} operations"
                )

            except Exception as e:
                logger.warning(f"Gossip failed to {peer_address}: {e}")
                self._mark_peer_suspected_dead(peer_address)

    def _discover_peers(self) -> list:
        """
        Discover peer controllers via DNS.

        Returns:
            List of peer addresses in "IP:PORT" format
        """
        try:
            peers = discover_controller_peers()

            peer_addresses = [
                peer.replace(f':{8000}', f':{REPLICATION_PORT}')
                if ':8000' in peer
                else f"{peer.split(':')[0]}:{REPLICATION_PORT}"
                for peer in peers
            ]

            my_address = self._get_my_address()
            peer_addresses = [p for p in peer_addresses if p != my_address]

            return peer_addresses

        except Exception as e:
            logger.warning(f"DNS discovery failed: {e}")
            return []

    def _select_peers(self, peer_addresses: list, fan_out: int) -> list:
        """
        Select random peers for gossip.

        Args:
            peer_addresses: Available peer addresses
            fan_out: Number of peers to select

        Returns:
            List of selected peer addresses
        """
        if len(peer_addresses) <= fan_out:
            return peer_addresses

        return random.sample(peer_addresses, fan_out)

    def _get_my_address(self) -> str:
        """
        Get this controller's address in "IP:PORT" format.

        Returns:
            Address string
        """
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            return f"{ip}:{REPLICATION_PORT}"
        except Exception as e:
            logger.warning(f"Failed to get my address: {e}")
            return f"unknown:{REPLICATION_PORT}"

    def _get_current_vector_clock(self) -> dict:
        """
        Get current vector clock from database.

        Returns:
            Vector clock as dict
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT controller_id, sequence FROM vector_clock_state")
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}

    def _update_peer_state(
        self,
        peer_address: str,
        peer_controller_id: str,
        peer_vector_clock: dict
    ):
        """
        Update peer state in database.

        Args:
            peer_address: Peer address
            peer_controller_id: Peer controller ID
            peer_vector_clock: Peer's vector clock
        """
        from datetime import datetime
        import json

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO peer_state
                (peer_address, peer_controller_id, last_gossip_at, last_vector_clock, is_alive)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(peer_address) DO UPDATE SET
                    peer_controller_id = excluded.peer_controller_id,
                    last_gossip_at = excluded.last_gossip_at,
                    last_vector_clock = excluded.last_vector_clock,
                    is_alive = 1
                """,
                (
                    peer_address,
                    peer_controller_id,
                    datetime.utcnow().isoformat(),
                    json.dumps(peer_vector_clock)
                )
            )
            conn.commit()

    def _mark_peer_suspected_dead(self, peer_address: str):
        """
        Mark peer as suspected dead.

        Args:
            peer_address: Peer address
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE peer_state
                SET is_alive = 0
                WHERE peer_address = ?
                """,
                (peer_address,)
            )
            conn.commit()

        logger.warning(f"Marked peer {peer_address} as suspected dead")
