"""Chunk repair and anti-entropy service."""

import asyncio
import grpc
from typing import List, Dict, Any
from common.logging_config import get_logger
from controller.chunk_placement import ChunkPlacementManager
from controller.chunkserver_registry import ChunkserverRegistry
from controller.chunkserver_client import ChunkserverClient
from controller.database import get_db_connection
from common.protocol import ReplicateChunkRequest, ReplicateChunkResponse

logger = get_logger(__name__)


class ChunkRepairService:
    """
    Background service to ensure full replication of all chunks.

    Responsibilities:
    - Detect under-replicated chunks
    - Replicate chunks to new servers
    - Repair after partition healing
    - Ensure eventual full replication
    """

    def __init__(
        self,
        placement_manager: ChunkPlacementManager,
        chunkserver_registry: ChunkserverRegistry,
        repair_interval: int = 60
    ):
        self.placement = placement_manager
        self.chunkserver_registry = chunkserver_registry
        self.repair_interval = repair_interval
        self.running = False

    async def start(self):
        """Start background repair task"""
        self.running = True
        asyncio.create_task(self._repair_loop())
        logger.info(f"Chunk repair service started (interval={self.repair_interval}s)")

    async def stop(self):
        """Stop background repair task"""
        self.running = False
        logger.info("Chunk repair service stopped")

    async def _repair_loop(self):
        """Periodically check and repair chunk replication"""
        while self.running:
            try:
                await asyncio.sleep(self.repair_interval)
                await self._check_replication_health()
            except Exception as e:
                logger.error(f"Repair loop error: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def _check_replication_health(self):
        """
        Find under-replicated chunks and repair.

        Goal: Ensure ALL chunks exist on ALL chunkservers eventually.
        This runs continuously in background and automatically handles:
        - New chunkserver joins (replicates all chunks to it)
        - Partition healing (fills in missing chunks)
        - Failed replications (retries until successful)
        """
        all_chunk_ids = await self.placement.get_all_chunk_ids()
        all_servers = await self.chunkserver_registry.get_healthy_servers()

        if not all_servers:
            logger.warning("No healthy chunkservers available for repair")
            return

        logger.info(f"Checking replication health for {len(all_chunk_ids)} chunks across {len(all_servers)} servers")

        repairs_needed = 0
        repairs_successful = 0

        for chunk_id in all_chunk_ids:
            current_locations = await self.placement.get_chunk_locations(chunk_id)
            current_server_ids = set(current_locations)
            target_server_ids = {s['node_id'] for s in all_servers}

            missing_servers = target_server_ids - current_server_ids

            if missing_servers:
                repairs_needed += len(missing_servers)
                logger.debug(f"Chunk {chunk_id} needs replication to {len(missing_servers)} servers")

                if current_server_ids:
                    source_server_id = list(current_server_ids)[0]
                    source_info = await self.chunkserver_registry.get_server_info(source_server_id)

                    if source_info:
                        for target_server_id in missing_servers:
                            success = await self._replicate_chunk(
                                chunk_id=chunk_id,
                                source_address=source_info['address'],
                                target_server_id=target_server_id
                            )
                            if success:
                                repairs_successful += 1
                                await self.placement.record_chunk_location(chunk_id, target_server_id)

        if repairs_needed > 0:
            logger.info(f"Repair cycle complete: {repairs_successful}/{repairs_needed} replications successful")

    async def _replicate_chunk(
        self,
        chunk_id: str,
        source_address: str,
        target_server_id: str
    ) -> bool:
        """
        Replicate a chunk from source to target server.

        Args:
            chunk_id: UUID of chunk to replicate
            source_address: Address of server with the chunk
            target_server_id: ID of server to replicate to

        Returns:
            True if successful, False otherwise
        """
        try:
            target_info = await self.chunkserver_registry.get_server_info(target_server_id)
            if not target_info:
                logger.error(f"Target server {target_server_id} not found")
                return False

            target_address = target_info['address']

            async with grpc.aio.insecure_channel(target_address) as channel:
                request = ReplicateChunkRequest(
                    chunk_id=chunk_id,
                    source_chunkserver_address=source_address
                )

                response_bytes = await channel.unary_unary(
                    f'/chunkserver.ChunkserverService/ReplicateChunk',
                    request_serializer=lambda x: x,
                    response_deserializer=lambda x: x
                )(request.to_json())

                response = ReplicateChunkResponse.from_json(response_bytes)

                if response.success:
                    logger.info(f"Successfully replicated chunk {chunk_id} to {target_server_id}")
                    return True
                else:
                    logger.warning(f"Failed to replicate chunk {chunk_id} to {target_server_id}: {response.error}")
                    return False

        except Exception as e:
            logger.error(f"Error replicating chunk {chunk_id} to {target_server_id}: {e}")
            return False
