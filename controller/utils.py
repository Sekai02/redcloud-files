"""Utility helper functions for the Controller."""

import uuid
from datetime import datetime
from typing import List


def generate_uuid() -> str:
    """
    Generate a new UUID4 string.

    Returns:
        UUID4 string
    """
    return str(uuid.uuid4())


def get_current_timestamp() -> str:
    """
    Get current timestamp in ISO format.

    Returns:
        Current timestamp as ISO format string
    """
    return datetime.utcnow().isoformat()


def parse_tags(tags_str: str) -> List[str]:
    """
    Parse comma-separated tags string into list.

    Args:
        tags_str: Comma-separated tags (e.g., "tag1,tag2,tag3")

    Returns:
        List of trimmed tag strings
    """
    return [tag.strip() for tag in tags_str.split(',') if tag.strip()]
