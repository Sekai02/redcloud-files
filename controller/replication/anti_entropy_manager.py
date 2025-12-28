"""
Anti-entropy protocol manager.

Runs background task that periodically reconciles state with peers
to ensure eventual consistency and repair missed gossip messages.
"""

import asyncio
import random
import logging
from typing import Optional

from common.constants import ANTI_ENTROPY_INTERVAL_SECONDS
from controller.replication.controller_id import get_controller_id
from controller.replication.operation_log import get_all_operation_ids
from controller.replication.grpc_client import ReplicationClient
from controller.replication.operation_applier import apply_operation
from controller.replication.gossip_manager import GossipManager

logger = logging.getLogger(__name__)


class AntiEntropyManager:
    """
    Manages periodic anti-entropy protocol execution.

    Reconciles state with random peers every ANTI_ENTROPY_INTERVAL_SECONDS.
    """

    def __init__(self, gossip_manager: GossipManager):
        """
        Initialize the anti-entropy manager.

        Args:
            gossip_manager: GossipManager instance for peer discovery
        """
        self.controller_id = get_controller_id()
        self.gossip_manager = gossip_manager
        self.client = ReplicationClient()
        self.task: Optional[asyncio.Task] = None
        self.running = False

    async def start(self):
        """Start the anti-entropy background task."""
        if self.running:
            logger.warning("Anti-entropy manager already running")
            return

        self.running = True
        self.task = asyncio.create_task(self._anti_entropy_loop())
        logger.info(
            f"Anti-entropy manager started [interval={ANTI_ENTROPY_INTERVAL_SECONDS}s, "
            f"controller_id={self.controller_id}]"
        )

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

        await self.client.close()

        logger.info("Anti-entropy manager stopped")

    async def _anti_entropy_loop(self):
        """
        Main anti-entropy loop.

        Executes anti-entropy rounds every ANTI_ENTROPY_INTERVAL_SECONDS.
        """
        while self.running:
            try:
                await self._anti_entropy_round()
            except Exception as e:
                logger.error(f"Error in anti-entropy round: {e}", exc_info=True)

            await asyncio.sleep(ANTI_ENTROPY_INTERVAL_SECONDS)

    async def _anti_entropy_round(self):
        """
        Execute one anti-entropy round.

        Discovers peers, selects one random peer, exchanges state summaries,
        and reconciles missing operations.
        """
        peer_addresses = self.gossip_manager._discover_peers()

        if not peer_addresses:
            logger.debug("No peers found for anti-entropy")
            return

        peer_address = random.choice(peer_addresses)

        try:
            logger.info(f"Starting anti-entropy round with {peer_address}")

            my_operation_ids = set(get_all_operation_ids())

            peer_summary = await self.client.get_state_summary(peer_address)

            peer_operation_ids = set(peer_summary.operation_ids)

            missing_from_me = peer_operation_ids - my_operation_ids
            missing_from_peer = my_operation_ids - peer_operation_ids

            logger.info(
                f"Anti-entropy with {peer_address}: "
                f"I need {len(missing_from_me)} ops, peer needs {len(missing_from_peer)} ops"
            )

            if missing_from_me:
                missing_ops = await self.client.fetch_operations(
                    peer_address,
                    list(missing_from_me)
                )

                logger.info(f"Fetched {len(missing_ops)} operations from {peer_address}")

                for op in missing_ops:
                    try:
                        applied = await apply_operation(op)
                        if applied:
                            logger.debug(f"Applied operation {op.operation_id} from anti-entropy")
                    except Exception as e:
                        logger.error(
                            f"Failed to apply operation {op.operation_id}: {e}",
                            exc_info=True
                        )

            if missing_from_peer:
                from controller.replication.operation_log import get_operations_by_ids

                ops_to_send = get_operations_by_ids(list(missing_from_peer))

                success = await self.client.push_operations(peer_address, ops_to_send)

                if success:
                    logger.info(f"Pushed {len(ops_to_send)} operations to {peer_address}")
                else:
                    logger.warning(f"Failed to push operations to {peer_address}")

            logger.info(f"Completed anti-entropy round with {peer_address}")

        except Exception as e:
            logger.warning(f"Anti-entropy failed with {peer_address}: {e}")
