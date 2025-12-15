"""Peer registry for tracking controller nodes."""

import asyncio
import aiohttp
import socket
import time
from typing import List, Dict, Any, Optional
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
        self.my_ip = advertise_addr.split(":")[0]
        self.running = False

    async def load_from_database(self):
        """
        Load persisted peers from database on startup.
        Restores peer topology after controller restart.
        """
        from controller.database import get_db_connection
        
        async with self.lock:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT node_id, address, last_seen
                    FROM controller_nodes
                """)
                rows = cursor.fetchall()
                
                for row in rows:
                    node_id = row['node_id']
                    if node_id != self.node_id:
                        self.peers[node_id] = {
                            "address": row['address'],
                            "last_seen": row['last_seen']
                        }
                
                count = len(self.peers)
                logger.info(f"Loaded {count} peers from database")
                return count

    async def discover_initial_peers(self, max_retries: int = 3):
        """
        Bootstrap by resolving service DNS to all controller IPs.
        Queries each discovered controller for its real node_id.
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"DNS discovery attempt {attempt + 1}/{max_retries} for service: {self.service_name}")
                
                loop = asyncio.get_event_loop()
                addr_info = await loop.run_in_executor(
                    None,
                    socket.getaddrinfo,
                    self.service_name,
                    8000,
                    socket.AF_INET,
                    socket.SOCK_STREAM
                )

                all_ips = [sockaddr[0] for _, _, _, _, sockaddr in addr_info]
                logger.debug(f"DNS returned {len(addr_info)} records, IPs: {all_ips}")
                
                discovered_ips = set()
                for family, socktype, proto, canonname, sockaddr in addr_info:
                    ip, port = sockaddr
                    if ip != self.my_ip:
                        discovered_ips.add(ip)

                logger.info(f"DNS returned {len(all_ips)} IPs, {len(discovered_ips)} after excluding self ({self.my_ip})")

                if not discovered_ips:
                    logger.info("No peers discovered via DNS - might be first controller")
                    return

                tasks = [
                    self._query_peer_identity(ip)
                    for ip in discovered_ips
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                async with self.lock:
                    for result in results:
                        if isinstance(result, dict) and result.get('node_id') and result.get('address'):
                            node_id = result['node_id']
                            address = result['address']

                            if node_id != self.node_id:
                                self.peers[node_id] = {"address": address, "last_seen": time.time()}

                successful = sum(1 for r in results if isinstance(r, dict) and r.get('node_id'))
                logger.info(f"Discovered {successful}/{len(discovered_ips)} peers via DNS")
                return

            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"DNS discovery failed after {max_retries} attempts: {e}")
                else:
                    wait_time = 2 ** attempt
                    logger.warning(f"DNS discovery attempt {attempt + 1} failed: {e}, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)

    async def _query_peer_identity(self, ip: str) -> Dict[str, str]:
        """
        Query a controller's /internal/peers endpoint to get its real node_id.

        Args:
            ip: Controller IP address

        Returns:
            Dict with node_id and address

        Raises:
            Exception: If query fails or returns invalid data
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{ip}:8000/internal/peers",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self_info = data.get("self")
                        if self_info and self_info.get("node_id"):
                            logger.debug(f"Retrieved identity from {ip}: {self_info['node_id']}")
                            return {
                                "node_id": self_info["node_id"],
                                "address": self_info["address"]
                            }
                    raise Exception(f"Invalid response from {ip}: status={resp.status}")
        except Exception as e:
            logger.debug(f"Failed to query peer identity from {ip}: {e}")
            raise

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

    async def start_periodic_refresh(self, interval: int = 30):
        """
        Start periodic DNS refresh to discover new peers.

        Args:
            interval: Seconds between DNS refreshes
        """
        self.running = True
        asyncio.create_task(self._aggressive_initial_refresh())
        asyncio.create_task(self._refresh_loop(interval))
        logger.info(f"Peer DNS refresh started (interval={interval}s)")

    async def _aggressive_initial_refresh(self):
        """Perform rapid DNS refreshes during startup to catch late-starting peers"""
        for i in range(3):
            await asyncio.sleep(5)
            if not self.running:
                break
            logger.debug(f"Aggressive DNS refresh {i + 1}/3")
            await self.discover_initial_peers()

    async def stop_periodic_refresh(self):
        """Stop periodic DNS refresh"""
        self.running = False
        logger.info("Peer DNS refresh stopped")

    async def _refresh_loop(self, interval: int):
        """Periodically refresh peer list via DNS"""
        while self.running:
            try:
                await asyncio.sleep(interval)
                await self.discover_initial_peers()
            except Exception as e:
                logger.error(f"Peer refresh error: {e}", exc_info=True)
                await asyncio.sleep(5)

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

    async def persist_to_database(self):
        """
        Write current in-memory peer state to database.
        Provides recovery snapshot for restart scenarios.
        """
        from controller.database import get_db_connection
        
        async with self.lock:
            peers_snapshot = dict(self.peers)
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for node_id, info in peers_snapshot.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO controller_nodes
                    (node_id, address, last_seen, vector_clock)
                    VALUES (?, ?, ?, ?)
                """, (node_id, info['address'], info['last_seen'], '{}'))
            conn.commit()
            logger.debug(f"Persisted {len(peers_snapshot)} peers to database")

    async def cleanup_stale_peers(self, timeout_seconds: int = 120):
        """
        Remove peers that haven't been seen within timeout period.
        Prevents unbounded memory growth from departed peers.
        """
        async with self.lock:
            cutoff_time = time.time() - timeout_seconds
            stale_peers = [
                node_id for node_id, info in self.peers.items()
                if info['last_seen'] < cutoff_time
            ]
            
            for node_id in stale_peers:
                del self.peers[node_id]
            
            if stale_peers:
                logger.info(f"Cleaned up {len(stale_peers)} stale peers: {stale_peers}")
            
            return len(stale_peers)

    def get_random_peers(self, count: int) -> List[Dict[str, str]]:
        """Get random subset of peers for gossip"""
        import random
        peers_list = self.get_all_peers()
        if len(peers_list) <= count:
            return peers_list
        return random.sample(peers_list, count)
