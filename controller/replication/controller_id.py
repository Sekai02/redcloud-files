"""
Controller ID generation and persistence.

Each controller instance has a unique UUID that persists across restarts
within a session. This ID is used in vector clocks and operation tracking.
"""

import uuid
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

DEFAULT_CONTROLLER_ID_PATH = "/app/data/controller_id.txt"


def get_controller_id(path: str = DEFAULT_CONTROLLER_ID_PATH) -> str:
    """
    Get or generate controller ID.

    If controller ID file exists, read and return it.
    Otherwise, generate new UUID and persist to file.

    Args:
        path: Path to controller ID file

    Returns:
        Controller UUID string
    """
    id_path = Path(path)

    if id_path.exists():
        try:
            controller_id = id_path.read_text().strip()
            logger.info(f"Loaded existing controller ID: {controller_id}")
            return controller_id
        except Exception as e:
            logger.warning(f"Failed to read controller ID from {path}: {e}. Generating new ID.")

    controller_id = str(uuid.uuid4())

    id_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        id_path.write_text(controller_id)
        logger.info(f"Generated and saved new controller ID: {controller_id}")
    except Exception as e:
        logger.error(f"Failed to write controller ID to {path}: {e}")

    return controller_id
