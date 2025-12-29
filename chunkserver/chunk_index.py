"""In-memory index: chunk_id -> metadata (file_id, chunk_index, length, checksum)."""

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timezone
import logging

from chunkserver.chunk_storage import list_all_chunks, get_chunk_size, get_chunk_path
from chunkserver.checksum_validator import compute_checksum
from common.constants import DEFAULT_CHUNK_INDEX_PATH

logger = logging.getLogger(__name__)

INDEX_FILE_PATH = Path(os.environ.get("CHUNK_INDEX_PATH", DEFAULT_CHUNK_INDEX_PATH))


@dataclass
class ChunkIndexEntry:
    """
    Metadata entry for a chunk in the index.
    """
    chunk_id: str
    file_id: str
    chunk_index: int
    size: int
    checksum: str
    filepath: str


@dataclass
class TombstoneEntry:
    """
    Represents a deleted chunk to prevent resurrection after partitions.
    """
    chunk_id: str
    deleted_at: str
    checksum: str


class ChunkIndex:
    """
    In-memory index mapping chunk_id to chunk metadata.
    Supports persistence to/from JSON file and rebuilding from disk.
    Tracks tombstones for deleted chunks to prevent resurrection.
    """

    def __init__(self):
        """Initialize empty chunk index."""
        self._index: Dict[str, ChunkIndexEntry] = {}
        self._tombstones: Dict[str, TombstoneEntry] = {}
    
    def add_chunk(self, entry: ChunkIndexEntry) -> None:
        """
        Add or update chunk entry in index.
        
        Args:
            entry: ChunkIndexEntry to add
        """
        self._index[entry.chunk_id] = entry
    
    def get_chunk(self, chunk_id: str) -> Optional[ChunkIndexEntry]:
        """
        Retrieve chunk metadata by ID.
        
        Args:
            chunk_id: UUID of the chunk
            
        Returns:
            ChunkIndexEntry if found, None otherwise
        """
        return self._index.get(chunk_id)
    
    def remove_chunk(self, chunk_id: str) -> bool:
        """
        Remove chunk from index.
        
        Args:
            chunk_id: UUID of the chunk
            
        Returns:
            True if chunk was removed, False if not found
        """
        if chunk_id in self._index:
            del self._index[chunk_id]
            return True
        return False
    
    def chunk_exists(self, chunk_id: str) -> bool:
        """
        Check if chunk exists in index.
        
        Args:
            chunk_id: UUID of the chunk
            
        Returns:
            True if chunk is in index, False otherwise
        """
        return chunk_id in self._index
    
    def get_all_chunk_ids(self) -> list[str]:
        """
        Get list of all chunk IDs in index.

        Returns:
            List of chunk IDs
        """
        return list(self._index.keys())

    def count(self) -> int:
        """
        Get number of chunks in index.

        Returns:
            Count of chunks
        """
        return len(self._index)

    def add_tombstone(self, chunk_id: str, checksum: str) -> None:
        """
        Add tombstone for deleted chunk.
        Removes chunk from index if present.

        Args:
            chunk_id: UUID of the deleted chunk
            checksum: Last known checksum before deletion
        """
        if chunk_id in self._index:
            del self._index[chunk_id]

        deleted_at = datetime.now(timezone.utc).isoformat()
        tombstone = TombstoneEntry(
            chunk_id=chunk_id,
            deleted_at=deleted_at,
            checksum=checksum
        )
        self._tombstones[chunk_id] = tombstone
        logger.debug(f"Added tombstone for chunk {chunk_id}")

    def get_tombstone(self, chunk_id: str) -> Optional[TombstoneEntry]:
        """
        Get tombstone entry if exists.

        Args:
            chunk_id: UUID of the chunk

        Returns:
            TombstoneEntry if chunk is tombstoned, None otherwise
        """
        return self._tombstones.get(chunk_id)

    def is_tombstoned(self, chunk_id: str) -> bool:
        """
        Check if chunk is tombstoned.

        Args:
            chunk_id: UUID of the chunk

        Returns:
            True if chunk has a tombstone, False otherwise
        """
        return chunk_id in self._tombstones

    def get_all_tombstone_ids(self) -> list[str]:
        """
        Get list of all tombstoned chunk IDs.

        Returns:
            List of chunk IDs that are tombstoned
        """
        return list(self._tombstones.keys())

    def prune_old_tombstones(self, max_age_days: int = 30) -> int:
        """
        Remove tombstones older than max_age_days.

        Args:
            max_age_days: Maximum age in days before pruning tombstone

        Returns:
            Number of tombstones pruned
        """
        now = datetime.now(timezone.utc)
        to_remove = []

        for chunk_id, tombstone in self._tombstones.items():
            try:
                deleted_at = datetime.fromisoformat(tombstone.deleted_at)
                age_days = (now - deleted_at).days

                if age_days > max_age_days:
                    to_remove.append(chunk_id)
            except (ValueError, AttributeError) as e:
                logger.warning(f"Invalid tombstone timestamp for {chunk_id}: {e}")

        for chunk_id in to_remove:
            del self._tombstones[chunk_id]

        if to_remove:
            logger.info(f"Pruned {len(to_remove)} tombstones older than {max_age_days} days")

        return len(to_remove)
    
    def load_from_disk(self, path: Optional[Path] = None) -> bool:
        """
        Load index and tombstones from JSON file.

        Args:
            path: Path to JSON file (default: /data/chunk_index.json)

        Returns:
            True if loaded successfully, False if file doesn't exist

        Raises:
            json.JSONDecodeError: If file is corrupted
        """
        if path is None:
            path = INDEX_FILE_PATH

        if not path.exists():
            logger.warning(f"Index file not found at {path}")
            return False

        try:
            with open(path, 'r') as f:
                data = json.load(f)

            self._index.clear()
            self._tombstones.clear()

            if isinstance(data, dict) and 'chunks' in data:
                for chunk_id, entry_dict in data.get('chunks', {}).items():
                    entry = ChunkIndexEntry(**entry_dict)
                    self._index[chunk_id] = entry

                for chunk_id, tombstone_dict in data.get('tombstones', {}).items():
                    tombstone = TombstoneEntry(**tombstone_dict)
                    self._tombstones[chunk_id] = tombstone

                logger.info(
                    f"Loaded {len(self._index)} chunks and {len(self._tombstones)} tombstones from index file"
                )
            else:
                for chunk_id, entry_dict in data.items():
                    entry = ChunkIndexEntry(**entry_dict)
                    self._index[chunk_id] = entry

                logger.info(f"Loaded {len(self._index)} chunks from index file (legacy format)")

            return True
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse index file: {e}")
            raise
    
    def save_to_disk(self, path: Optional[Path] = None) -> None:
        """
        Persist index and tombstones to JSON file.

        Args:
            path: Path to JSON file (default: /data/chunk_index.json)

        Raises:
            OSError: If write operation fails
        """
        if path is None:
            path = INDEX_FILE_PATH

        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'chunks': {
                chunk_id: asdict(entry)
                for chunk_id, entry in self._index.items()
            },
            'tombstones': {
                chunk_id: asdict(tombstone)
                for chunk_id, tombstone in self._tombstones.items()
            }
        }

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(
            f"Saved {len(self._index)} chunks and {len(self._tombstones)} tombstones to index file"
        )
    
    def rebuild_from_directory(self, verify_checksums: bool = False) -> int:
        """
        Rebuild index by scanning chunks directory.
        WARNING: This loses file_id and chunk_index information.
        
        Args:
            verify_checksums: If True, compute and verify checksums (slow)
            
        Returns:
            Number of chunks added to index
        """
        logger.info("Rebuilding index from disk...")
        
        self._index.clear()
        chunk_ids = list_all_chunks()
        
        for chunk_id in chunk_ids:
            size = get_chunk_size(chunk_id)
            filepath = str(get_chunk_path(chunk_id))
            
            if size is None:
                continue
            
            checksum = ""
            if verify_checksums:
                try:
                    with open(filepath, 'rb') as f:
                        data = f.read()
                        checksum = compute_checksum(data)
                except Exception as e:
                    logger.error(f"Failed to compute checksum for {chunk_id}: {e}")
                    continue
            
            entry = ChunkIndexEntry(
                chunk_id=chunk_id,
                file_id="unknown",
                chunk_index=-1,
                size=size,
                checksum=checksum,
                filepath=filepath
            )
            
            self._index[chunk_id] = entry
        
        logger.info(f"Rebuilt index with {len(self._index)} chunks")
        return len(self._index)
