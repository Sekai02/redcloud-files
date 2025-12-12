"""Entry point for the Controller service."""

import uvicorn
import asyncio
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from controller.config import CONTROLLER_HOST, CONTROLLER_PORT
from controller.database import init_database
from controller.routes.auth_routes import router as auth_router
from controller.routes.file_routes import router as file_router
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


app = FastAPI(
    title="RedCloud Files Controller",
    description="Centralized tag-based file system controller server",
    version="1.0.0"
)

cleanup_task = OrphanedChunkCleaner()


@app.on_event("startup")
async def startup_event():
    """
    Initialize database and start background tasks on application startup.
    """
    init_database()
    await cleanup_task.start()


@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup resources on application shutdown.
    """
    await cleanup_task.stop()


@app.exception_handler(UserAlreadyExistsError)
async def user_already_exists_handler(request: Request, exc: UserAlreadyExistsError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "code": "USER_ALREADY_EXISTS"}
    )


@app.exception_handler(InvalidCredentialsError)
async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(exc), "code": "INVALID_CREDENTIALS"}
    )


@app.exception_handler(InvalidAPIKeyError)
async def invalid_api_key_handler(request: Request, exc: InvalidAPIKeyError):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": str(exc), "code": "INVALID_API_KEY"}
    )


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request: Request, exc: FileNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "code": "FILE_NOT_FOUND"}
    )


@app.exception_handler(UnauthorizedAccessError)
async def unauthorized_access_handler(request: Request, exc: UnauthorizedAccessError):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc), "code": "UNAUTHORIZED_ACCESS"}
    )


@app.exception_handler(ChunkserverUnavailableError)
async def chunkserver_unavailable_handler(request: Request, exc: ChunkserverUnavailableError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc), "code": "CHUNKSERVER_UNAVAILABLE"}
    )


@app.exception_handler(InvalidTagQueryError)
async def invalid_tag_query_handler(request: Request, exc: InvalidTagQueryError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "code": "INVALID_TAG_QUERY"}
    )


@app.exception_handler(StorageFullError)
async def storage_full_handler(request: Request, exc: StorageFullError):
    return JSONResponse(
        status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
        content={"detail": str(exc), "code": "STORAGE_FULL"}
    )


@app.exception_handler(ChecksumMismatchError)
async def checksum_mismatch_handler(request: Request, exc: ChecksumMismatchError):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc), "code": "CHECKSUM_MISMATCH"}
    )


@app.exception_handler(DFSException)
async def dfs_exception_handler(request: Request, exc: DFSException):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc), "code": "INTERNAL_ERROR"}
    )


@app.exception_handler(NotImplementedError)
async def not_implemented_handler(request: Request, exc: NotImplementedError):
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"detail": str(exc), "code": "NOT_IMPLEMENTED"}
    )


app.include_router(auth_router)
app.include_router(file_router)


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
