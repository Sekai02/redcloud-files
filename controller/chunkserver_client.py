"""RPC client abstraction for sending chunk read/write requests to Chunkserver."""

import grpc
from typing import AsyncIterator
import logging
import asyncio

from common.protocol import (
    WriteChunkRequest,
    WriteChunkResponse,
    ReadChunkRequest,
    ReadChunkResponse,
    DeleteChunkRequest,
    DeleteChunkResponse,
    PingRequest,
    PingResponse,
    ChunkMetadata,
    ChunkDataPiece
)
from common.constants import (
    CHUNKSERVER_SERVICE_NAME,
    CHUNKSERVER_PORT,
    STREAM_PIECE_SIZE_BYTES,
    CHUNKSERVER_TIMEOUT_SECONDS,
    GRPC_KEEPALIVE_TIME_MS,
    GRPC_KEEPALIVE_TIMEOUT_MS
)
from controller.exceptions import (
    ChunkserverUnavailableError,
    ChecksumMismatchError,
    FileNotFoundError as DFSFileNotFoundError,
    StorageFullError
)

logger = logging.getLogger(__name__)


class ChunkserverClient:
    """
    gRPC client for chunkserver operations.
    Handles connection management and RPC calls.
    """
    
    def __init__(self):
        """Initialize client with lazy connection."""
        self._channel = None
        self._target = f"{CHUNKSERVER_SERVICE_NAME}:{CHUNKSERVER_PORT}"
    
    def _ensure_channel(self):
        """Ensure gRPC channel is established."""
        if self._channel is None:
            options = [
                ('grpc.keepalive_time_ms', GRPC_KEEPALIVE_TIME_MS),
                ('grpc.keepalive_timeout_ms', GRPC_KEEPALIVE_TIMEOUT_MS),
                ('grpc.keepalive_permit_without_calls', 1),
            ]
            self._channel = grpc.aio.insecure_channel(self._target, options=options)
            logger.info(f"Established gRPC channel to {self._target}")
    
    async def close(self):
        """Close gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
    
    async def _retry_with_backoff(self, operation, *args, max_retries=3, **kwargs):
        """
        Retry operation with exponential backoff for transient failures.
        
        Args:
            operation: Async function to retry
            max_retries: Maximum number of retry attempts
            *args, **kwargs: Arguments to pass to operation
            
        Returns:
            Result from successful operation
            
        Raises:
            Last exception if all retries exhausted
        """
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return await operation(*args, **kwargs)
            except grpc.RpcError as e:
                last_exception = e
                
                if e.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                    if attempt < max_retries - 1:
                        delay = 2 ** attempt
                        logger.warning(f"Transient failure, retrying in {delay}s (attempt {attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(delay)
                        continue
                
                raise
            except (ChecksumMismatchError, StorageFullError, DFSFileNotFoundError):
                raise
            except Exception as e:
                last_exception = e
                raise
        
        if last_exception:
            raise last_exception
    
    async def write_chunk(
        self,
        chunk_id: str,
        file_id: str,
        chunk_index: int,
        data: bytes,
        checksum: str
    ) -> bool:
        """
        Send chunk data to chunkserver for storage.
        
        Args:
            chunk_id: UUID of the chunk
            file_id: UUID of the file
            chunk_index: Index of chunk in file
            data: Raw chunk data (max 4MB)
            checksum: SHA-256 checksum of the data
            
        Returns:
            True if write successful, False otherwise
            
        Raises:
            ChunkserverUnavailableError: If chunkserver is unreachable
            ChecksumMismatchError: If checksum verification fails
            StorageFullError: If chunkserver disk is full
        """
        return await self._retry_with_backoff(
            self._write_chunk_internal,
            chunk_id, file_id, chunk_index, data, checksum
        )
    
    async def _write_chunk_internal(
        self,
        chunk_id: str,
        file_id: str,
        chunk_index: int,
        data: bytes,
        checksum: str
    ) -> bool:
        """Internal implementation of write_chunk without retry logic."""
        self._ensure_channel()
        
        try:
            async def request_generator():
                metadata = ChunkMetadata(
                    chunk_id=chunk_id,
                    file_id=file_id,
                    chunk_index=chunk_index,
                    total_size=len(data),
                    checksum=checksum
                )
                yield WriteChunkRequest(metadata=metadata).to_json()
                
                for i in range(0, len(data), STREAM_PIECE_SIZE_BYTES):
                    piece = data[i:i + STREAM_PIECE_SIZE_BYTES]
                    data_piece = ChunkDataPiece(data=piece)
                    yield WriteChunkRequest(data=data_piece).to_json()
            
            multi_callable = self._channel.stream_unary(
                '/chunkserver.ChunkserverService/WriteChunk',
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )
            
            response_bytes = await multi_callable(
                request_generator(),
                timeout=CHUNKSERVER_TIMEOUT_SECONDS
            )
            
            response = WriteChunkResponse.from_json(response_bytes)
            
            if not response.success:
                if response.error_message:
                    error_lower = response.error_message.lower()
                    if 'checksum' in error_lower:
                        raise ChecksumMismatchError(f"Chunkserver checksum verification failed: {response.error_message}")
                    if 'disk full' in error_lower or 'no space' in error_lower:
                        raise StorageFullError(f"Chunkserver storage full: {response.error_message}")
                raise Exception(f"Write failed: {response.error_message}")
            
            logger.info(f"Successfully wrote chunk {chunk_id}")
            return True
            
        except grpc.RpcError as e:
            if e.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                raise ChunkserverUnavailableError(f"Chunkserver unavailable: {e.details()}")
            logger.error(f"gRPC error writing chunk {chunk_id}: {e}")
            raise
        except ChecksumMismatchError:
            raise
        except Exception as e:
            logger.error(f"Error writing chunk {chunk_id}: {e}")
            raise
    
    async def read_chunk(self, chunk_id: str) -> AsyncIterator[bytes]:
        """
        Retrieve chunk data from chunkserver.

        Note: Streaming operations cannot use retry logic.
        The stream must succeed or fail in one attempt.

        Args:
            chunk_id: UUID of the chunk to retrieve

        Yields:
            Chunk data in streaming pieces

        Raises:
            ChunkserverUnavailableError: If chunkserver is unreachable
            FileNotFoundError: If chunk does not exist
        """
        async for piece in self._read_chunk_internal(chunk_id):
            yield piece
    
    async def _read_chunk_internal(self, chunk_id: str) -> AsyncIterator[bytes]:
        """Internal implementation of read_chunk without retry logic."""
        self._ensure_channel()
        
        try:
            request = ReadChunkRequest(chunk_id=chunk_id)
            
            multi_callable = self._channel.unary_stream(
                '/chunkserver.ChunkserverService/ReadChunk',
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )
            
            response_stream = multi_callable(
                request.to_json(),
                timeout=CHUNKSERVER_TIMEOUT_SECONDS
            )
            
            first_response = True
            async for response_bytes in response_stream:
                response = ReadChunkResponse.from_json(response_bytes)

                if first_response:
                    first_response = False
                    if response.metadata:
                        logger.info(f"Reading chunk {chunk_id}, size={response.metadata.total_size}")
                    if not response.data:
                        continue

                if response.data:
                    yield response.data.data
            
            logger.info(f"Successfully read chunk {chunk_id}")
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise DFSFileNotFoundError(f"Chunk {chunk_id} not found on chunkserver")
            if e.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                raise ChunkserverUnavailableError(f"Chunkserver unavailable: {e.details()}")
            logger.error(f"gRPC error reading chunk {chunk_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error reading chunk {chunk_id}: {e}")
            raise
    
    async def delete_chunk(self, chunk_id: str) -> bool:
        """
        Delete chunk from chunkserver storage.
        
        Args:
            chunk_id: UUID of the chunk to delete
            
        Returns:
            True if deletion successful, False otherwise
            
        Raises:
            ChunkserverUnavailableError: If chunkserver is unreachable
        """
        self._ensure_channel()
        
        try:
            request = DeleteChunkRequest(chunk_id=chunk_id)
            
            multi_callable = self._channel.unary_unary(
                '/chunkserver.ChunkserverService/DeleteChunk',
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )
            
            response_bytes = await multi_callable(
                request.to_json(),
                timeout=CHUNKSERVER_TIMEOUT_SECONDS
            )
            
            response = DeleteChunkResponse.from_json(response_bytes)
            
            if response.success:
                logger.info(f"Successfully deleted chunk {chunk_id}")
            else:
                logger.warning(f"Failed to delete chunk {chunk_id}: {response.error_message}")
            
            return response.success
            
        except grpc.RpcError as e:
            if e.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                raise ChunkserverUnavailableError(f"Chunkserver unavailable: {e.details()}")
            logger.error(f"gRPC error deleting chunk {chunk_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error deleting chunk {chunk_id}: {e}")
            raise
    
    async def ping(self) -> bool:
        """
        Check if chunkserver is available.
        
        Returns:
            True if chunkserver responds, False otherwise
        """
        self._ensure_channel()
        
        try:
            request = PingRequest()
            
            multi_callable = self._channel.unary_unary(
                '/chunkserver.ChunkserverService/Ping',
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )
            
            response_bytes = await multi_callable(
                request.to_json(),
                timeout=5
            )
            
            response = PingResponse.from_json(response_bytes)
            return response.available
            
        except Exception as e:
            logger.warning(f"Ping failed: {e}")
            return False
    
    async def get_stats(self) -> dict:
        """
        Get storage statistics from chunkserver.
        
        Returns:
            Dictionary with storage statistics (optional feature)
        """
        raise NotImplementedError("GetStats RPC not yet implemented")

