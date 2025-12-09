"""Pydantic models for API requests and responses."""

from typing import List
from pydantic import BaseModel


class RegisterRequest(BaseModel):
    """Request model for user registration."""
    username: str
    password: str


class RegisterResponse(BaseModel):
    """Response model for user registration."""
    api_key: str
    user_id: str


class LoginRequest(BaseModel):
    """Request model for user login."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Response model for user login."""
    api_key: str


class AddFileResponse(BaseModel):
    """Response model for file upload."""
    file_id: str
    name: str
    size: int
    tags: List[str]


class FileMetadataResponse(BaseModel):
    """Response model for file metadata."""
    file_id: str
    name: str
    size: int
    tags: List[str]
    owner_id: str
    created_at: str


class ListFilesResponse(BaseModel):
    """Response model for file listing."""
    files: List[FileMetadataResponse]


class DeleteFilesResponse(BaseModel):
    """Response model for file deletion."""
    deleted_count: int
    file_ids: List[str]


class AddTagsRequest(BaseModel):
    """Request model for adding tags to files."""
    query_tags: List[str]
    new_tags: List[str]


class AddTagsResponse(BaseModel):
    """Response model for adding tags."""
    updated_count: int
    file_ids: List[str]


class DeleteTagsRequest(BaseModel):
    """Request model for deleting tags from files."""
    query_tags: List[str]
    tags_to_remove: List[str]


class DeleteTagsResponse(BaseModel):
    """Response model for deleting tags."""
    updated_count: int
    file_ids: List[str]


class ErrorResponse(BaseModel):
    """Response model for errors."""
    detail: str
    code: str
