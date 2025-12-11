"""Pydantic schemas for file operation endpoints."""

from typing import List
from pydantic import BaseModel


class AddFileResponse(BaseModel):
    """Response model for file upload."""
    file_id: str
    name: str
    size: int
    tags: List[str]
    replaced_file_id: str = None


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
