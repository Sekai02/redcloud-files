"""gRPC server implementation for chunkserver."""

import grpc
from grpc import aio
import logging
import errno
from typing import AsyncIterator

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
    ChunkDataPiece,
    ListChunksRequest,
    ListChunksResponse,
    ChunkInfo,
    ReplicateChunkRequest,
    ReplicateChunkResponse
)
from common.constants import STREAM_PIECE_SIZE_BYTES
from chunkserver.chunk_index import ChunkIndex, ChunkIndexEntry
from chunkserver.chunk_storage import (
    write_chunk,
    read_chunk_streaming,
    delete_chunk,
    chunk_exists,
    get_chunk_path
)
from chunkserver.checksum_validator import (
    IncrementalChecksumCalculator,
    verify_checksum
)

logger = logging.getLogger(__name__)


class ChunkserverServicer:
    """
    gRPC service implementation for chunkserver operations.
    """
    
    def __init__(self, chunk_index: ChunkIndex):
        """
        Initialize servicer with chunk index.
        
        Args:
            chunk_index: ChunkIndex instance for metadata management
        """
        self.chunk_index = chunk_index
    
    async def WriteChunk(
        self,
        request_iterator: AsyncIterator[bytes],
        context: grpc.aio.ServicerContext
    ) -> bytes:
        """
        Handle WriteChunk RPC (client streaming).
        Receives metadata followed by data pieces, validates checksum, writes to disk.
        
        Args:
            request_iterator: Stream of WriteChunkRequest messages (serialized)
            context: gRPC context
            
        Returns:
            Serialized WriteChunkResponse
        """
        metadata = None
        data_buffer = bytearray()
        checksum_calculator = IncrementalChecksumCalculator()
        
        try:
            async for request_bytes in request_iterator:
                request = WriteChunkRequest.from_json(request_bytes)
                
                if request.metadata:
                    metadata = request.metadata
                    logger.info(f"Receiving chunk {metadata.chunk_id}, size={metadata.total_size}")
                
                if request.data:
                    data_buffer.extend(request.data.data)
                    checksum_calculator.update(request.data.data)
            
            if metadata is None:
                error_msg = "No metadata received in WriteChunk stream"
                logger.error(error_msg)
                response = WriteChunkResponse(success=False, error_message=error_msg)
                return response.to_json()
            
            computed_checksum = checksum_calculator.finalize()
            if computed_checksum != metadata.checksum:
                error_msg = f"Checksum mismatch for chunk {metadata.chunk_id}: expected {metadata.checksum}, got {computed_checksum}"
                logger.error(error_msg)
                response = WriteChunkResponse(success=False, error_message=error_msg)
                return response.to_json()
            
            if len(data_buffer) != metadata.total_size:
                error_msg = f"Size mismatch for chunk {metadata.chunk_id}: expected {metadata.total_size}, got {len(data_buffer)}"
                logger.error(error_msg)
                response = WriteChunkResponse(success=False, error_message=error_msg)
                return response.to_json()
            
            try:
                filepath = write_chunk(metadata.chunk_id, bytes(data_buffer))
            except OSError as os_error:
                if os_error.errno == errno.ENOSPC:
                    error_msg = f"Disk full: cannot write chunk {metadata.chunk_id}"
                    logger.error(error_msg)
                    response = WriteChunkResponse(success=False, error_message=error_msg)
                    return response.to_json()
                raise
            
            entry = ChunkIndexEntry(
                chunk_id=metadata.chunk_id,
                file_id=metadata.file_id,
                chunk_index=metadata.chunk_index,
                size=metadata.total_size,
                checksum=metadata.checksum,
                filepath=filepath
            )
            self.chunk_index.add_chunk(entry)
            
            logger.info(f"Successfully wrote chunk {metadata.chunk_id}")
            response = WriteChunkResponse(success=True)
            return response.to_json()
            
        except Exception as e:
            error_msg = f"Error writing chunk: {str(e)}"
            logger.error(error_msg, exc_info=True)
            response = WriteChunkResponse(success=False, error_message=error_msg)
            return response.to_json()
    
    async def ReadChunk(
        self,
        request_bytes: bytes,
        context: grpc.aio.ServicerContext
    ) -> AsyncIterator[bytes]:
        """
        Handle ReadChunk RPC (server streaming).
        Sends metadata followed by data pieces.
        
        Args:
            request_bytes: Serialized ReadChunkRequest
            context: gRPC context
            
        Yields:
            Serialized ReadChunkResponse messages
        """
        try:
            request = ReadChunkRequest.from_json(request_bytes)
            chunk_id = request.chunk_id
            
            logger.info(f"Reading chunk {chunk_id}")
            
            entry = self.chunk_index.get_chunk(chunk_id)
            if entry is None:
                logger.error(f"Chunk {chunk_id} not found in index")
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Chunk {chunk_id} not found")
                return
            
            metadata = ChunkMetadata(
                chunk_id=entry.chunk_id,
                file_id=entry.file_id,
                chunk_index=entry.chunk_index,
                total_size=entry.size,
                checksum=entry.checksum
            )
            response = ReadChunkResponse(metadata=metadata)
            yield response.to_json()
            
            for piece in read_chunk_streaming(chunk_id, STREAM_PIECE_SIZE_BYTES):
                data_piece = ChunkDataPiece(data=piece)
                response = ReadChunkResponse(data=data_piece)
                yield response.to_json()
            
            logger.info(f"Successfully streamed chunk {chunk_id}")
            
        except FileNotFoundError:
            logger.error(f"Chunk file not found: {chunk_id}")
            await context.abort(grpc.StatusCode.NOT_FOUND, f"Chunk file not found: {chunk_id}")
        except Exception as e:
            logger.error(f"Error reading chunk {chunk_id}: {str(e)}", exc_info=True)
            await context.abort(grpc.StatusCode.INTERNAL, f"Error reading chunk: {str(e)}")
    
    async def DeleteChunk(
        self,
        request_bytes: bytes,
        context: grpc.aio.ServicerContext
    ) -> bytes:
        """
        Handle DeleteChunk RPC (unary).
        Removes chunk file and updates index.
        
        Args:
            request_bytes: Serialized DeleteChunkRequest
            context: gRPC context
            
        Returns:
            Serialized DeleteChunkResponse
        """
        try:
            request = DeleteChunkRequest.from_json(request_bytes)
            chunk_id = request.chunk_id
            
            logger.info(f"Deleting chunk {chunk_id}")
            
            deleted = delete_chunk(chunk_id)
            self.chunk_index.remove_chunk(chunk_id)
            
            if deleted:
                logger.info(f"Successfully deleted chunk {chunk_id}")
                response = DeleteChunkResponse(success=True)
            else:
                logger.warning(f"Chunk {chunk_id} not found for deletion")
                response = DeleteChunkResponse(success=True, error_message="Chunk not found")
            
            return response.to_json()
            
        except Exception as e:
            error_msg = f"Error deleting chunk: {str(e)}"
            logger.error(error_msg, exc_info=True)
            response = DeleteChunkResponse(success=False, error_message=error_msg)
            return response.to_json()
    
    async def Ping(
        self,
        request_bytes: bytes,
        context: grpc.aio.ServicerContext
    ) -> bytes:
        """
        Handle Ping RPC (unary).
        Simple health check endpoint.
        
        Args:
            request_bytes: Serialized PingRequest
            context: gRPC context
            
        Returns:
            Serialized PingResponse
        """
        response = PingResponse(available=True)
        return response.to_json()

    async def ListChunks(
        self,
        request_bytes: bytes,
        context: grpc.aio.ServicerContext
    ) -> bytes:
        """
        Handle ListChunks RPC (unary).
        List all chunks stored on this chunkserver.

        Args:
            request_bytes: Serialized ListChunksRequest
            context: gRPC context

        Returns:
            Serialized ListChunksResponse
        """
        try:
            all_chunks = self.chunk_index.list_all()
            chunk_infos = []

            for chunk_id, entry in all_chunks.items():
                chunk_infos.append(ChunkInfo(
                    chunk_id=chunk_id,
                    file_id=entry.file_id,
                    chunk_index=entry.chunk_index,
                    size=entry.size,
                    checksum=entry.checksum
                ))

            response = ListChunksResponse(chunks=chunk_infos)
            return response.to_json()

        except Exception as e:
            logger.error(f"Failed to list chunks: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            response = ListChunksResponse(chunks=[])
            return response.to_json()

    async def ReplicateChunk(
        self,
        request_bytes: bytes,
        context: grpc.aio.ServicerContext
    ) -> bytes:
        """
        Handle ReplicateChunk RPC (unary).
        Replicate a chunk from another chunkserver.

        Args:
            request_bytes: Serialized ReplicateChunkRequest
            context: gRPC context

        Returns:
            Serialized ReplicateChunkResponse
        """
        request = ReplicateChunkRequest.from_json(request_bytes)
        chunk_id = request.chunk_id
        source_address = request.source_chunkserver_address

        try:
            async with grpc.aio.insecure_channel(source_address) as channel:
                read_request = ReadChunkRequest(chunk_id=chunk_id)

                response_stream = channel.unary_stream(
                    f'/chunkserver.ChunkserverService/ReadChunk',
                    request_serializer=lambda x: x,
                    response_deserializer=lambda x: x
                )(read_request.to_json())

                metadata = None
                chunk_data = bytearray()

                async for response_bytes in response_stream:
                    response = ReadChunkResponse.from_json(response_bytes)

                    if response.metadata:
                        metadata = response.metadata

                    if response.data:
                        chunk_data.extend(response.data.data)

                if metadata is None:
                    raise Exception(f"No metadata received for chunk {chunk_id}")

                write_chunk(
                    chunk_id=chunk_id,
                    data=bytes(chunk_data),
                    file_id=metadata.file_id,
                    chunk_index=metadata.chunk_index
                )

                self.chunk_index.add(
                    chunk_id=chunk_id,
                    file_id=metadata.file_id,
                    chunk_index=metadata.chunk_index,
                    size=metadata.total_size,
                    checksum=metadata.checksum
                )

                logger.info(f"Successfully replicated chunk {chunk_id} from {source_address}")
                response = ReplicateChunkResponse(success=True)
                return response.to_json()

        except Exception as e:
            logger.error(f"Failed to replicate chunk {chunk_id} from {source_address}: {e}", exc_info=True)
            response = ReplicateChunkResponse(success=False, error=str(e))
            return response.to_json()


def create_server(chunk_index: ChunkIndex) -> aio.Server:
    """
    Create and configure gRPC server.
    
    Args:
        chunk_index: ChunkIndex instance
        
    Returns:
        Configured gRPC server
    """
    server = aio.server()
    servicer = ChunkserverServicer(chunk_index)
    
    server.add_generic_rpc_handlers((
        grpc.method_handlers_generic_handler(
            'chunkserver.ChunkserverService',
            {
                'WriteChunk': grpc.stream_unary_rpc_method_handler(
                    servicer.WriteChunk,
                    request_deserializer=lambda x: x,
                    response_serializer=lambda x: x,
                ),
                'ReadChunk': grpc.unary_stream_rpc_method_handler(
                    servicer.ReadChunk,
                    request_deserializer=lambda x: x,
                    response_serializer=lambda x: x,
                ),
                'DeleteChunk': grpc.unary_unary_rpc_method_handler(
                    servicer.DeleteChunk,
                    request_deserializer=lambda x: x,
                    response_serializer=lambda x: x,
                ),
                'Ping': grpc.unary_unary_rpc_method_handler(
                    servicer.Ping,
                    request_deserializer=lambda x: x,
                    response_serializer=lambda x: x,
                ),
                'ListChunks': grpc.unary_unary_rpc_method_handler(
                    servicer.ListChunks,
                    request_deserializer=lambda x: x,
                    response_serializer=lambda x: x,
                ),
                'ReplicateChunk': grpc.unary_unary_rpc_method_handler(
                    servicer.ReplicateChunk,
                    request_deserializer=lambda x: x,
                    response_serializer=lambda x: x,
                ),
            }
        ),
    ))
    
    return server
