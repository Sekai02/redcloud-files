"""Distributed system configuration for controllers."""

import os
import socket
import time


def get_container_ip():
    """
    Get container's IP address on Docker network.

    Uses routing table approach to find the correct interface IP.
    Handles containers with multiple network interfaces correctly.
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


CONTROLLER_NODE_ID = os.getenv("CONTROLLER_NODE_ID") or f"{socket.gethostname()}-{int(time.time())}"

CONTROLLER_ADVERTISE_ADDR = os.getenv("CONTROLLER_ADVERTISE_ADDR") or f"{get_container_ip()}:8000"

DATABASE_PATH = os.getenv("DATABASE_PATH") or f"/app/data/controller-{CONTROLLER_NODE_ID}/redcloud.db"

MIN_CHUNK_REPLICAS = int(os.getenv("MIN_CHUNK_REPLICAS", "1"))

GOSSIP_INTERVAL = int(os.getenv("GOSSIP_INTERVAL", "5"))
ANTI_ENTROPY_INTERVAL = int(os.getenv("ANTI_ENTROPY_INTERVAL", "30"))
GOSSIP_FANOUT = int(os.getenv("GOSSIP_FANOUT", "2"))

CONTROLLER_SERVICE_NAME = os.getenv("CONTROLLER_SERVICE_NAME", "controller")

REPAIR_INTERVAL = int(os.getenv("REPAIR_INTERVAL", "60"))
HEARTBEAT_TIMEOUT = int(os.getenv("HEARTBEAT_TIMEOUT", "30"))
