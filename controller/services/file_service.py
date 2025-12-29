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
        
        chunks_metadata = []
        written_chunk_ids = []
        
        try:
            for chunk_meta, chunk_data in self._split_into_chunks_with_data(file_data, file_id):
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
                chunks_metadata.append(chunk_meta)
                logger.info(f"Wrote chunk {chunk_meta.chunk_index} for file {file_id}")
            
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
                        chunks_metadata,
                        conn=conn
                    )

                    from controller.replication.operation_emitter import emit_file_created, emit_chunks_created

                    chunks_payload = [
                        {
                            "chunk_id": chunk.chunk_id,
                            "chunk_index": chunk.chunk_index,
                            "size": chunk.size,
                            "checksum": chunk.checksum
                        }
                        for chunk in chunks_metadata
                    ]

                    emit_chunks_created(
                        file_id=file_id,
                        chunks=chunks_payload,
                        owner_id=owner_id,
                        conn=conn
                    )

                    emit_file_created(
                        file_id=file_id,
                        name=file_name,
                        size=file_size,
                        owner_id=owner_id,
                        created_at=created_at.isoformat(),
                        tags=tags,
                        replaced_file_id=replaced_file_id,
                        conn=conn
                    )

                    conn.commit()
                    logger.info(f"Successfully uploaded file {file_id} with {len(chunks_metadata)} chunks")
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

    def _split_into_chunks_with_data(self, file_data: BinaryIO, file_id: str):
        from controller.utils import generate_uuid
        
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
            
            yield (chunk_meta, chunk_data)
            chunk_index += 1

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
            self._mark_chunks_for_gc(failed_deletions)

        return failed_deletions

    def _mark_chunks_for_gc(self, chunk_ids: List[str]) -> None:
        """
        Mark chunks for distributed garbage collection.

        Args:
            chunk_ids: List of chunk IDs to mark for GC
        """
        try:
            from controller.replication.chunk_gc_manager import ChunkGCManager

            with get_db_connection() as conn:
                cursor = conn.cursor()
                now = datetime.utcnow().isoformat()

                for chunk_id in chunk_ids:
                    cursor.execute(
                        """
                        INSERT INTO chunk_liveness (chunk_id, referenced_by_files, last_verified_at, marked_for_gc)
                        VALUES (?, ?, ?, 1)
                        ON CONFLICT(chunk_id) DO UPDATE SET
                            marked_for_gc = 1,
                            last_verified_at = excluded.last_verified_at
                        """,
                        (chunk_id, json.dumps([]), now)
                    )

                conn.commit()

            logger.info(f"Marked {len(chunk_ids)} chunks for distributed GC")
        except Exception as e:
            logger.error(f"Failed to mark chunks for GC: {e}", exc_info=True)

    async def download_file(self, file_id: str, user_id: str) -> tuple[File, AsyncIterator[bytes]]:
        file = self.file_repo.get_by_id(file_id)
        if file is None:
            raise FileNotFoundError(f"File {file_id} not found")

        if file.owner_id != user_id:
            raise UnauthorizedAccessError(f"User {user_id} does not own file {file_id}")

        chunks = self.chunk_repo.get_chunks_by_file(file_id)

        if not chunks:
            logger.warning(f"File {file_id} has no chunks in database")
            raise FileNotFoundError(f"File {file_id} has no data")

        async def stream_file_data():
            total_chunks = len(chunks)
            bytes_streamed = 0

            logger.info(f"Starting download of file {file_id} ({total_chunks} chunks, {file.size} bytes)")

            for chunk in chunks:
                chunk_num = chunk.chunk_index + 1
                logger.info(f"Streaming chunk {chunk_num}/{total_chunks} (chunk_id={chunk.chunk_id})")

                try:
                    async for piece in self.chunkserver_client.read_chunk(chunk.chunk_id):
                        bytes_streamed += len(piece)
                        yield piece
                except FileNotFoundError:
                    logger.error(
                        f"Chunk {chunk.chunk_id} (index {chunk.chunk_index}) not found on chunkserver. "
                        f"Downloaded {bytes_streamed}/{file.size} bytes before failure."
                    )
                    raise
                except Exception as e:
                    logger.error(
                        f"Error streaming chunk {chunk.chunk_id} (index {chunk.chunk_index}): {e}. "
                        f"Downloaded {bytes_streamed}/{file.size} bytes before failure."
                    )
                    raise

            logger.info(f"Successfully streamed file {file_id}: {bytes_streamed} bytes total")

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
        file_chunks_map = {}

        for file in files:
            chunks = self.chunk_repo.get_chunks_by_file(file.file_id)
            chunk_ids = [chunk.chunk_id for chunk in chunks]
            chunks_to_delete.extend(chunk_ids)
            file_chunks_map[file.file_id] = chunk_ids

        with get_db_connection() as conn:
            try:
                from controller.replication.operation_emitter import emit_file_deleted

                for file in files:
                    emit_file_deleted(
                        file_id=file.file_id,
                        owner_id=file.owner_id,
                        name=file.name,
                        deleted_at=datetime.utcnow().isoformat(),
                        chunk_ids=file_chunks_map.get(file.file_id, []),
                        conn=conn
                    )

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
