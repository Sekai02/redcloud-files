"""Tag service for business logic."""

from typing import List

from controller.repositories.file_repository import FileRepository
from controller.repositories.tag_repository import TagRepository
from controller.database import get_db_connection
from controller.types import FileMetadata
from controller.exceptions import InvalidTagQueryError


class TagService:
    def __init__(self):
        self.file_repo = FileRepository()
        self.tag_repo = TagRepository()

    def query_by_tags(self, tags: List[str], user_id: str) -> List[FileMetadata]:
        if not tags:
            raise InvalidTagQueryError("Tag list cannot be empty")
        
        files = self.file_repo.query_by_tags_and_owner(tags, user_id)
        
        result = []
        for file in files:
            file_tags = self.tag_repo.get_tags_for_file(file.file_id)
            result.append(FileMetadata(
                file_id=file.file_id,
                name=file.name,
                size=file.size,
                tags=file_tags,
                owner_id=file.owner_id,
                created_at=file.created_at,
            ))
        
        return result

    def add_tags_to_files(self, query_tags: List[str], new_tags: List[str], user_id: str) -> List[str]:
        if not query_tags:
            raise InvalidTagQueryError("Query tags cannot be empty")
        if not new_tags:
            raise InvalidTagQueryError("New tags cannot be empty")
        
        file_ids = self.tag_repo.query_files_by_tags(query_tags, user_id)
        
        with get_db_connection() as conn:
            try:
                for file_id in file_ids:
                    self.tag_repo.add_tags(file_id, new_tags, conn=conn)
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise
        
        return file_ids

    def remove_tags_from_files(self, query_tags: List[str], tags_to_remove: List[str], user_id: str) -> List[str]:
        if not query_tags:
            raise InvalidTagQueryError("Query tags cannot be empty")
        if not tags_to_remove:
            raise InvalidTagQueryError("Tags to remove cannot be empty")
        
        file_ids = self.tag_repo.query_files_by_tags(query_tags, user_id)
        
        with get_db_connection() as conn:
            try:
                for file_id in file_ids:
                    self.tag_repo.delete_tags(file_id, tags_to_remove, conn=conn)
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise
        
        return file_ids
