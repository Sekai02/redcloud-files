"""API routes package."""

from controller.routes.auth_routes import router as auth_router
from controller.routes.file_routes import router as file_router

__all__ = ["auth_router", "file_router"]
