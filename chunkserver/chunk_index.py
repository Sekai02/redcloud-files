"""In-memory index: chunk_id -> metadata (file_id, chunk_index, length, checksum)."""

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict
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


class ChunkIndex:
    """
    In-memory index mapping chunk_id to chunk metadata.
    Supports persistence to/from JSON file and rebuilding from disk.
    """
    
    def __init__(self):
        """Initialize empty chunk index."""
        self._index: Dict[str, ChunkIndexEntry] = {}
    
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
    
    def load_from_disk(self, path: Optional[Path] = None) -> bool:
        """
        Load index from JSON file.
        
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
            for chunk_id, entry_dict in data.items():
                entry = ChunkIndexEntry(**entry_dict)
                self._index[chunk_id] = entry
            
            logger.info(f"Loaded {len(self._index)} chunks from index file")
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse index file: {e}")
            raise
    
    def save_to_disk(self, path: Optional[Path] = None) -> None:
        """
        Persist index to JSON file.
        
        Args:
            path: Path to JSON file (default: /data/chunk_index.json)
            
        Raises:
            OSError: If write operation fails
        """
        if path is None:
            path = INDEX_FILE_PATH
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            chunk_id: asdict(entry)
            for chunk_id, entry in self._index.items()
        }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved {len(self._index)} chunks to index file")
    
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
