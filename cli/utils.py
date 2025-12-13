"""Utility functions for CLI operations."""

import sys
from cli.constants import GREEN, RESET


class ProgressFileWrapper:
    """File-like wrapper that displays upload progress to stdout."""

    def __init__(self, file_path: str, file_size: int, filename: str):
        """
        Initialize the progress file wrapper.

        Args:
            file_path: Absolute path to the file to read
            file_size: Total size of the file in bytes
            filename: Display name for the file
        """
        self.file_path = file_path
        self.file_size = file_size
        self.filename = filename
        self._file = open(file_path, 'rb')
        self._uploaded = 0
        self._finished = False

    def read(self, size: int = -1) -> bytes:
        """
        Read bytes from the file and update progress display.

        Args:
            size: Number of bytes to read (-1 or 0 for default chunk size)

        Returns:
            Bytes read from the file
        """
        chunk = self._file.read(size if size > 0 else 8192)
        if chunk:
            self._uploaded += len(chunk)
            self._display_progress()
        elif not self._finished:
            self._finish_progress()
        return chunk

    def _display_progress(self) -> None:
        """Display current upload progress to stdout."""
        progress = (self._uploaded / self.file_size) * 100
        uploaded_str = format_file_size(self._uploaded)
        total_str = format_file_size(self.file_size)
        sys.stdout.write(
            f"\rUploading {self.filename}: {uploaded_str} / {total_str} ({GREEN}{progress:.1f}%{RESET})"
        )
        sys.stdout.flush()

    def _finish_progress(self) -> None:
        """Finalize progress display with newline."""
        self._finished = True
        sys.stdout.write('\n')
        sys.stdout.flush()

    def close(self) -> None:
        """Close the underlying file."""
        if self._file:
            self._file.close()

    def __enter__(self) -> 'ProgressFileWrapper':
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and ensure file is closed."""
        self.close()


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human-readable format with appropriate unit.
    
    Uses binary units (1024-based) and automatically selects the most
    appropriate unit (B, KiB, MiB, GiB, TiB).
    
    Args:
        size_bytes: File size in bytes
        
    Returns:
        Formatted string with size and unit (e.g., "1.50 MiB", "512 B")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    
    units = ['KiB', 'MiB', 'GiB', 'TiB']
    size = size_bytes / 1024.0
    
    for unit in units:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    
    return f"{size:.2f} PiB"
