"""File service for business logic."""

from datetime import datetime
from typing import List, BinaryIO, AsyncIterator
import hashlib
import logging
import json
from pathlib import Path
import asyncio

from controller.repositories.file_repository import FileRepository, File
from controller.repositories.tag_repository import TagRepository
from controller.repositories.chunk_repository import ChunkRepository, Chunk
from controller.database import get_db_connection
from controller.exceptions import FileNotFoundError, UnauthorizedAccessError, EmptyTagListError
from controller.domain import FileMetadata
from controller.chunkserver_client import ChunkserverClient
from common.types import ChunkDescriptor
from common.constants import CHUNK_SIZE_BYTES

logger = logging.getLogger(__name__)


class FileService:
    def __init__(self):
        self.file_repo = FileRepository()
        self.tag_repo = TagRepository()
        self.chunk_repo = ChunkRepository()
        self.chunkserver_client = ChunkserverClient()

    async def upload_file(
        self,
        file_name: str,
        file_data: BinaryIO,
        file_size: int,
        tags: List[str],
        owner_id: str,
    ) -> FileMetadata:
        if not tags:
            raise EmptyTagListError("At least one tag is required for file upload")
        
        from controller.utils import generate_uuid
        
        file_id = generate_uuid()
        created_at = datetime.utcnow()
        
        chunks_with_data = self._split_into_chunks_with_data(file_data, file_id)
        
        written_chunk_ids = []
        
        try:
            for chunk_meta, chunk_data in chunks_with_data:
                success = await self.chunkserver_client.write_chunk(
                    chunk_id=chunk_meta.chunk_id,
                    file_id=chunk_meta.file_id,
                    chunk_index=chunk_meta.chunk_index,
                    data=chunk_data,
                    checksum=chunk_meta.checksum
                )
                
                if not success:
                    raise Exception(f"Failed to write chunk {chunk_meta.chunk_id} to chunkserver")
                
                written_chunk_ids.append(chunk_meta.chunk_id)
                logger.info(f"Wrote chunk {chunk_meta.chunk_index}/{len(chunks_with_data)} for file {file_id}")
            
            replaced_file_id = None
            old_chunk_ids = []
            
            with get_db_connection() as conn:
                try:
                    existing_file = self.file_repo.find_by_owner_and_name(
                        owner_id=owner_id,
                        name=file_name,
                        conn=conn
                    )
                    
                    if existing_file:
                        replaced_file_id = existing_file.file_id
                        old_chunks = self.chunk_repo.get_chunks_by_file(replaced_file_id)
                        old_chunk_ids = [chunk.chunk_id for chunk in old_chunks]
                        
                        self.file_repo.delete_file(replaced_file_id, conn=conn)
                        logger.info(f"Replacing existing file {replaced_file_id} with new file {file_id}")
                    
                    self.file_repo.create_file(
                        file_id=file_id,
                        name=file_name,
                        size=file_size,
                        owner_id=owner_id,
                        created_at=created_at,
                        conn=conn,
                    )
                    
                    self.tag_repo.add_tags(file_id, tags, conn=conn)
                    
                    self.chunk_repo.create_chunks(
                        [chunk_meta for chunk_meta, _ in chunks_with_data],
                        conn=conn
                    )
                    
                    conn.commit()
                    logger.info(f"Successfully uploaded file {file_id} with {len(chunks_with_data)} chunks")
                except Exception as e:
                    conn.rollback()
                    raise
            
            if old_chunk_ids:
                logger.info(f"Cleaning up {len(old_chunk_ids)} chunks from replaced file")
                await self._cleanup_chunks(old_chunk_ids)
                    
        except Exception as e:
            logger.error(f"Upload failed for file {file_id}: {e}")
            
            if written_chunk_ids:
                logger.info(f"Cleaning up {len(written_chunk_ids)} orphaned chunks")
                await self._cleanup_chunks(written_chunk_ids)
            
            raise
        
        return FileMetadata(
            file_id=file_id,
            name=file_name,
            size=file_size,
            tags=tags,
            owner_id=owner_id,
            created_at=created_at,
            replaced_file_id=replaced_file_id,
        )

    def _split_into_chunks_with_data(self, file_data: BinaryIO, file_id: str) -> List[tuple[Chunk, bytes]]:
        from controller.utils import generate_uuid
        
        chunks = []
        chunk_index = 0
        
        while True:
            chunk_data = file_data.read(CHUNK_SIZE_BYTES)
            if not chunk_data:
                break
            
            chunk_id = generate_uuid()
            checksum = hashlib.sha256(chunk_data).hexdigest()
            
            chunk_meta = Chunk(
                chunk_id=chunk_id,
                file_id=file_id,
                chunk_index=chunk_index,
                size=len(chunk_data),
                checksum=checksum,
            )
            
            chunks.append((chunk_meta, chunk_data))
            chunk_index += 1
        
        return chunks

    async def _cleanup_chunks(self, chunk_ids: List[str]) -> List[str]:
        """
        Delete chunks from chunkserver with retry logic.
        
        Args:
            chunk_ids: List of chunk IDs to delete
            
        Returns:
            List of chunk IDs that could not be deleted
        """
        failed_deletions = []
        
        for chunk_id in chunk_ids:
            max_attempts = 3
            deleted = False
            
            for attempt in range(max_attempts):
                try:
                    await self.chunkserver_client.delete_chunk(chunk_id)
                    logger.info(f"Deleted orphaned chunk {chunk_id}")
                    deleted = True
                    break
                except Exception as e:
                    if attempt < max_attempts - 1:
                        delay = 2 ** attempt
                        logger.warning(f"Failed to delete chunk {chunk_id}, retrying in {delay}s: {e}")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Failed to delete orphaned chunk {chunk_id} after {max_attempts} attempts: {e}")
            
            if not deleted:
                failed_deletions.append(chunk_id)
        
        if failed_deletions:
            await self._log_orphaned_chunks(failed_deletions)
        
        return failed_deletions
    
    async def _log_orphaned_chunks(self, chunk_ids: List[str]) -> None:
        """
        Log orphaned chunks that could not be deleted.
        
        Args:
            chunk_ids: List of chunk IDs that failed deletion
        """
        orphaned_log_path = Path("./data/orphaned_chunks.json")
        
        try:
            if orphaned_log_path.exists():
                with open(orphaned_log_path, 'r') as f:
                    orphaned_data = json.load(f)
            else:
                orphaned_data = []
            
            for chunk_id in chunk_ids:
                orphaned_data.append({
                    "chunk_id": chunk_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "reason": "Failed cleanup after upload failure or file deletion"
                })
            
            orphaned_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(orphaned_log_path, 'w') as f:
                json.dump(orphaned_data, f, indent=2)
            
            logger.warning(f"Logged {len(chunk_ids)} orphaned chunks to {orphaned_log_path}")
        except Exception as e:
            logger.error(f"Failed to log orphaned chunks: {e}")

    async def download_file(self, file_id: str, user_id: str) -> tuple[File, AsyncIterator[bytes]]:
        file = self.file_repo.get_by_id(file_id)
        if file is None:
            raise FileNotFoundError(f"File {file_id} not found")
        
        if file.owner_id != user_id:
            raise UnauthorizedAccessError(f"User {user_id} does not own file {file_id}")
        
        chunks = self.chunk_repo.get_chunks_by_file(file_id)
        
        async def stream_file_data():
            for chunk in chunks:
                logger.info(f"Streaming chunk {chunk.chunk_index}/{len(chunks)} for file {file_id}")
                try:
                    async for piece in self.chunkserver_client.read_chunk(chunk.chunk_id):
                        yield piece
                except FileNotFoundError:
                    logger.error(f"Chunk {chunk.chunk_id} not found, validating file integrity")
                    is_valid = await self.validate_file_integrity(file_id)
                    if not is_valid:
                        logger.error(f"File {file_id} is corrupted")
                    raise
        
        return file, stream_file_data()
    
    async def validate_file_integrity(self, file_id: str) -> bool:
        """
        Validate that all chunks for a file exist on chunkserver.
        
        Args:
            file_id: UUID of file to validate
            
        Returns:
            True if all chunks exist, False if any are missing
        """
        chunks = self.chunk_repo.get_chunks_by_file(file_id)
        
        for chunk in chunks:
            try:
                available = await self.chunkserver_client.ping()
                if not available:
                    logger.warning(f"Chunkserver unavailable during validation")
                    return True
                
            except Exception as e:
                logger.warning(f"Cannot validate chunk {chunk.chunk_id}: {e}")
                return False
        
        return True

    def get_chunk_descriptors(self, file_id: str, user_id: str) -> List[ChunkDescriptor]:
        file = self.file_repo.get_by_id(file_id)
        if file is None:
            raise FileNotFoundError(f"File {file_id} not found")
        
        if file.owner_id != user_id:
            raise UnauthorizedAccessError(f"User {user_id} does not own file {file_id}")
        
        chunks = self.chunk_repo.get_chunks_by_file(file_id)
        
        chunk_descriptors = [
            ChunkDescriptor(
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                size=chunk.size,
                checksum=chunk.checksum,
            )
            for chunk in chunks
        ]
        
        return chunk_descriptors

    async def delete_files(self, tags: List[str], user_id: str) -> List[str]:
        files = self.file_repo.query_by_tags_and_owner(tags, user_id)
        
        deleted_file_ids = []
        chunks_to_delete = []
        
        for file in files:
            chunks = self.chunk_repo.get_chunks_by_file(file.file_id)
            chunks_to_delete.extend([chunk.chunk_id for chunk in chunks])
        
        with get_db_connection() as conn:
            try:
                for file in files:
                    self.file_repo.delete_file(file.file_id, conn=conn)
                    deleted_file_ids.append(file.file_id)
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise
        
        if chunks_to_delete:
            logger.info(f"Deleting {len(chunks_to_delete)} chunks from chunkserver")
            await self._cleanup_chunks(chunks_to_delete)
        
        return deleted_file_ids

    def get_file_metadata(self, file_id: str, user_id: str) -> FileMetadata:
        file = self.file_repo.get_by_id(file_id)
        if file is None:
            raise FileNotFoundError(f"File {file_id} not found")
        
        if file.owner_id != user_id:
            raise UnauthorizedAccessError(f"User {user_id} does not own file {file_id}")
        
        tags = self.tag_repo.get_tags_for_file(file_id)
        
        return FileMetadata(
            file_id=file.file_id,
            name=file.name,
            size=file.size,
            tags=tags,
            owner_id=file.owner_id,
            created_at=file.created_at,
        )
