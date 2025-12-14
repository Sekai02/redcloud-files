"""Entry point for the Controller service."""

import uvicorn
import asyncio
import time
import uuid
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from common.logging_config import setup_logging, get_logger
from controller.config import CONTROLLER_HOST, CONTROLLER_PORT
from controller.database import init_database
from controller.routes.auth_routes import router as auth_router
from controller.routes.file_routes import router as file_router
from controller.routes.internal_routes import router as internal_router
from controller.routes.internal_routes import (
    set_gossip_service,
    set_peer_registry,
    set_chunkserver_registry
)
from controller.cleanup_task import OrphanedChunkCleaner
from controller.exceptions import (
    DFSException,
    UserAlreadyExistsError,
    InvalidCredentialsError,
    InvalidAPIKeyError,
    FileNotFoundError,
    UnauthorizedAccessError,
    ChunkserverUnavailableError,
    InvalidTagQueryError,
    StorageFullError,
    ChecksumMismatchError
)

logger = setup_logging('controller')

app = FastAPI(
    title="RedCloud Files Controller",
    description="Centralized tag-based file system controller server",
    version="1.0.0"
)

cleanup_task = OrphanedChunkCleaner()

peer_registry = None
gossip_service = None
chunkserver_registry = None
health_monitor = None
repair_service = None


async def peer_persistence_loop(peer_registry):
    """
    Periodically persist peer state to database.
    """
    while True:
        try:
            await asyncio.sleep(30)
            await peer_registry.persist_to_database()
        except Exception as e:
            logger.error(f"Peer persistence error: {e}", exc_info=True)


async def peer_cleanup_loop(peer_registry):
    """
    Periodically cleanup stale peers.
    """
    while True:
        try:
            await asyncio.sleep(60)
            await peer_registry.cleanup_stale_peers(120)
        except Exception as e:
            logger.error(f"Peer cleanup error: {e}", exc_info=True)


