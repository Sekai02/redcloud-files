"""Configuration settings for the Controller server."""

import os
from common.constants import CHUNK_SIZE_BYTES, CHUNKSERVER_SERVICE_NAME, CHUNKSERVER_PORT

try:
    from controller.distributed_config import DATABASE_PATH, CONTROLLER_NODE_ID, CONTROLLER_ADVERTISE_ADDR
except ImportError:
    DATABASE_PATH = os.environ.get("DFS_DATABASE_PATH", "/app/data/metadata.db")
    CONTROLLER_NODE_ID = "controller-1"
    CONTROLLER_ADVERTISE_ADDR = "localhost:8000"

CONTROLLER_HOST = os.environ.get("DFS_CONTROLLER_HOST", "0.0.0.0")

CONTROLLER_PORT = int(os.environ.get("DFS_CONTROLLER_PORT", "8000"))

API_KEY_PREFIX = "dfs_"

CHUNKSERVER_ADDRESS = os.environ.get("DFS_CHUNKSERVER_ADDRESS", f"{CHUNKSERVER_SERVICE_NAME}:{CHUNKSERVER_PORT}")
