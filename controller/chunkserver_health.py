"""Chunkserver health monitoring and failure detection."""

import asyncio
import time
from typing import Set
from common.logging_config import get_logger
from controller.chunkserver_registry import ChunkserverRegistry

logger = get_logger(__name__)


class ChunkserverHealthMonitor:
    """
    Monitors chunkserver health based on heartbeat timestamps.
    Marks chunkservers as failed if they miss heartbeats.
    """

    def __init__(self, chunkserver_registry: ChunkserverRegistry, heartbeat_timeout: int = 30):
        """
        Args:
            chunkserver_registry: Registry storing chunkserver info
            heartbeat_timeout: Seconds without heartbeat before marking failed (default: 30)
        """
        self.chunkserver_registry = chunkserver_registry
        self.heartbeat_timeout = heartbeat_timeout
        self.failed_servers: Set[str] = set()
        self.running = False

    async def start(self):
        """Start background health monitoring"""
        self.running = True
        asyncio.create_task(self._health_check_loop())
        logger.info(f"Chunkserver health monitor started (timeout={self.heartbeat_timeout}s)")

    async def stop(self):
        """Stop background health monitoring"""
        self.running = False
        logger.info("Chunkserver health monitor stopped")

    async def _health_check_loop(self):
        """Periodically check for failed chunkservers"""
        while self.running:
            try:
                await self._check_chunkserver_health()
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _check_chunkserver_health(self):
        """Mark chunkservers as failed if heartbeat timeout exceeded"""
        current_time = time.time()
        cutoff_time = current_time - self.heartbeat_timeout

        all_servers = await self.chunkserver_registry.get_all()

        for server in all_servers:
            server_id = server['node_id']
            last_heartbeat = server.get('last_heartbeat', 0)

            if last_heartbeat < cutoff_time:
                if server_id not in self.failed_servers:
                    self.failed_servers.add(server_id)
                    await self.chunkserver_registry.mark_failed(server_id)
                    await self._trigger_repair_for_failed_server(server_id)
            else:
                if server_id in self.failed_servers:
                    self.failed_servers.remove(server_id)
                    await self.chunkserver_registry.mark_healthy(server_id)
                    logger.info(f"Chunkserver {server_id} recovered")

    async def _trigger_repair_for_failed_server(self, server_id: str):
        """
        Notify repair service that a server has failed.
        Repair service will replicate chunks to other servers.
        """
        logger.info(f"Triggering repair for failed chunkserver {server_id}")

    def is_healthy(self, server_id: str) -> bool:
        """Check if a chunkserver is currently healthy"""
        return server_id not in self.failed_servers
