"""Provides SHA-256 checksum calculation and verification helpers."""

import hashlib
from typing import Optional


def compute_checksum(data: bytes) -> str:
    """
    Compute SHA-256 checksum for given data.
    
    Args:
        data: Bytes to compute checksum for
        
    Returns:
        Hexadecimal string representation of SHA-256 hash
    """
    return hashlib.sha256(data).hexdigest()


def verify_checksum(data: bytes, expected: str) -> bool:
    """
    Verify that data matches expected checksum.
    
    Args:
        data: Bytes to verify
        expected: Expected SHA-256 checksum (hex string)
        
    Returns:
        True if checksum matches, False otherwise
    """
    actual = compute_checksum(data)
    return actual == expected


class IncrementalChecksumCalculator:
    """
    Calculate SHA-256 checksum incrementally for streaming data.
    
    Usage:
        calculator = IncrementalChecksumCalculator()
        calculator.update(chunk1)
        calculator.update(chunk2)
        final_checksum = calculator.finalize()
    """
    
    def __init__(self):
        """Initialize a new incremental checksum calculator."""
        self._hasher = hashlib.sha256()
        self._finalized = False
    
    def update(self, data: bytes) -> None:
        """
        Update checksum with new data.
        
        Args:
            data: Bytes to add to checksum calculation
        """
        if self._finalized:
            raise ValueError("Cannot update after finalization")
        self._hasher.update(data)
    
    def finalize(self) -> str:
        """
        Finalize checksum calculation and return result.
        
        Returns:
            Hexadecimal string representation of SHA-256 hash
        """
        self._finalized = True
        return self._hasher.hexdigest()
    
    def reset(self) -> None:
        """Reset calculator to initial state."""
        self._hasher = hashlib.sha256()
        self._finalized = False
