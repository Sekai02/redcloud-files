"""Replication manager for parallel chunk replication across chunkservers."""

import asyncio
from typing import List, Dict, Any, Optional
from common.logging_config import get_logger
from controller.chunk_placement import ChunkPlacementManager
from controller.chunkserver_registry import ChunkserverRegistry
from controller.chunkserver_client import ChunkserverClient
from controller.database import get_db_connection

logger = get_logger(__name__)


class ReplicationManager:
    """
    Manages parallel replication for chunks across multiple chunkservers.
    Uses DYNAMIC replication - writes to all available servers.
    """

    def __init__(
        self,
        placement_manager: ChunkPlacementManager,
        chunkserver_registry: ChunkserverRegistry
    ):
        self.placement = placement_manager
        self.chunkserver_registry = chunkserver_registry
        self.chunkserver_clients: Dict[str, ChunkserverClient] = {}
        self.min_write_success = 1

    def get_client(self, chunkserver_id: str, address: str) -> ChunkserverClient:
        """Get or create gRPC client for a chunkserver"""
        if chunkserver_id not in self.chunkserver_clients:
            self.chunkserver_clients[chunkserver_id] = ChunkserverClient(address)
        return self.chunkserver_clients[chunkserver_id]

    async def write_chunk_replicated(
        self,
        chunk_id: str,
        file_id: str,
        chunk_index: int,
        data: bytes,
        checksum: str
    ) -> bool:
        """
        Write chunk to N chunkservers in parallel.

        Returns True if at least one write succeeds.
        Records all successful locations in chunk_locations table.
        """
        available_servers = await self.chunkserver_registry.get_healthy_servers()

        target_servers = await self.placement.select_chunkservers_for_write(
            chunk_id=chunk_id,
            available_servers=available_servers
        )

        if not target_servers:
            raise Exception("No chunkservers available for write")

        logger.info(f"Writing chunk {chunk_id} to {len(target_servers)} servers: {target_servers}")

        write_tasks = []
        for server_id in target_servers:
            server_info = next(s for s in available_servers if s['node_id'] == server_id)
            client = self.get_client(server_id, server_info['address'])

            write_tasks.append(
                self._write_to_server(
                    client=client,
                    server_id=server_id,
                    chunk_id=chunk_id,
                    file_id=file_id,
                    chunk_index=chunk_index,
                    data=data,
                    checksum=checksum
                )
            )

        results = await asyncio.gather(*write_tasks, return_exceptions=True)

        successful_servers = []
        with get_db_connection() as conn:
            for server_id, result in zip(target_servers, results):
                if result is True:
                    successful_servers.append(server_id)
                    await self.placement.record_chunk_location(chunk_id, server_id, conn)
                    logger.debug(f"Successfully wrote chunk {chunk_id} to {server_id}")
                else:
                    logger.warning(f"Failed to write chunk {chunk_id} to {server_id}: {result}")

        if not successful_servers:
            raise Exception(f"Failed to write chunk {chunk_id} to any chunkserver")

        logger.info(f"Chunk {chunk_id} written to {len(successful_servers)}/{len(target_servers)} servers")
        return True

    async def _write_to_server(
        self,
        client: ChunkserverClient,
        server_id: str,
        chunk_id: str,
        file_id: str,
        chunk_index: int,
        data: bytes,
        checksum: str
    ) -> bool:
        """Write chunk to a single chunkserver"""
        try:
            await client.write_chunk(
                chunk_id=chunk_id,
                file_id=file_id,
                chunk_index=chunk_index,
                data=data,
                checksum=checksum
            )
            return True
        except Exception as e:
            logger.error(f"Write to {server_id} failed: {e}")
            return False

    async def read_chunk_with_fallback(
        self,
        chunk_id: str,
        health_monitor=None
    ) -> bytes:
        """
        Read chunk from any available replica with fallback.

        Args:
            chunk_id: UUID of chunk to read
            health_monitor: Optional health monitor to filter healthy servers

        Returns:
            Chunk data bytes
        """
        chunk_locations = await self.placement.get_chunk_locations(chunk_id)

        if health_monitor:
            healthy = [loc for loc in chunk_locations if health_monitor.is_healthy(loc)]
            failed = [loc for loc in chunk_locations if not health_monitor.is_healthy(loc)]
            ordered_locations = healthy + failed
        else:
            ordered_locations = chunk_locations

        if not ordered_locations:
            raise FileNotFoundError(f"No locations found for chunk {chunk_id}")

        last_error = None
        for server_id in ordered_locations:
            try:
                server_info = await self.chunkserver_registry.get_server_info(server_id)
                if not server_info:
                    continue

                client = self.get_client(server_id, server_info['address'])
                
                chunk_data = bytearray()
                async for piece in client.read_chunk(chunk_id):
                    chunk_data.extend(piece)
                
                logger.debug(f"Successfully read chunk {chunk_id} from {server_id}")
                return bytes(chunk_data)

            except Exception as e:
                logger.warning(f"Failed to read chunk {chunk_id} from {server_id}: {e}")
                last_error = e
                continue

        raise Exception(f"Failed to read chunk {chunk_id} from any replica: {last_error}")

    async def delete_chunk_from_all_replicas(self, chunk_id: str):
        """
        Delete chunk from all replicas in parallel.

        Returns number of successful deletions.
        """
        chunk_locations = await self.placement.get_chunk_locations(chunk_id)

        if not chunk_locations:
            logger.warning(f"No locations found for chunk {chunk_id} to delete")
            return 0

        delete_tasks = []
        for server_id in chunk_locations:
            server_info = await self.chunkserver_registry.get_server_info(server_id)
            if server_info:
                client = self.get_client(server_id, server_info['address'])
                delete_tasks.append(self._delete_from_server(client, server_id, chunk_id))

        results = await asyncio.gather(*delete_tasks, return_exceptions=True)

        successful = sum(1 for r in results if r is True)
        logger.info(f"Deleted chunk {chunk_id} from {successful}/{len(chunk_locations)} servers")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chunk_locations WHERE chunk_id = ?", (chunk_id,))
            conn.commit()

        return successful

    async def _delete_from_server(
        self,
        client: ChunkserverClient,
        server_id: str,
        chunk_id: str
    ) -> bool:
        """Delete chunk from a single chunkserver"""
        try:
            await client.delete_chunk(chunk_id)
            return True
        except Exception as e:
            logger.warning(f"Delete from {server_id} failed: {e}")
            return False
