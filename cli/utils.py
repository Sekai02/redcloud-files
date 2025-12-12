"""Utility functions for CLI operations."""


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
