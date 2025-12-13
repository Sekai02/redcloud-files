"""Background task for cleaning up orphaned chunks."""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict

from controller.chunkserver_client import ChunkserverClient

logger = logging.getLogger(__name__)

ORPHANED_LOG_PATH = Path("./data/orphaned_chunks.json")
CLEANUP_INTERVAL_SECONDS = 6 * 3600


class OrphanedChunkCleaner:
    """
    Background task that periodically attempts to clean up orphaned chunks.
    """
    
    def __init__(self, interval_seconds: int = CLEANUP_INTERVAL_SECONDS):
        """
        Initialize cleaner task.
        
        Args:
            interval_seconds: Time between cleanup attempts (default 6 hours)
        """
        self.interval_seconds = interval_seconds
        self.chunkserver_client = ChunkserverClient()
        self._running = False
        self._task = None
    
    async def start(self) -> None:
        """Start the background cleanup task."""
        if self._running:
            logger.warning("Cleanup task already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"Started orphaned chunk cleanup task (interval: {self.interval_seconds}s)")
    
    async def stop(self) -> None:
        """Stop the background cleanup task."""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        await self.chunkserver_client.close()
        logger.info("Stopped orphaned chunk cleanup task")
    
    async def _run(self) -> None:
        """Main loop for cleanup task."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                
                if not self._running:
                    break
                
                await self._cleanup_cycle()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}", exc_info=True)
    
    async def _cleanup_cycle(self) -> None:
        """Execute one cleanup cycle."""
        if not ORPHANED_LOG_PATH.exists():
            logger.debug("No orphaned chunks log found")
            return
        
        try:
            with open(ORPHANED_LOG_PATH, 'r') as f:
                orphaned_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read orphaned chunks log: {e}")
            return
        
        if not orphaned_data:
            logger.debug("No orphaned chunks to clean")
            return
        
        logger.info(f"Starting cleanup cycle for {len(orphaned_data)} orphaned chunks")
        
        remaining_orphans = []
        cleaned_count = 0
        
        for entry in orphaned_data:
            chunk_id = entry.get("chunk_id")
            if not chunk_id:
                continue
            
            try:
                success = await self.chunkserver_client.delete_chunk(chunk_id)
                if success:
                    logger.info(f"Cleaned orphaned chunk {chunk_id}")
                    cleaned_count += 1
                else:
                    logger.warning(f"Failed to clean orphaned chunk {chunk_id}")
                    remaining_orphans.append(entry)
            except Exception as e:
                logger.warning(f"Error cleaning orphaned chunk {chunk_id}: {e}")
                remaining_orphans.append(entry)
        
        try:
            if remaining_orphans:
                with open(ORPHANED_LOG_PATH, 'w') as f:
                    json.dump(remaining_orphans, f, indent=2)
                logger.info(f"Cleanup cycle complete: {cleaned_count} cleaned, {len(remaining_orphans)} remaining")
            else:
                ORPHANED_LOG_PATH.unlink()
                logger.info(f"Cleanup cycle complete: {cleaned_count} cleaned, all orphans removed")
        except Exception as e:
            logger.error(f"Failed to update orphaned chunks log: {e}")
