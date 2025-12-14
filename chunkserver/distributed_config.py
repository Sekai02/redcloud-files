"""Distributed system configuration for chunkservers."""

import os
import socket
import time


def get_container_ip():
    """
    Get chunkserver's IP address on Docker network.

    Uses routing table approach to find the correct interface IP.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
    finally:
        s.close()
    return ip


CHUNKSERVER_NODE_ID = os.getenv("CHUNKSERVER_NODE_ID") or f"{socket.gethostname()}-{int(time.time())}"

CHUNKSERVER_ADVERTISE_ADDR = os.getenv("CHUNKSERVER_ADVERTISE_ADDR") or f"{get_container_ip()}:50051"

CHUNK_STORAGE_PATH = os.getenv("CHUNK_STORAGE_PATH", "/app/data/chunks")
CHUNK_INDEX_PATH = os.getenv("CHUNK_INDEX_PATH", "/app/data/chunk_index.json")

CONTROLLER_SERVICE_NAME = os.getenv("CONTROLLER_SERVICE_NAME", "controller")
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "10"))

DNS_REFRESH_INTERVAL = int(os.getenv("DNS_REFRESH_INTERVAL", "30"))
CONTROLLER_FAILURE_THRESHOLD = int(os.getenv("CONTROLLER_FAILURE_THRESHOLD", "3"))
