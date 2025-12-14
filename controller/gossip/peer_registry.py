"""Peer registry for tracking controller nodes."""

import asyncio
import aiohttp
import time
from typing import List, Dict, Any
from common.logging_config import get_logger

logger = get_logger(__name__)


class PeerRegistry:
    """Maintains list of known controller peers via gossip"""

    def __init__(self, node_id: str, advertise_addr: str, service_name: str):
        self.node_id = node_id
        self.advertise_addr = advertise_addr
        self.service_name = service_name
        self.peers: Dict[str, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    async def discover_initial_peers(self):
        """
        Bootstrap by querying 'controller' DNS multiple times.
        DNS round-robin may return different IPs each time.
        """
        discovered = set()

        for attempt in range(10):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"http://{self.service_name}:8000/internal/peers",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for peer in data.get("peers", []):
                                peer_node_id = peer["node_id"]
                                peer_address = peer["address"]
                                if peer_node_id != self.node_id:
                                    discovered.add((peer_node_id, peer_address))
                            
                            self_info = data.get("self")
                            if self_info and self_info["node_id"] != self.node_id:
                                discovered.add((self_info["node_id"], self_info["address"]))
            except Exception as e:
                logger.debug(f"Discovery attempt {attempt} failed: {e}")
                pass

            await asyncio.sleep(0.5)

        async with self.lock:
            for node_id, address in discovered:
                self.peers[node_id] = {"address": address, "last_seen": time.time()}

        if discovered:
            logger.info(f"Discovered {len(discovered)} initial peers: {[nid for nid, _ in discovered]}")
        else:
            logger.info("No initial peers discovered - might be first controller")

    async def register_with_peers(self):
        """Register ourselves with discovered peers"""
        async with self.lock:
            peer_list = list(self.peers.values())

        for peer in peer_list:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"http://{peer['address']}/internal/peers/register",
                        json={
                            "node_id": self.node_id,
                            "address": self.advertise_addr
                        },
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        if resp.status == 200:
                            logger.info(f"Registered with peer {peer['address']}")
            except Exception as e:
                logger.warning(f"Failed to register with peer {peer['address']}: {e}")

    def get_all_peers(self) -> List[Dict[str, str]]:
        """Get list of all known peers"""
        return [{"node_id": nid, "address": info["address"]} for nid, info in self.peers.items()]

    async def add_peer(self, node_id: str, address: str):
        """Add or update peer (called from gossip or registration)"""
        async with self.lock:
            self.peers[node_id] = {"address": address, "last_seen": time.time()}
            logger.debug(f"Added/updated peer: {node_id} @ {address}")

    async def remove_peer(self, node_id: str):
        """Remove a peer"""
        async with self.lock:
            if node_id in self.peers:
                del self.peers[node_id]
                logger.info(f"Removed peer: {node_id}")

    def get_random_peers(self, count: int) -> List[Dict[str, str]]:
        """Get random subset of peers for gossip"""
        import random
        peers_list = self.get_all_peers()
        if len(peers_list) <= count:
            return peers_list
        return random.sample(peers_list, count)
