"""Configuration settings for the Controller server."""

import os
from common.constants import CHUNK_SIZE_BYTES, CHUNKSERVER_SERVICE_NAME, CHUNKSERVER_PORT


DATABASE_PATH = os.environ.get("DFS_DATABASE_PATH", "/app/data/metadata.db")

CONTROLLER_HOST = os.environ.get("DFS_CONTROLLER_HOST", "0.0.0.0")

CONTROLLER_PORT = int(os.environ.get("DFS_CONTROLLER_PORT", "8000"))

API_KEY_PREFIX = "dfs_"
