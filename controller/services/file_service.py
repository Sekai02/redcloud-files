"""File service for business logic."""

from datetime import datetime
from typing import List, BinaryIO
import hashlib

from controller.repositories.file_repository import FileRepository, File
from controller.repositories.tag_repository import TagRepository
from controller.repositories.chunk_repository import ChunkRepository, Chunk
from controller.database import get_db_connection
from controller.exceptions import FileNotFoundError, UnauthorizedAccessError
from controller.domain import FileMetadata
from common.types import ChunkDescriptor
from common.constants import CHUNK_SIZE_BYTES


class FileService:
    def __init__(self):
        self.file_repo = FileRepository()
        self.tag_repo = TagRepository()
        self.chunk_repo = ChunkRepository()

    def upload_file(
        self,
        file_name: str,
        file_data: BinaryIO,
        file_size: int,
        tags: List[str],
        owner_id: str,
    ) -> FileMetadata:
        from controller.utils import generate_uuid
        
        file_id = generate_uuid()
        created_at = datetime.utcnow()
        
        chunks = self._split_into_chunks(file_data, file_id)
        
        with get_db_connection() as conn:
            try:
                self.file_repo.create_file(
                    file_id=file_id,
                    name=file_name,
                    size=file_size,
                    owner_id=owner_id,
                    created_at=created_at,
                    conn=conn,
                )
                
                self.tag_repo.add_tags(file_id, tags, conn=conn)
                
                self.chunk_repo.create_chunks(chunks, conn=conn)
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise
        
        return FileMetadata(
            file_id=file_id,
            name=file_name,
            size=file_size,
            tags=tags,
            owner_id=owner_id,
            created_at=created_at,
        )

    def _split_into_chunks(self, file_data: BinaryIO, file_id: str) -> List[Chunk]:
        from controller.utils import generate_uuid
        
        chunks = []
        chunk_index = 0
        
        while True:
            chunk_data = file_data.read(CHUNK_SIZE_BYTES)
            if not chunk_data:
                break
            
            chunk_id = generate_uuid()
            checksum = hashlib.sha256(chunk_data).hexdigest()
            
            chunks.append(Chunk(
                chunk_id=chunk_id,
                file_id=file_id,
                chunk_index=chunk_index,
                size=len(chunk_data),
                checksum=checksum,
            ))
            
            chunk_index += 1
        
        return chunks

    def download_file(self, file_id: str, user_id: str) -> tuple[File, List[ChunkDescriptor]]:
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
        
        return file, chunk_descriptors

    def delete_files(self, tags: List[str], user_id: str) -> List[str]:
        files = self.file_repo.query_by_tags_and_owner(tags, user_id)
        
        deleted_file_ids = []
        
        with get_db_connection() as conn:
            try:
                for file in files:
                    self.file_repo.delete_file(file.file_id, conn=conn)
                    deleted_file_ids.append(file.file_id)
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise
        
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
