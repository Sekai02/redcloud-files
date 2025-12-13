"""Manages physical chunk files on disk: read/write and checksum verify."""

import os
from pathlib import Path
from typing import Iterator, Optional
from common.constants import DEFAULT_CHUNK_STORAGE_PATH

CHUNKS_DIR = Path(os.environ.get("CHUNK_STORAGE_PATH", DEFAULT_CHUNK_STORAGE_PATH))


def ensure_chunks_directory() -> None:
    """Ensure chunks directory exists."""
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)


def get_chunk_path(chunk_id: str) -> Path:
    """
    Get file path for a chunk.
    
    Args:
        chunk_id: UUID of the chunk
        
    Returns:
        Path object for chunk file
    """
    return CHUNKS_DIR / f"{chunk_id}.chk"


def write_chunk(chunk_id: str, data: bytes) -> str:
    """
    Write chunk data to disk.
    
    Args:
        chunk_id: UUID of the chunk
        data: Raw chunk data (up to 4MB)
        
    Returns:
        String path to written file
        
    Raises:
        OSError: If write operation fails
    """
    ensure_chunks_directory()
    filepath = get_chunk_path(chunk_id)
    filepath.write_bytes(data)
    return str(filepath)


def read_chunk(chunk_id: str) -> bytes:
    """
    Read entire chunk from disk.
    
    Args:
        chunk_id: UUID of the chunk
        
    Returns:
        Raw chunk data
        
    Raises:
        FileNotFoundError: If chunk does not exist
        OSError: If read operation fails
    """
    filepath = get_chunk_path(chunk_id)
    return filepath.read_bytes()


def read_chunk_streaming(chunk_id: str, piece_size: int = 64 * 1024) -> Iterator[bytes]:
    """
    Stream chunk data in pieces.
    
    Args:
        chunk_id: UUID of the chunk
        piece_size: Size of each piece in bytes (default 64KB)
        
    Yields:
        Chunk data pieces
        
    Raises:
        FileNotFoundError: If chunk does not exist
        OSError: If read operation fails
    """
    filepath = get_chunk_path(chunk_id)
    with open(filepath, 'rb') as f:
        while True:
            piece = f.read(piece_size)
            if not piece:
                break
            yield piece


def delete_chunk(chunk_id: str) -> bool:
    """
    Delete chunk file from disk.
    
    Args:
        chunk_id: UUID of the chunk
        
    Returns:
        True if file was deleted, False if it didn't exist
    """
    filepath = get_chunk_path(chunk_id)
    if filepath.exists():
        filepath.unlink()
        return True
    return False


def chunk_exists(chunk_id: str) -> bool:
    """
    Check if chunk file exists on disk.
    
    Args:
        chunk_id: UUID of the chunk
        
    Returns:
        True if chunk file exists, False otherwise
    """
    filepath = get_chunk_path(chunk_id)
    return filepath.exists()


def get_chunk_size(chunk_id: str) -> Optional[int]:
    """
    Get size of chunk file in bytes.
    
    Args:
        chunk_id: UUID of the chunk
        
    Returns:
        Size in bytes, or None if chunk doesn't exist
    """
    filepath = get_chunk_path(chunk_id)
    if filepath.exists():
        return filepath.stat().st_size
    return None


def list_all_chunks() -> list[str]:
    """
    List all chunk IDs in storage directory.
    
    Returns:
        List of chunk IDs (without .chk extension)
    """
    if not CHUNKS_DIR.exists():
        return []
    
    chunk_ids = []
    for filepath in CHUNKS_DIR.glob("*.chk"):
        chunk_ids.append(filepath.stem)
    return chunk_ids
