"""File operation API routes."""

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status, HTTPException
from fastapi.responses import StreamingResponse

from controller.auth import get_current_user
from controller.exceptions import EmptyTagListError
from controller.schemas.files import (
    AddFileResponse,
    ListFilesResponse,
    DeleteFilesResponse,
    AddTagsRequest,
    AddTagsResponse,
    DeleteTagsRequest,
    DeleteTagsResponse,
    FileMetadataResponse
)
from controller.services.file_service import FileService
from controller.services.tag_service import TagService
from controller.utils import parse_tags

router = APIRouter(prefix="/files", tags=["Files"])


@router.post("", response_model=AddFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    tags: str = Form(...),
    current_user: str = Depends(get_current_user)
):
    """
    Upload a file with associated tags.

    Parameters:
        - file: File to upload (multipart/form-data)
        - tags: Comma-separated list of tags (e.g., "tag1,tag2,tag3")
        - Authorization header: Bearer <api_key> (required)

    Returns:
        - file_id: UUID of uploaded file
        - name: Original filename
        - size: File size in bytes
        - tags: List of associated tags

    Raises:
        - 401: Invalid or missing API Key
        - 413: File too large
        - 500: Internal server error
        - 503: Chunkserver unavailable
    """
    file_service = FileService()
    
    tag_list = parse_tags(tags)
    
    if not tag_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one tag is required for file upload"
        )
    
    file_content = await file.read()
    file_size = len(file_content)
    
    from io import BytesIO
    file_data = BytesIO(file_content)
    
    file_metadata = await file_service.upload_file(
        file_name=file.filename,
        file_data=file_data,
        file_size=file_size,
        tags=tag_list,
        owner_id=current_user,
    )
    
    return AddFileResponse(
        file_id=file_metadata.file_id,
        name=file_metadata.name,
        size=file_metadata.size,
        tags=file_metadata.tags,
        replaced_file_id=file_metadata.replaced_file_id,
    )


@router.get("", response_model=ListFilesResponse)
async def list_files(
    tags: str = Query(..., description="Comma-separated tags for AND query"),
    current_user: str = Depends(get_current_user)
):
    """
    Query files by tag intersection (AND logic).

    Parameters:
        - tags: Comma-separated list of tags (e.g., "tag1,tag2")
        - Authorization header: Bearer <api_key> (required)

    Returns:
        - files: List of file metadata matching ALL provided tags
                 (only returns files owned by current user)

    Raises:
        - 400: Invalid tag query
        - 401: Invalid or missing API Key
        - 500: Internal server error
    """
    tag_service = TagService()
    
    tag_list = parse_tags(tags)
    
    files = tag_service.query_by_tags(tag_list, current_user)
    
    file_responses = [
        FileMetadataResponse(
            file_id=file.file_id,
            name=file.name,
            size=file.size,
            tags=file.tags,
            owner_id=file.owner_id,
            created_at=file.created_at.isoformat(),
        )
        for file in files
    ]
    
    return ListFilesResponse(files=file_responses)


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    Download a file by file_id.

    Parameters:
        - file_id: UUID of file to download
        - Authorization header: Bearer <api_key> (required)

    Returns:
        - StreamingResponse with file data

    Raises:
        - 401: Invalid or missing API Key
        - 403: User does not own this file
        - 404: File not found
        - 500: Internal server error
        - 503: Chunkserver unavailable
    """
    file_service = FileService()
    
    file, stream_generator = await file_service.download_file(file_id, current_user)
    
    return StreamingResponse(
        stream_generator,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{file.name}"',
            "Content-Length": str(file.size),
        }
    )


@router.delete("", response_model=DeleteFilesResponse)
async def delete_files(
    tags: str = Query(..., description="Comma-separated tags for AND query"),
    current_user: str = Depends(get_current_user)
):
    """
    Delete files matching tag query (AND logic).

    Parameters:
        - tags: Comma-separated list of tags (e.g., "tag1,tag2")
        - Authorization header: Bearer <api_key> (required)

    Returns:
        - deleted_count: Number of files deleted
        - file_ids: List of deleted file UUIDs
                   (only deletes files owned by current user)

    Raises:
        - 400: Invalid tag query
        - 401: Invalid or missing API Key
        - 500: Internal server error
    """
    file_service = FileService()
    
    tag_list = parse_tags(tags)
    
    deleted_file_ids = await file_service.delete_files(tag_list, current_user)
    
    return DeleteFilesResponse(
        deleted_count=len(deleted_file_ids),
        file_ids=deleted_file_ids,
    )


@router.post("/tags", response_model=AddTagsResponse)
async def add_tags(
    request: AddTagsRequest,
    current_user: str = Depends(get_current_user)
):
    """
    Add tags to files matching query.

    Parameters:
        - query_tags: Tags to query files (AND logic)
        - new_tags: Tags to add to matching files
        - Authorization header: Bearer <api_key> (required)

    Returns:
        - updated_count: Number of files updated
        - file_ids: List of updated file UUIDs
                   (only updates files owned by current user)

    Raises:
        - 400: Invalid request
        - 401: Invalid or missing API Key
        - 500: Internal server error
    """
    tag_service = TagService()
    
    updated_file_ids = tag_service.add_tags_to_files(
        request.query_tags,
        request.new_tags,
        current_user
    )
    
    return AddTagsResponse(
        updated_count=len(updated_file_ids),
        file_ids=updated_file_ids,
    )


@router.delete("/tags", response_model=DeleteTagsResponse)
async def delete_tags(
    request: DeleteTagsRequest,
    current_user: str = Depends(get_current_user)
):
    """
    Remove tags from files matching query.

    Parameters:
        - query_tags: Tags to query files (AND logic)
        - tags_to_remove: Tags to remove from matching files
        - Authorization header: Bearer <api_key> (required)

    Returns:
        - updated_count: Number of files updated
        - file_ids: List of updated file UUIDs
        - skipped_files: List of file UUIDs skipped to prevent becoming tagless
                   (only updates files owned by current user)

    Raises:
        - 400: Invalid request
        - 401: Invalid or missing API Key
        - 500: Internal server error
    """
    tag_service = TagService()
    
    updated_file_ids, skipped_files = tag_service.remove_tags_from_files(
        request.query_tags,
        request.tags_to_remove,
        current_user
    )
    
    return DeleteTagsResponse(
        updated_count=len(updated_file_ids),
        file_ids=updated_file_ids,
        skipped_files=skipped_files,
    )
