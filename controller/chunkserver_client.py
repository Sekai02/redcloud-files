"""RPC client abstraction for sending chunk read/write requests to Chunkserver."""

from typing import AsyncIterator


class ChunkserverClient:
    """
    Abstract interface for chunkserver operations.
    Actual gRPC implementation should be added by the chunkserver developer.
    """
    
    async def write_chunk(self, chunk_id: str, data: bytes, checksum: str) -> bool:
        """
        Send chunk data to chunkserver for storage.
        
        Args:
            chunk_id: UUID of the chunk
            data: Raw chunk data (max 4MB)
            checksum: SHA-256 checksum of the data
            
        Returns:
            True if write successful, False otherwise
            
        Raises:
            ChunkserverUnavailableError: If chunkserver is unreachable
            ChecksumMismatchError: If checksum verification fails
        """
        raise NotImplementedError("TODO: Implement gRPC WriteChunk streaming call")
    
    async def read_chunk(self, chunk_id: str) -> AsyncIterator[bytes]:
        """
        Retrieve chunk data from chunkserver.
        
        Args:
            chunk_id: UUID of the chunk to retrieve
            
        Yields:
            Chunk data in streaming pieces
            
        Raises:
            ChunkserverUnavailableError: If chunkserver is unreachable
            FileNotFoundError: If chunk does not exist
        """
        raise NotImplementedError("TODO: Implement gRPC ReadChunk streaming call")
        yield b""
    
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
        raise NotImplementedError("TODO: Implement gRPC DeleteChunk unary call")
    
    async def ping(self) -> bool:
        """
        Check if chunkserver is available.
        
        Returns:
            True if chunkserver responds, False otherwise
        """
        raise NotImplementedError("TODO: Implement gRPC Ping call (optional)")
    
    async def get_stats(self) -> dict:
        """
        Get storage statistics from chunkserver.
        
        Returns:
            Dictionary with storage statistics (optional feature)
        """
        raise NotImplementedError("TODO: Implement gRPC GetStats call (optional)")

