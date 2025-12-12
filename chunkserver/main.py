"""Entry point for the Chunkserver service.
Loads chunk index, starts RPC server to handle controller requests.
"""

import asyncio
import signal
import sys
from pathlib import Path

from common.logging_config import setup_logging
from common.constants import CHUNKSERVER_PORT
from chunkserver.chunk_index import ChunkIndex
from chunkserver.grpc_server import create_server

logger = setup_logging('chunkserver')


async def serve(chunk_index: ChunkIndex) -> None:
    """
    Start and run gRPC server.

    Args:
        chunk_index: Initialized ChunkIndex instance
    """
    server = create_server(chunk_index)
    listen_addr = f'[::]:{CHUNKSERVER_PORT}'
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting chunkserver on {listen_addr}")
    await server.start()

    async def shutdown(sig=None):
        if sig:
            logger.info(f"Received signal {sig}, shutting down...")
        else:
            logger.info("Shutting down...")
        await server.stop(5)
        chunk_index.save_to_disk()
        logger.info("Chunkserver stopped")

    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        await shutdown()


def main() -> None:
    """Bootstrap chunkserver service."""
    logger.info("Initializing chunkserver...")

    chunk_index = ChunkIndex()

    try:
        loaded = chunk_index.load_from_disk()
        if loaded:
            logger.info(f"Loaded {chunk_index.count()} chunks from index")
        else:
            logger.warning("No index file found, starting with empty index")
    except Exception as e:
        logger.error(f"Failed to load index from disk: {e}")
        logger.info("Attempting to rebuild index from chunks directory...")
        try:
            count = chunk_index.rebuild_from_directory(verify_checksums=False)
            logger.info(f"Rebuilt index with {count} chunks")
            chunk_index.save_to_disk()
        except Exception as rebuild_error:
            logger.error(f"Failed to rebuild index: {rebuild_error}")
            logger.warning("Starting with empty index")

    try:
        asyncio.run(serve(chunk_index))
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, saving index...")
        chunk_index.save_to_disk()
        logger.info("Chunkserver shutdown complete")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        chunk_index.save_to_disk()
        raise


if __name__ == "__main__":
    main()
