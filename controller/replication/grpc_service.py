"""
gRPC service handlers for replication protocol.

Implements server-side handlers for gossip, anti-entropy, and operation exchange.
"""

import logging
from typing import List

from common.protocol import (
    GossipMessage, GossipResponse,
    GetStateSummaryRequest, StateSummary,
    FetchOperationsRequest, FetchOperationsResponse,
    PushOperationsRequest, PushOperationsResponse
)
from controller.replication.controller_id import get_controller_id
from controller.replication.operation_log import (
    get_all_operation_ids,
    get_operations_by_ids,
    get_recent_operation_summaries
)
from controller.replication.vector_clock import VectorClock
from controller.database import get_db_connection

logger = logging.getLogger(__name__)


class ReplicationServicer:
    """
    gRPC servicer for replication operations.

    Handles incoming gossip messages, state summaries, and operation exchanges.
    """

    def __init__(self):
        """Initialize the replication servicer."""
        self.controller_id = get_controller_id()
        logger.info(f"Initialized ReplicationServicer [controller_id={self.controller_id}]")

    async def Gossip(self, request_bytes: bytes) -> bytes:
        """
        Handle incoming gossip message.

        Args:
            request_bytes: Serialized GossipMessage

        Returns:
            Serialized GossipResponse
        """
        try:
            request = GossipMessage.from_json(request_bytes)

            logger.debug(
                f"Received gossip from {request.sender_id} "
                f"({len(request.operation_summaries)} operations)"
            )

            my_vector_clock = self._get_current_vector_clock()

            sender_clock = VectorClock(clocks=request.vector_clock)
            my_clock = VectorClock(clocks=my_vector_clock)
            my_clock.merge(sender_clock)
            self._update_vector_clock(my_clock)

            my_operation_ids = set(get_all_operation_ids())
            received_operation_ids = {op.operation_id for op in request.operation_summaries}

            missing_operation_ids = list(received_operation_ids - my_operation_ids)

            response = GossipResponse(
                peer_id=self.controller_id,
                vector_clock=my_vector_clock,
                missing_operation_ids=missing_operation_ids
            )

            logger.info(
                f"Gossip processed from {request.sender_id}: "
                f"received {len(received_operation_ids)} ops, "
                f"missing {len(missing_operation_ids)} ops"
            )

            return response.to_json()

        except Exception as e:
            logger.error(f"Error processing gossip: {e}", exc_info=True)
            raise

    async def GetStateSummary(self, request_bytes: bytes) -> bytes:
        """
        Handle state summary request for anti-entropy.

        Args:
            request_bytes: Serialized GetStateSummaryRequest

        Returns:
            Serialized StateSummary
        """
        try:
            GetStateSummaryRequest.from_json(request_bytes)

            my_vector_clock = self._get_current_vector_clock()
            operation_ids = get_all_operation_ids()

            response = StateSummary(
                peer_id=self.controller_id,
                vector_clock=my_vector_clock,
                operation_ids=operation_ids
            )

            logger.debug(
                f"State summary requested: returning {len(operation_ids)} operation IDs"
            )

            return response.to_json()

        except Exception as e:
            logger.error(f"Error getting state summary: {e}", exc_info=True)
            raise

    async def FetchOperations(self, request_bytes: bytes) -> bytes:
        """
        Handle request to fetch specific operations.

        Args:
            request_bytes: Serialized FetchOperationsRequest

        Returns:
            Serialized FetchOperationsResponse
        """
        try:
            request = FetchOperationsRequest.from_json(request_bytes)

            operations = get_operations_by_ids(request.operation_ids)

            response = FetchOperationsResponse(operations=operations)

            logger.info(
                f"Fetched {len(operations)} operations "
                f"(requested {len(request.operation_ids)})"
            )

            return response.to_json()

        except Exception as e:
            logger.error(f"Error fetching operations: {e}", exc_info=True)
            raise

    async def PushOperations(self, request_bytes: bytes) -> bytes:
        """
        Handle incoming operations pushed from peer.

        Args:
            request_bytes: Serialized PushOperationsRequest

        Returns:
            Serialized PushOperationsResponse
        """
        try:
            request = PushOperationsRequest.from_json(request_bytes)

            logger.info(f"Received {len(request.operations)} operations to apply")

            for operation in request.operations:
                from controller.replication.operation_applier import apply_operation
                await apply_operation(operation)

            response = PushOperationsResponse(success=True)

            logger.info(f"Successfully processed {len(request.operations)} pushed operations")

            return response.to_json()

        except Exception as e:
            logger.error(f"Error pushing operations: {e}", exc_info=True)
            response = PushOperationsResponse(
                success=False,
                error_message=str(e)
            )
            return response.to_json()

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

    def _update_vector_clock(self, vector_clock: VectorClock) -> None:
        """
        Update vector clock state in database.

        Args:
            vector_clock: Updated vector clock
        """
        from datetime import datetime

        with get_db_connection() as conn:
            cursor = conn.cursor()
            for controller_id, sequence in vector_clock.clocks.items():
                cursor.execute(
                    """
                    INSERT INTO vector_clock_state (controller_id, sequence, last_seen_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(controller_id) DO UPDATE SET
                        sequence = excluded.sequence,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (controller_id, sequence, datetime.utcnow().isoformat())
                )
            conn.commit()