async def chunkserver_cleanup_loop(chunkserver_registry):
    """
    Periodically cleanup stale chunkservers.
    """
    while True:
        try:
            await asyncio.sleep(60)
            await chunkserver_registry.cleanup_stale_servers(60)
        except Exception as e:
            logger.error(f"Chunkserver cleanup error: {e}", exc_info=True)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware to log all HTTP requests and responses.
    """
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    start_time = time.time()
    
    user_id = getattr(request.state, 'user_id', None)
    
    logger.info(
        f"Request started: {request.method} {request.url.path} [request_id={request_id}] [user_id={user_id or 'anonymous'}]"
    )
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    
    logger.info(
        f"Request completed: {request.method} {request.url.path} "
        f"status={response.status_code} duration={duration:.3f}s [request_id={request_id}]"
    )
    
    response.headers["X-Request-ID"] = request_id
    
    return response


@app.on_event("startup")
async def startup_event():
    """
    Initialize database and start background tasks on application startup.
    """
    global peer_registry, gossip_service, chunkserver_registry, health_monitor, repair_service

    logger.info("Controller service starting up...")

    init_database()
    logger.info("Database initialized")

    try:
        from controller.distributed_config import (
            CONTROLLER_NODE_ID,
            CONTROLLER_ADVERTISE_ADDR,
            CONTROLLER_SERVICE_NAME,
            GOSSIP_INTERVAL,
            ANTI_ENTROPY_INTERVAL,
            GOSSIP_FANOUT,
            HEARTBEAT_TIMEOUT,
            REPAIR_INTERVAL,
            MIN_CHUNK_REPLICAS,
            PEER_DNS_REFRESH_INTERVAL,
            get_container_ip
        )
        from controller.gossip.peer_registry import PeerRegistry
        from controller.gossip.gossip_service import GossipService
        from controller.chunkserver_registry import ChunkserverRegistry
        from controller.chunkserver_health import ChunkserverHealthMonitor
        from controller.chunk_repair import ChunkRepairService
        from controller.chunk_placement import ChunkPlacementManager
        from controller.replication_manager import ReplicationManager
        from controller.service_locator import (
            set_replication_manager,
            set_placement_manager,
            set_chunkserver_registry as set_cs_registry,
            set_health_monitor
        )

        detected_ip = get_container_ip()
        logger.info(f"Detected container IP: {detected_ip}")
        logger.info(f"Starting distributed controller: node_id={CONTROLLER_NODE_ID}, addr={CONTROLLER_ADVERTISE_ADDR}")

        peer_registry = PeerRegistry(
            node_id=CONTROLLER_NODE_ID,
            advertise_addr=CONTROLLER_ADVERTISE_ADDR,
            service_name=CONTROLLER_SERVICE_NAME
        )

        gossip_service = GossipService(
            node_id=CONTROLLER_NODE_ID,
            peer_registry=peer_registry,
            gossip_interval=GOSSIP_INTERVAL,
            anti_entropy_interval=ANTI_ENTROPY_INTERVAL,
            fanout=GOSSIP_FANOUT
        )

        chunkserver_registry = ChunkserverRegistry()

        health_monitor = ChunkserverHealthMonitor(
            chunkserver_registry=chunkserver_registry,
            heartbeat_timeout=HEARTBEAT_TIMEOUT
        )

        placement_manager = ChunkPlacementManager(min_replicas=MIN_CHUNK_REPLICAS)

        replication_manager = ReplicationManager(
            placement_manager=placement_manager,
            chunkserver_registry=chunkserver_registry
        )

        repair_service = ChunkRepairService(
            placement_manager=placement_manager,
            chunkserver_registry=chunkserver_registry,
            repair_interval=REPAIR_INTERVAL
        )

        set_peer_registry(peer_registry)
        set_gossip_service(gossip_service)
        set_chunkserver_registry(chunkserver_registry)
        set_replication_manager(replication_manager)
        set_placement_manager(placement_manager)
        set_cs_registry(chunkserver_registry)
        set_health_monitor(health_monitor)

        await chunkserver_registry.load_from_database()
        await peer_registry.load_from_database()
        await peer_registry.discover_initial_peers()
        await peer_registry.register_with_peers()
        await peer_registry.start_periodic_refresh(PEER_DNS_REFRESH_INTERVAL)

        asyncio.create_task(peer_persistence_loop(peer_registry))
        asyncio.create_task(peer_cleanup_loop(peer_registry))
        asyncio.create_task(chunkserver_cleanup_loop(chunkserver_registry))

        await gossip_service.start()
        await health_monitor.start()
        await repair_service.start()

        logger.info("Distributed services started")

    except ImportError:
        logger.info("Distributed config not available - running in standalone mode")
    except Exception as e:
        logger.error(f"Failed to start distributed services: {e}", exc_info=True)
        logger.info("Continuing in standalone mode")

    await cleanup_task.start()
    logger.info("Background cleanup task started")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup resources on application shutdown.
    """
    logger.info("Controller service shutting down...")

    if peer_registry:
        await peer_registry.stop_periodic_refresh()
        logger.info("Peer refresh stopped")

    if gossip_service:
        await gossip_service.stop()
        logger.info("Gossip service stopped")

    if health_monitor:
        await health_monitor.stop()
        logger.info("Health monitor stopped")

    if repair_service:
        await repair_service.stop()
        logger.info("Repair service stopped")

    await cleanup_task.stop()
    logger.info("Cleanup task stopped")


@app.exception_handler(UserAlreadyExistsError)
async def user_already_exists_handler(request: Request, exc: UserAlreadyExistsError):
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.warning(
        f"User already exists error: {exc} [request_id={request_id}] path={request.url.path}"
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "code": "USER_ALREADY_EXISTS"}
    )


@app.exception_handler(InvalidCredentialsError)
async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError):
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.warning(
        f"Invalid credentials error: {exc} [request_id={request_id}] path={request.url.path}"
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(exc), "code": "INVALID_CREDENTIALS"}
    )


