"""Tag service for business logic."""

from typing import List

from common.logging_config import get_logger
from controller.repositories.file_repository import FileRepository
from controller.repositories.tag_repository import TagRepository
from controller.database import get_db_connection
from controller.domain import FileMetadata
from controller.exceptions import InvalidTagQueryError
from controller.schemas.files import SkippedFileInfo

logger = get_logger(__name__)


class TagService:
    def __init__(self):
        self.file_repo = FileRepository()
        self.tag_repo = TagRepository()

    def query_by_tags(self, tags: List[str], user_id: str) -> List[FileMetadata]:
        logger.info(f"Querying files by tags: {tags} [user_id={user_id}]")
        if not tags:
            logger.warning("Query failed: empty tag list")
            raise InvalidTagQueryError("Tag list cannot be empty")
        
        files = self.file_repo.query_by_tags_and_owner(tags, user_id)
        logger.info(f"Found {len(files)} files matching tags {tags} [user_id={user_id}]")
        
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
        logger.info(f"Adding tags {new_tags} to files matching {query_tags} [user_id={user_id}]")
        if not query_tags:
            logger.warning("Add tags failed: empty query tags")
            raise InvalidTagQueryError("Query tags cannot be empty")
        if not new_tags:
            logger.warning("Add tags failed: empty new tags")
            raise InvalidTagQueryError("New tags cannot be empty")
        
        file_ids = self.tag_repo.query_files_by_tags(query_tags, user_id)
        logger.info(f"Adding tags to {len(file_ids)} files [user_id={user_id}]")
        
        with get_db_connection() as conn:
            try:
                from controller.replication.operation_emitter import emit_tags_added

                for file_id in file_ids:
                    self.tag_repo.add_tags(file_id, new_tags, conn=conn)

                    emit_tags_added(
                        file_id=file_id,
                        tags=new_tags,
                        owner_id=user_id,
                        conn=conn
                    )

                conn.commit()
                logger.info(f"Successfully added tags {new_tags} to {len(file_ids)} files [user_id={user_id}]")
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to add tags: {e} [user_id={user_id}]", exc_info=True)
                raise
        
        return file_ids

    def remove_tags_from_files(self, query_tags: List[str], tags_to_remove: List[str], user_id: str) -> tuple[List[str], List[SkippedFileInfo]]:
        """
        Remove tags from files matching query.
        
        Args:
            query_tags: Tags to query files (AND logic)
            tags_to_remove: Tags to remove from matching files
            user_id: Owner ID of files
            
        Returns:
            Tuple of (updated_file_ids, skipped_files)
            - updated_file_ids: Files where tags were successfully removed
            - skipped_files: SkippedFileInfo objects for files that would become tagless
        """
        logger.info(f"Removing tags {tags_to_remove} from files matching {query_tags} [user_id={user_id}]")
        if not query_tags:
            logger.warning("Remove tags failed: empty query tags")
            raise InvalidTagQueryError("Query tags cannot be empty")
        if not tags_to_remove:
            logger.warning("Remove tags failed: empty tags to remove")
            raise InvalidTagQueryError("Tags to remove cannot be empty")
        
        file_ids = self.tag_repo.query_files_by_tags(query_tags, user_id)
        logger.info(f"Processing tag removal for {len(file_ids)} files [user_id={user_id}]")
        
        updated_file_ids = []
        skipped_files = []
        
        with get_db_connection() as conn:
            try:
                from controller.replication.operation_emitter import emit_tags_removed

                for file_id in file_ids:
                    if self.tag_repo.would_become_tagless(file_id, tags_to_remove, conn=conn):
                        file = self.file_repo.get_by_id(file_id)
                        if file:
                            current_tags = self.tag_repo.get_tags_for_file(file_id)
                            skipped_files.append(SkippedFileInfo(
                                file_id=file_id,
                                name=file.name,
                                current_tags=current_tags
                            ))
                            logger.debug(f"Skipped file {file.name} (would become tagless) [file_id={file_id}]")
                    else:
                        self.tag_repo.delete_tags(file_id, tags_to_remove, conn=conn)

                        emit_tags_removed(
                            file_id=file_id,
                            tags=tags_to_remove,
                            owner_id=user_id,
                            conn=conn
                        )

                        updated_file_ids.append(file_id)
                conn.commit()
                logger.info(
                    f"Tag removal completed: {len(updated_file_ids)} updated, {len(skipped_files)} skipped [user_id={user_id}]"
                )
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to remove tags: {e} [user_id={user_id}]", exc_info=True)
                raise
        
        return updated_file_ids, skipped_files
