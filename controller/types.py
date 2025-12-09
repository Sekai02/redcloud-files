"""Controller-specific data type definitions."""

from dataclasses import dataclass
from datetime import datetime
from typing import List


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