@app.exception_handler(InvalidAPIKeyError)
async def invalid_api_key_handler(request: Request, exc: InvalidAPIKeyError):
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.warning(
        f"Invalid API key error: {exc} [request_id={request_id}] path={request.url.path}"
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(exc), "code": "INVALID_API_KEY"}
    )


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request: Request, exc: FileNotFoundError):
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.warning(
        f"File not found error: {exc} [request_id={request_id}] path={request.url.path}"
    )
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "code": "FILE_NOT_FOUND"}
    )


@app.exception_handler(UnauthorizedAccessError)
async def unauthorized_access_handler(request: Request, exc: UnauthorizedAccessError):
    request_id = getattr(request.state, 'request_id', 'unknown')
    user_id = getattr(request.state, 'user_id', 'unknown')
    logger.warning(
        f"Unauthorized access error: {exc} [request_id={request_id}] [user_id={user_id}] path={request.url.path}"
    )
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc), "code": "UNAUTHORIZED_ACCESS"}
    )


@app.exception_handler(ChunkserverUnavailableError)
async def chunkserver_unavailable_handler(request: Request, exc: ChunkserverUnavailableError):
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(
        f"Chunkserver unavailable error: {exc} [request_id={request_id}] path={request.url.path}",
        exc_info=True
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc), "code": "CHUNKSERVER_UNAVAILABLE"}
    )


@app.exception_handler(InvalidTagQueryError)
async def invalid_tag_query_handler(request: Request, exc: InvalidTagQueryError):
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.warning(
        f"Invalid tag query error: {exc} [request_id={request_id}] path={request.url.path}"
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "code": "INVALID_TAG_QUERY"}
    )


@app.exception_handler(StorageFullError)
async def storage_full_handler(request: Request, exc: StorageFullError):
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(
        f"Storage full error: {exc} [request_id={request_id}] path={request.url.path}",
        exc_info=True
    )
    return JSONResponse(
        status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
        content={"detail": str(exc), "code": "STORAGE_FULL"}
    )


@app.exception_handler(ChecksumMismatchError)
async def checksum_mismatch_handler(request: Request, exc: ChecksumMismatchError):
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(
        f"Checksum mismatch error: {exc} [request_id={request_id}] path={request.url.path}",
        exc_info=True
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc), "code": "CHECKSUM_MISMATCH"}
    )


@app.exception_handler(DFSException)
async def dfs_exception_handler(request: Request, exc: DFSException):
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(
        f"DFS exception: {exc} [request_id={request_id}] path={request.url.path}",
        exc_info=True
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc), "code": "INTERNAL_ERROR"}
    )


@app.exception_handler(NotImplementedError)
async def not_implemented_handler(request: Request, exc: NotImplementedError):
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(
        f"Not implemented error: {exc} [request_id={request_id}] path={request.url.path}",
        exc_info=True
    )
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": str(exc), "code": "NOT_IMPLEMENTED"}
    )


app.include_router(auth_router)
app.include_router(file_router)
app.include_router(internal_router)


@app.get("/")
async def root():
    """
    Root endpoint for health check.
    """
    return {"message": "RedCloud Files Controller API", "status": "running"}


@app.get("/health")
async def health_check():
    """
    Health check endpoint for Docker healthcheck.
    Returns 200 if service is alive.
    """
    return {"status": "healthy", "service": "controller"}


@app.get("/ready")
async def ready_check():
    """
    Readiness check endpoint.
    Verifies database and chunkserver connectivity.
    """
    from controller.database import get_db_connection
    from controller.chunkserver_client import ChunkserverClient
    
    try:
        conn = get_db_connection()
        conn.close()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    try:
        client = ChunkserverClient()
        await client.ping()
        await client.close()
        chunkserver_status = "ok"
    except Exception as e:
        chunkserver_status = f"error: {str(e)}"
    
    ready = db_status == "ok" and chunkserver_status == "ok"
    status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        status_code=status_code,
        content={
            "ready": ready,
            "database": db_status,
            "chunkserver": chunkserver_status
        }
    )


def main() -> None:
    """
    Start the FastAPI server with uvicorn.
    """
    uvicorn.run(
        "controller.main:app",
        host=CONTROLLER_HOST,
        port=CONTROLLER_PORT,
        reload=True
    )


if __name__ == "__main__":
    main()
