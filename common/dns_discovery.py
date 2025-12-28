"""DNS-based service discovery for RedCloud Files distributed system."""

import socket
import logging
from typing import List

from common.constants import (
    CONTROLLER_SERVICE_NAME,
    CONTROLLER_PORT,
    CHUNKSERVER_SERVICE_NAME,
    CHUNKSERVER_PORT
)

logger = logging.getLogger(__name__)


def discover_peers(hostname: str, port: int, family: socket.AddressFamily = socket.AF_INET) -> List[str]:
    """
    Discover all peer instances via DNS lookup.

    Uses socket.getaddrinfo() to resolve DNS alias to multiple IP addresses.
    Filters to IPv4 by default to match Docker DNS behavior and avoid duplicates.

    Args:
        hostname: DNS alias to resolve (e.g., 'controller', 'chunkserver')
        port: Service port number
        family: Address family filter (default: IPv4 only)

    Returns:
        List of "IP:PORT" strings for all discovered peers, sorted for determinism.
        Returns empty list if no peers found.

    Raises:
        socket.gaierror: If DNS resolution fails
        ValueError: If hostname or port is invalid
    """
    if not hostname:
        raise ValueError("hostname cannot be empty")
    if port <= 0 or port > 65535:
        raise ValueError(f"Invalid port number: {port}")

    try:
        results = socket.getaddrinfo(hostname, port, family, socket.SOCK_STREAM)

        unique_ips = set()
        for result in results:
            sockaddr = result[4]
            ip_address = sockaddr[0]
            unique_ips.add(ip_address)

        peer_addresses = sorted([f"{ip}:{port}" for ip in unique_ips])

        if peer_addresses:
            logger.info(f"DNS discovery: {hostname} -> {len(peer_addresses)} peer(s) found {peer_addresses}")
        else:
            logger.info(f"DNS discovery: {hostname} -> 0 peers found")

        return peer_addresses

    except socket.gaierror as e:
        logger.error(f"DNS discovery failed for '{hostname}': {e}")
        raise


def discover_controller_peers() -> List[str]:
    """
    Discover all controller instances via DNS.

    Resolves the 'controller' DNS alias to find all controller instances
    in the Docker Swarm overlay network.

    Returns:
        List of controller addresses in format ["IP:8000", ...]

    Raises:
        socket.gaierror: If 'controller' DNS alias doesn't resolve
    """
    return discover_peers(CONTROLLER_SERVICE_NAME, CONTROLLER_PORT)


def discover_chunkserver_peers() -> List[str]:
    """
    Discover all chunkserver instances via DNS.

    Resolves the 'chunkserver' DNS alias to find all chunkserver instances
    in the Docker Swarm overlay network.

    Returns:
        List of chunkserver addresses in format ["IP:50051", ...]

    Raises:
        socket.gaierror: If 'chunkserver' DNS alias doesn't resolve
    """
    return discover_peers(CHUNKSERVER_SERVICE_NAME, CHUNKSERVER_PORT)


def validate_dns_resolution(hostname: str, port: int) -> bool:
    """
    Validate that a DNS alias resolves to at least one IP address.

    Non-throwing wrapper for startup validation. Useful for checking
    if peer services are available without raising exceptions.

    Args:
        hostname: DNS alias to validate (e.g., 'controller', 'chunkserver')
        port: Service port number

    Returns:
        True if DNS resolves to at least one address, False otherwise
    """
    try:
        peers = discover_peers(hostname, port)
        return len(peers) > 0
    except (socket.gaierror, ValueError):
        return False


def get_peer_count(hostname: str, port: int) -> int:
    """
    Count number of peers discovered via DNS.

    Non-throwing wrapper that returns a count. Useful for metrics
    and observability.

    Args:
        hostname: DNS alias to query
        port: Service port number

    Returns:
        Number of IP addresses resolved (0 if resolution fails)
    """
    try:
        peers = discover_peers(hostname, port)
        return len(peers)
    except (socket.gaierror, ValueError):
        return 0
