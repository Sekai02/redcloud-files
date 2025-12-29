"""
gRPC client for chunkserver-to-chunkserver replication operations.

Provides async methods for gossip, anti-entropy, and chunk transfer.
"""

import grpc
import logging
from typing import Dict, Tuple, List

from common.protocol import (
    ChunkGossipMessage,
    ChunkGossipResponse,
    ChunkStateSummary,
    FetchChunkRequest,
    FetchChunkResponse,
    PushTombstonesRequest,
    PushTombstonesResponse,
    TombstoneEntry,
    ChunkMetadata,
    ReadChunkResponse
)
from chunkserver.chunk_index import ChunkIndexEntry

logger = logging.getLogger(__name__)


class ChunkReplicationClient:
    """
    gRPC client for chunk replication operations with peer chunkservers.
    """

    def __init__(self):
        """Initialize the replication client."""
        self._channels: Dict[str, grpc.aio.Channel] = {}

    async def send_chunk_gossip(
        self,
        peer_address: str,
        message: ChunkGossipMessage
    ) -> ChunkGossipResponse:
        """
        Send chunk gossip message to peer.

        Args:
            peer_address: Peer address in "IP:PORT" format
            message: ChunkGossipMessage with summaries and tombstones

        Returns:
            ChunkGossipResponse with missing chunk IDs

        Raises:
            grpc.RpcError: If RPC fails
        """
        channel = self._get_channel(peer_address)
        multi_callable = channel.unary_unary(
            '/chunkserver.ChunkReplicationService/ChunkGossip',
            request_serializer=lambda x: x,
            response_deserializer=lambda x: x,
        )

        request_bytes = message.to_json()
        response_bytes = await multi_callable(request_bytes)

        return ChunkGossipResponse.from_json(response_bytes)

    async def get_chunk_state_summary(
        self,
        peer_address: str
    ) -> ChunkStateSummary:
        """
        Request chunk state summary from peer for anti-entropy.

        Args:
            peer_address: Peer address in "IP:PORT" format

        Returns:
            ChunkStateSummary with all chunk IDs and tombstones

        Raises:
            grpc.RpcError: If RPC fails
        """
        channel = self._get_channel(peer_address)
        multi_callable = channel.unary_unary(
            '/chunkserver.ChunkReplicationService/GetChunkStateSummary',
            request_serializer=lambda x: x,
            response_deserializer=lambda x: x,
        )

        request_bytes = b'{}'
        response_bytes = await multi_callable(request_bytes)

        return ChunkStateSummary.from_json(response_bytes)

    async def fetch_chunk_data(
        self,
        peer_address: str,
        chunk_id: str
    ) -> Tuple[bytes, ChunkMetadata]:
        """
        Fetch chunk data from peer via streaming RPC.

        Args:
            peer_address: Peer address in "IP:PORT" format
            chunk_id: UUID of chunk to fetch

        Returns:
            Tuple of (chunk_data, metadata)

        Raises:
            grpc.RpcError: If RPC fails
        """
        channel = self._get_channel(peer_address)
        multi_callable = channel.unary_stream(
            '/chunkserver.ChunkReplicationService/FetchChunkData',
            request_serializer=lambda x: x,
            response_deserializer=lambda x: x,
        )

        request = FetchChunkRequest(chunk_id=chunk_id)
        request_bytes = request.to_json()

        metadata = None
        data_buffer = bytearray()
        message_index = 0

        async for response_bytes in multi_callable(request_bytes):
            message_index += 1

            if message_index == 1:
                fetch_response = FetchChunkResponse.from_json(response_bytes)
                if not fetch_response.exists:
                    raise Exception(f"Chunk {chunk_id} not found on peer {peer_address}")
                continue

            if not isinstance(response_bytes, bytes):
                response_bytes = bytes(response_bytes)

            try:
                chunk_response = ReadChunkResponse.from_json(response_bytes)

                if chunk_response.metadata:
                    metadata = chunk_response.metadata

                if chunk_response.data:
                    data_buffer.extend(chunk_response.data.data)

            except Exception as e:
                logger.error(f"Error parsing chunk response: {e}")
                raise

        if metadata is None:
            raise Exception(f"No metadata received for chunk {chunk_id}")

        return bytes(data_buffer), metadata

    async def push_chunk_data(
        self,
        peer_address: str,
        chunk_id: str,
        chunk_data: bytes,
        entry: ChunkIndexEntry
    ) -> bool:
        """
        Push chunk data to peer via streaming RPC.

        Args:
            peer_address: Peer address in "IP:PORT" format
            chunk_id: UUID of chunk to push
            chunk_data: Raw chunk data
            entry: ChunkIndexEntry with metadata

        Returns:
            True if push succeeded, False otherwise

        Raises:
            grpc.RpcError: If RPC fails
        """
        logger.info(f"Pushing chunk {chunk_id} to {peer_address} (not yet implemented)")
        return True

    async def push_tombstones(
        self,
        peer_address: str,
        tombstones: List[TombstoneEntry]
    ) -> bool:
        """
        Push tombstones to peer.

        Args:
            peer_address: Peer address in "IP:PORT" format
            tombstones: List of TombstoneEntry objects

        Returns:
            True if push succeeded, False otherwise

        Raises:
            grpc.RpcError: If RPC fails
        """
        channel = self._get_channel(peer_address)
        multi_callable = channel.unary_unary(
            '/chunkserver.ChunkReplicationService/PushTombstones',
            request_serializer=lambda x: x,
            response_deserializer=lambda x: x,
        )

        request = PushTombstonesRequest(tombstones=tombstones)
        request_bytes = request.to_json()

        response_bytes = await multi_callable(request_bytes)
        response = PushTombstonesResponse.from_json(response_bytes)

        return response.success

    def _get_channel(self, peer_address: str) -> grpc.aio.Channel:
        """
        Get or create gRPC channel for peer.

        Args:
            peer_address: Peer address in "IP:PORT" format

        Returns:
            gRPC channel instance
        """
        if peer_address not in self._channels:
            self._channels[peer_address] = grpc.aio.insecure_channel(peer_address)

        return self._channels[peer_address]

    async def close(self):
        """Close all gRPC channels."""
        for channel in self._channels.values():
            await channel.close()
        self._channels.clear()
