"""Heartbeat service for chunkserver registration and health reporting."""

import asyncio
import aiohttp
import os
from pathlib import Path
from common.logging_config import get_logger

logger = get_logger(__name__)


class HeartbeatService:
    """
    Sends periodic heartbeats to controller to register and report health.
    """

    def __init__(
        self,
        node_id: str,
        advertise_addr: str,
        controller_service: str,
        interval: int = 10
    ):
        self.node_id = node_id
        self.advertise_addr = advertise_addr
        self.controller_service = controller_service
        self.interval = interval
        self.running = False
        self.chunk_storage_path = Path(os.getenv("CHUNK_STORAGE_PATH", "/app/data/chunks"))

    async def start(self):
        """Start heartbeat background task"""
        self.running = True
        asyncio.create_task(self._heartbeat_loop())
        logger.info(f"Heartbeat service started - node_id={self.node_id}, addr={self.advertise_addr}")

    async def stop(self):
        """Stop heartbeat background task"""
        self.running = False
        logger.info("Heartbeat service stopped")

    async def _heartbeat_loop(self):
        """Send periodic heartbeat to controller"""
        while self.running:
            try:
                await self._send_heartbeat()
                await asyncio.sleep(self.interval)
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
                await asyncio.sleep(5)

    async def _send_heartbeat(self):
        """
        Register with controller and report status.

        NOTE: Sends to 'controller' DNS (reaches one random controller).
        That controller will gossip the registration to all other controllers.
        """
        capacity_bytes, used_bytes = self._get_storage_stats()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"http://{self.controller_service}:8000/internal/chunkserver/heartbeat",
                    json={
                        "node_id": self.node_id,
                        "address": self.advertise_addr,
                        "capacity_bytes": capacity_bytes,
                        "used_bytes": used_bytes
                    },
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        logger.debug(f"Heartbeat sent successfully")
                    else:
                        logger.warning(f"Heartbeat returned status {resp.status}")
        except Exception as e:
            logger.warning(f"Failed to send heartbeat: {e}")

    def _get_storage_stats(self):
        """Get storage capacity and usage statistics"""
        try:
            self.chunk_storage_path.mkdir(parents=True, exist_ok=True)

            if os.name == 'nt':
                import ctypes
                free_bytes = ctypes.c_ulonglong(0)
                total_bytes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    str(self.chunk_storage_path),
                    None,
                    ctypes.byref(total_bytes),
                    ctypes.byref(free_bytes)
                )
                capacity = total_bytes.value
                used = capacity - free_bytes.value
            else:
                import shutil
                stat = shutil.disk_usage(str(self.chunk_storage_path))
                capacity = stat.total
                used = stat.used

            return capacity, used
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return 0, 0
