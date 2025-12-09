"""Shared data type definitions (FileMeta, ChunkDescriptor, ChunkRecord, etc.)."""

from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass(frozen=True)
class ChunkDescriptor:
    """
    Metadata for a single file chunk.
    """
    chunk_id: str
    chunk_index: int
    size: int
    checksum: str


@dataclass(frozen=True)
class FileMetadata:
    """
    Complete metadata for a file in the system.
    """
    file_id: str
    name: str
    size: int
    tags: List[str]
    owner_id: str
    created_at: datetime
