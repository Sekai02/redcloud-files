"""DNS-based service discovery for Docker Swarm environments."""

import asyncio
import socket
from typing import Dict, List
from dataclasses import dataclass
from common.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ServiceInfo:
    """Information about a discovered service instance."""
    address: str
    seen_this_round: bool = True
    consecutive_failures: int = 0


class ServiceDiscoveryService:
    """
    DNS-based service discovery for Docker Swarm.

    Discovers all IP addresses for a service name via DNS lookups.
    In Docker Swarm mode, DNS returns all task IPs for a service.
    Maintains a list of discovered services and tracks failures.
    """

    def __init__(
        self,
        service_name: str,
        port: int = 8000,
        refresh_interval: int = 30,
        failure_threshold: int = 3
    ):
        """
        Initialize service discovery.

        Args:
            service_name: Docker service name to discover (e.g., 'controller')
            port: Service port
            refresh_interval: Seconds between DNS refreshes
            failure_threshold: Consecutive failures before removing service
        """
        self.service_name = service_name
        self.port = port
        self.refresh_interval = refresh_interval
        self.failure_threshold = failure_threshold

        self.services: Dict[str, ServiceInfo] = {}
        self.lock = asyncio.Lock()
        self.running = False

    async def start(self):
        """Start DNS discovery background loop."""
        self.running = True
        await self._discover_services()
        asyncio.create_task(self._discovery_loop())
        logger.info(
            f"Service discovery started for {self.service_name} "
            f"(refresh_interval={self.refresh_interval}s)"
        )

    async def stop(self):
        """Stop DNS discovery."""
        self.running = False
        logger.info(f"Service discovery stopped for {self.service_name}")

    async def _discovery_loop(self):
        """Periodically refresh service list via DNS."""
        while self.running:
            try:
                await asyncio.sleep(self.refresh_interval)
                await self._discover_services()
            except Exception as e:
                logger.error(f"Discovery loop error: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _discover_services(self):
        """
        Resolve DNS name to all service IPs.

        Uses socket.getaddrinfo() to get ALL IPs for the service.
        In Docker Swarm, this returns all task IPs for the service.
        """
        try:
            loop = asyncio.get_event_loop()
            addr_info = await loop.run_in_executor(
                None,
                socket.getaddrinfo,
                self.service_name,
                self.port,
                socket.AF_INET,
                socket.SOCK_STREAM
            )

            discovered_ips = set()
            for family, socktype, proto, canonname, sockaddr in addr_info:
                ip, port = sockaddr
                discovered_ips.add(ip)

            async with self.lock:
                for info in self.services.values():
                    info.seen_this_round = False

                for ip in discovered_ips:
                    address = f"{ip}:{self.port}"
                    if address in self.services:
                        self.services[address].seen_this_round = True
                        self.services[address].consecutive_failures = 0
                    else:
                        self.services[address] = ServiceInfo(
                            address=address,
                            seen_this_round=True,
                            consecutive_failures=0
                        )
                        logger.info(f"Discovered new service: {address}")

                to_remove = [
                    addr for addr, info in self.services.items()
                    if not info.seen_this_round
                ]
                for addr in to_remove:
                    del self.services[addr]
                    logger.info(f"Removed service (not in DNS): {addr}")

            logger.debug(
                f"DNS discovery for {self.service_name}: "
                f"{len(discovered_ips)} services found"
            )

        except Exception as e:
            logger.warning(f"DNS discovery failed for {self.service_name}: {e}")

    async def mark_failure(self, address: str):
        """
        Mark a service as failed.

        Increments failure count and removes after threshold.

        Args:
            address: Service address that failed
        """
        async with self.lock:
            if address in self.services:
                self.services[address].consecutive_failures += 1

                if self.services[address].consecutive_failures >= self.failure_threshold:
                    del self.services[address]
                    logger.warning(
                        f"Removed service {address} after "
                        f"{self.failure_threshold} consecutive failures"
                    )

    async def mark_success(self, address: str):
        """
        Mark a service as successfully contacted.

        Resets failure count to zero.

        Args:
            address: Service address that succeeded
        """
        async with self.lock:
            if address in self.services:
                self.services[address].consecutive_failures = 0

    async def get_all_addresses(self) -> List[str]:
        """
        Get list of all known service addresses.

        Returns:
            List of addresses in format 'ip:port'
        """
        async with self.lock:
            return list(self.services.keys())
