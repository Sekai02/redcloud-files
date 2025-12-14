"""Heartbeat service for chunkserver registration and health reporting."""

import asyncio
import aiohttp
import os
from typing import Dict, Any
from pathlib import Path
from common.logging_config import get_logger

logger = get_logger(__name__)


class HeartbeatService:
    """
    Sends periodic heartbeats to all controllers in parallel.

    Uses DNS-based discovery to find all controller instances and
    broadcasts heartbeats to ensure consistent health state across
    all controllers.
    """

    def __init__(
        self,
        node_id: str,
        advertise_addr: str,
        controller_service: str,
        interval: int,
        controller_discovery: Any
    ):
        self.node_id = node_id
        self.advertise_addr = advertise_addr
        self.controller_service = controller_service
        self.interval = interval
        self.controller_discovery = controller_discovery
        self.running = False
        self.chunk_storage_path = Path(os.getenv("CHUNK_STORAGE_PATH", "/app/data/chunks"))

    async def start(self):
        """Start heartbeat background task"""
        self.running = True

        await self.controller_discovery.start()
        logger.info("Controller discovery service started")

        asyncio.create_task(self._heartbeat_loop())
        logger.info(f"Heartbeat service started - node_id={self.node_id}, addr={self.advertise_addr}")

    async def stop(self):
        """Stop heartbeat background task"""
        self.running = False

        await self.controller_discovery.stop()

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
        Send heartbeat to all discovered controllers in parallel.
        """
        await self._broadcast_to_all_controllers()

    async def _broadcast_to_all_controllers(self):
        """Broadcast heartbeat to all discovered controllers in parallel."""
        controllers = await self.controller_discovery.get_all_addresses()

        if not controllers:
            logger.warning("No controllers discovered, skipping heartbeat")
            return

        capacity_bytes, used_bytes = self._get_storage_stats()
        payload = {
            "node_id": self.node_id,
            "address": self.advertise_addr,
            "capacity_bytes": capacity_bytes,
            "used_bytes": used_bytes
        }

        tasks = [
            self._send_to_controller(f"http://{addr}", payload)
            for addr in controllers
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        logger.debug(
            f"Heartbeat broadcast: {success_count}/{len(controllers)} succeeded"
        )

    async def _send_to_controller(
        self,
        base_url: str,
        payload: Dict[str, Any]
    ) -> bool:
        """
        Send heartbeat to a single controller.

        Args:
            base_url: Controller base URL (e.g., 'http://172.18.0.3:8000')
            payload: Heartbeat payload

        Returns:
            True on success, False on failure
        """
        address = base_url.split("://")[1]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/internal/chunkserver/heartbeat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    if resp.status == 200:
                        await self.controller_discovery.mark_success(address)
                        logger.debug(f"Heartbeat to {address} succeeded")
                        return True
                    else:
                        logger.warning(
                            f"Heartbeat to {address} returned {resp.status}"
                        )
                        await self.controller_discovery.mark_failure(address)
                        return False

        except asyncio.TimeoutError:
            logger.warning(f"Heartbeat to {address} timed out")
            await self.controller_discovery.mark_failure(address)
            return False
        except Exception as e:
            logger.warning(f"Heartbeat to {address} failed: {e}")
            await self.controller_discovery.mark_failure(address)
            return False

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
