"""Shared data type definitions (ChunkDescriptor, etc.)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkDescriptor:
    """
    Metadata for a single file chunk.
    """
    chunk_id: str
    chunk_index: int
    size: int
    checksum: str
