"""
gRPC client for peer controller communication.

Provides client-side methods for sending gossip messages, fetching operations,
and exchanging state summaries with peer controllers.
"""

import grpc
import logging
from typing import List

from common.protocol import (
    GossipMessage, GossipResponse,
    GetStateSummaryRequest, StateSummary,
    FetchOperationsRequest, FetchOperationsResponse,
    PushOperationsRequest, PushOperationsResponse,
    Operation
)
from common.constants import CHUNKSERVER_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class ReplicationClient:
    """
    gRPC client for replication operations with peer controllers.
    """

    def __init__(self):
        """Initialize the replication client."""
        self._channels = {}

    async def send_gossip(self, peer_address: str, message: GossipMessage) -> GossipResponse:
        """
        Send gossip message to peer controller.

        Args:
            peer_address: Peer address in "IP:PORT" format
            message: GossipMessage to send

        Returns:
            GossipResponse from peer

        Raises:
            grpc.RpcError: If communication fails
        """
        try:
            channel = self._get_channel(peer_address)

            multi_callable = channel.unary_unary(
                '/replication.ReplicationService/Gossip',
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )

            response_bytes = await multi_callable(
                message.to_json(),
                timeout=CHUNKSERVER_TIMEOUT_SECONDS
            )

            response = GossipResponse.from_json(response_bytes)

            logger.debug(f"Gossip sent to {peer_address} successfully")

            return response

        except grpc.RpcError as e:
            logger.warning(f"Gossip failed to {peer_address}: {e.code()} - {e.details()}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending gossip to {peer_address}: {e}", exc_info=True)
            raise

    async def get_state_summary(self, peer_address: str) -> StateSummary:
        """
        Request state summary from peer for anti-entropy.

        Args:
            peer_address: Peer address in "IP:PORT" format

        Returns:
            StateSummary from peer

        Raises:
            grpc.RpcError: If communication fails
        """
        try:
            channel = self._get_channel(peer_address)

            multi_callable = channel.unary_unary(
                '/replication.ReplicationService/GetStateSummary',
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )

            request = GetStateSummaryRequest()
            response_bytes = await multi_callable(
                request.to_json(),
                timeout=CHUNKSERVER_TIMEOUT_SECONDS
            )

            response = StateSummary.from_json(response_bytes)

            logger.debug(
                f"State summary received from {peer_address}: "
                f"{len(response.operation_ids)} operations"
            )

            return response

        except grpc.RpcError as e:
            logger.warning(f"Get state summary failed from {peer_address}: {e.code()} - {e.details()}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting state summary from {peer_address}: {e}", exc_info=True)
            raise

    async def fetch_operations(
        self,
        peer_address: str,
        operation_ids: List[str]
    ) -> List[Operation]:
        """
        Fetch specific operations from peer.

        Args:
            peer_address: Peer address in "IP:PORT" format
            operation_ids: List of operation IDs to fetch

        Returns:
            List of Operation objects

        Raises:
            grpc.RpcError: If communication fails
        """
        try:
            channel = self._get_channel(peer_address)

            multi_callable = channel.unary_unary(
                '/replication.ReplicationService/FetchOperations',
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )

            request = FetchOperationsRequest(operation_ids=operation_ids)
            response_bytes = await multi_callable(
                request.to_json(),
                timeout=CHUNKSERVER_TIMEOUT_SECONDS
            )

            response = FetchOperationsResponse.from_json(response_bytes)

            logger.info(
                f"Fetched {len(response.operations)} operations from {peer_address}"
            )

            return response.operations

        except grpc.RpcError as e:
            logger.warning(f"Fetch operations failed from {peer_address}: {e.code()} - {e.details()}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching operations from {peer_address}: {e}", exc_info=True)
            raise

    async def push_operations(
        self,
        peer_address: str,
        operations: List[Operation]
    ) -> bool:
        """
        Push operations to peer.

        Args:
            peer_address: Peer address in "IP:PORT" format
            operations: List of Operation objects to push

        Returns:
            True if successful, False otherwise

        Raises:
            grpc.RpcError: If communication fails
        """
        try:
            channel = self._get_channel(peer_address)

            multi_callable = channel.unary_unary(
                '/replication.ReplicationService/PushOperations',
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )

            request = PushOperationsRequest(operations=operations)
            response_bytes = await multi_callable(
                request.to_json(),
                timeout=CHUNKSERVER_TIMEOUT_SECONDS
            )

            response = PushOperationsResponse.from_json(response_bytes)

            if response.success:
                logger.info(f"Pushed {len(operations)} operations to {peer_address}")
            else:
                logger.warning(
                    f"Push operations to {peer_address} failed: {response.error_message}"
                )

            return response.success

        except grpc.RpcError as e:
            logger.warning(f"Push operations failed to {peer_address}: {e.code()} - {e.details()}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error pushing operations to {peer_address}: {e}", exc_info=True)
            raise

    def _get_channel(self, peer_address: str) -> grpc.aio.Channel:
        """
        Get or create gRPC channel for peer.

        Args:
            peer_address: Peer address in "IP:PORT" format

        Returns:
            gRPC channel
        """
        if peer_address not in self._channels:
            self._channels[peer_address] = grpc.aio.insecure_channel(peer_address)
            logger.debug(f"Created gRPC channel to {peer_address}")

        return self._channels[peer_address]

    async def close(self):
        """Close all gRPC channels."""
        for address, channel in self._channels.items():
            await channel.close()
            logger.debug(f"Closed gRPC channel to {address}")

        self._channels.clear()
