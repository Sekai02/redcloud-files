"""
gRPC server for replication service.

Starts gRPC server on REPLICATION_PORT to handle incoming replication requests.
"""

import grpc
import logging
import asyncio
from typing import Optional

from common.constants import REPLICATION_PORT
from controller.replication.grpc_service import ReplicationServicer

logger = logging.getLogger(__name__)


class ReplicationServer:
    """
    gRPC server for replication operations.

    Starts server on REPLICATION_PORT and registers ReplicationServicer.
    """

    def __init__(self):
        """Initialize the replication server."""
        self.server: Optional[grpc.aio.Server] = None
        self.servicer = ReplicationServicer()

    async def start(self):
        """
        Start the gRPC replication server.

        Binds to [::]:REPLICATION_PORT and starts serving.
        """
        self.server = grpc.aio.server()

        self._register_handlers()

        listen_addr = f'[::]:{REPLICATION_PORT}'
        self.server.add_insecure_port(listen_addr)

        await self.server.start()

        logger.info(f"Replication gRPC server started on {listen_addr}")

    async def stop(self):
        """
        Stop the gRPC replication server.

        Gracefully shuts down the server.
        """
        if self.server:
            logger.info("Stopping replication gRPC server...")
            await self.server.stop(grace=5)
            logger.info("Replication gRPC server stopped")

    def _register_handlers(self):
        """
        Register gRPC method handlers.

        Maps RPC methods to servicer methods.
        """
        async def gossip_handler(request, context):
            return await self.servicer.Gossip(request)

        async def get_state_summary_handler(request, context):
            return await self.servicer.GetStateSummary(request)

        async def fetch_operations_handler(request, context):
            return await self.servicer.FetchOperations(request)

        async def push_operations_handler(request, context):
            return await self.servicer.PushOperations(request)

        self.server.add_generic_rpc_handlers((
            grpc.method_handlers_generic_handler(
                'replication.ReplicationService',
                {
                    'Gossip': grpc.unary_unary_rpc_method_handler(
                        gossip_handler,
                        request_deserializer=lambda x: x,
                        response_serializer=lambda x: x,
                    ),
                    'GetStateSummary': grpc.unary_unary_rpc_method_handler(
                        get_state_summary_handler,
                        request_deserializer=lambda x: x,
                        response_serializer=lambda x: x,
                    ),
                    'FetchOperations': grpc.unary_unary_rpc_method_handler(
                        fetch_operations_handler,
                        request_deserializer=lambda x: x,
                        response_serializer=lambda x: x,
                    ),
                    'PushOperations': grpc.unary_unary_rpc_method_handler(
                        push_operations_handler,
                        request_deserializer=lambda x: x,
                        response_serializer=lambda x: x,
                    ),
                }
            ),
        ))

        logger.debug("Registered replication gRPC handlers")
