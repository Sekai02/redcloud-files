"""Configuration settings for the Controller server."""

import os


DATABASE_PATH = os.environ.get("DFS_DATABASE_PATH", "./data/metadata.db")

CONTROLLER_HOST = os.environ.get("DFS_CONTROLLER_HOST", "0.0.0.0")

CONTROLLER_PORT = int(os.environ.get("DFS_CONTROLLER_PORT", "8000"))

CHUNK_SIZE_BYTES = 4 * 1024 * 1024

API_KEY_PREFIX = "dfs_"

CHUNKSERVER_ADDRESS = os.environ.get("DFS_CHUNKSERVER_ADDRESS", "chunkserver:50051")
