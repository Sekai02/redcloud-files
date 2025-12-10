"""Pydantic schemas for API requests and responses."""

from controller.schemas.auth import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse
)
from controller.schemas.files import (
    AddFileResponse,
    FileMetadataResponse,
    ListFilesResponse,
    DeleteFilesResponse,
    AddTagsRequest,
    AddTagsResponse,
    DeleteTagsRequest,
    DeleteTagsResponse
)
from controller.schemas.common import ErrorResponse

__all__ = [
    "RegisterRequest",
    "RegisterResponse",
    "LoginRequest",
    "LoginResponse",
    "AddFileResponse",
    "FileMetadataResponse",
    "ListFilesResponse",
    "DeleteFilesResponse",
    "AddTagsRequest",
    "AddTagsResponse",
    "DeleteTagsRequest",
    "DeleteTagsResponse",
    "ErrorResponse"
]
