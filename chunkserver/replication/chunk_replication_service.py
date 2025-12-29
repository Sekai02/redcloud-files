"""
gRPC service implementation for chunkserver replication.

Handles peer-to-peer chunk synchronization requests.
"""

import grpc
import logging
import socket
from typing import AsyncIterator

from common.protocol import (
    ChunkGossipMessage,
    ChunkGossipResponse,
    ChunkStateSummary,
    FetchChunkRequest,
    FetchChunkResponse,
    PushTombstonesRequest,
    PushTombstonesResponse,
    ReadChunkResponse,
    ChunkMetadata,
    ChunkDataPiece
)
from common.constants import CHUNKSERVER_PORT, STREAM_PIECE_SIZE_BYTES
from chunkserver.chunk_index import ChunkIndex
from chunkserver.chunk_storage import delete_chunk, read_chunk_streaming

logger = logging.getLogger(__name__)


class ChunkReplicationServicer:
    """
    gRPC servicer for chunk replication operations.

    Handles peer-to-peer chunk synchronization requests.
    """

    def __init__(self, chunk_index: ChunkIndex):
        """
        Initialize the replication servicer.

        Args:
            chunk_index: ChunkIndex instance for metadata access
        """
        self.chunk_index = chunk_index

    async def ChunkGossip(self, request_bytes: bytes) -> bytes:
        """
        Handle incoming chunk gossip message.

        Steps:
        1. Process tombstones (delete chunks, add tombstones)
        2. Identify missing chunks
        3. Return list of missing chunk IDs

        Args:
            request_bytes: Serialized ChunkGossipMessage

        Returns:
            Serialized ChunkGossipResponse
        """
        try:
            request = ChunkGossipMessage.from_json(request_bytes)

            logger.debug(
                f"Received chunk gossip from {request.sender_address}: "
                f"{len(request.chunk_summaries)} chunks, "
                f"{len(request.tombstones)} tombstones"
            )

            for tombstone in request.tombstones:
                if not self.chunk_index.is_tombstoned(tombstone.chunk_id):
                    if self.chunk_index.chunk_exists(tombstone.chunk_id):
                        delete_chunk(tombstone.chunk_id)

                    self.chunk_index.add_tombstone(
                        tombstone.chunk_id,
                        tombstone.checksum
                    )
                    logger.info(f"Applied tombstone for chunk {tombstone.chunk_id}")

            my_chunk_ids = set(self.chunk_index.get_all_chunk_ids())
            received_chunk_ids = {cs.chunk_id for cs in request.chunk_summaries}
            missing_chunk_ids = list(received_chunk_ids - my_chunk_ids)

            missing_chunk_ids = [
                cid for cid in missing_chunk_ids
                if not self.chunk_index.is_tombstoned(cid)
            ]

            response = ChunkGossipResponse(
                peer_address=self._get_my_address(),
                missing_chunk_ids=missing_chunk_ids
            )

            logger.info(
                f"Chunk gossip processed from {request.sender_address}: "
                f"missing {len(missing_chunk_ids)} chunks"
            )

            return response.to_json()

        except Exception as e:
            logger.error(f"Error processing chunk gossip: {e}", exc_info=True)
            raise

    async def GetChunkStateSummary(self, request_bytes: bytes) -> bytes:
        """
        Handle state summary request for anti-entropy.

        Returns complete list of chunk IDs and tombstones.

        Args:
            request_bytes: Empty request

        Returns:
            Serialized ChunkStateSummary
        """
        try:
            chunk_ids = self.chunk_index.get_all_chunk_ids()
            tombstone_ids = self.chunk_index.get_all_tombstone_ids()

            total_size = sum(
                entry.size
                for entry in [self.chunk_index.get_chunk(cid) for cid in chunk_ids]
                if entry
            )

            response = ChunkStateSummary(
                peer_address=self._get_my_address(),
                chunk_ids=chunk_ids,
                tombstone_ids=tombstone_ids,
                chunk_count=len(chunk_ids),
                total_size_bytes=total_size
            )

            logger.debug(
                f"Chunk state summary requested: "
                f"{len(chunk_ids)} chunks, {len(tombstone_ids)} tombstones, "
                f"{total_size} bytes"
            )

            return response.to_json()

        except Exception as e:
            logger.error(f"Error getting chunk state summary: {e}", exc_info=True)
            raise

    async def FetchChunkData(
        self,
        request_bytes: bytes,
        context: grpc.aio.ServicerContext
    ) -> AsyncIterator[bytes]:
        """
        Handle request to fetch chunk data for replication (server streaming).

        Streams:
        1. FetchChunkResponse with metadata
        2. ChunkMetadata
        3. ChunkDataPiece(s)

        Args:
            request_bytes: Serialized FetchChunkRequest
            context: gRPC context

        Yields:
            Serialized response messages
        """
        try:
            request = FetchChunkRequest.from_json(request_bytes)
            chunk_id = request.chunk_id

            logger.info(f"Fetching chunk {chunk_id} for replication")

            entry = self.chunk_index.get_chunk(chunk_id)
            if not entry:
                logger.error(f"Chunk {chunk_id} not found for replication")
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Chunk {chunk_id} not found"
                )
                return

            response = FetchChunkResponse(
                chunk_id=chunk_id,
                checksum=entry.checksum,
                size=entry.size,
                exists=True
            )
            yield response.to_json()

            metadata = ChunkMetadata(
                chunk_id=entry.chunk_id,
                file_id=entry.file_id,
                chunk_index=entry.chunk_index,
                total_size=entry.size,
                checksum=entry.checksum
            )
            metadata_response = ReadChunkResponse(metadata=metadata)
            yield metadata_response.to_json()

            for piece in read_chunk_streaming(chunk_id, STREAM_PIECE_SIZE_BYTES):
                data_piece = ChunkDataPiece(data=piece)
                data_response = ReadChunkResponse(data=data_piece)
                yield data_response.to_json()

            logger.info(f"Successfully streamed chunk {chunk_id} for replication")

        except FileNotFoundError:
            logger.error(f"Chunk file not found during replication: {chunk_id}")
            await context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Chunk file not found: {chunk_id}"
            )
        except Exception as e:
            logger.error(
                f"Error fetching chunk {chunk_id} for replication: {e}",
                exc_info=True
            )
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Error fetching chunk: {str(e)}"
            )

    async def PushTombstones(self, request_bytes: bytes) -> bytes:
        """
        Handle incoming tombstone push.

        Processes deletion tombstones to prevent chunk resurrection.

        Args:
            request_bytes: Serialized PushTombstonesRequest

        Returns:
            Serialized PushTombstonesResponse
        """
        try:
            request = PushTombstonesRequest.from_json(request_bytes)

            processed_count = 0
            for tombstone in request.tombstones:
                if not self.chunk_index.is_tombstoned(tombstone.chunk_id):
                    if self.chunk_index.chunk_exists(tombstone.chunk_id):
                        delete_chunk(tombstone.chunk_id)

                    self.chunk_index.add_tombstone(
                        tombstone.chunk_id,
                        tombstone.checksum
                    )
                    processed_count += 1

                    logger.info(
                        f"Applied tombstone for chunk {tombstone.chunk_id} "
                        f"(deleted_at={tombstone.deleted_at})"
                    )

            response = PushTombstonesResponse(
                success=True,
                processed_count=processed_count
            )

            logger.info(f"Processed {processed_count} tombstones")

            return response.to_json()

        except Exception as e:
            logger.error(f"Error processing tombstones: {e}", exc_info=True)
            response = PushTombstonesResponse(
                success=False,
                processed_count=0,
                error_message=str(e)
            )
            return response.to_json()

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
