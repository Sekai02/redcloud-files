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

    async def add_tags_to_files(self, query_tags: List[str], new_tags: List[str], user_id: str) -> List[str]:
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
                for file_id in file_ids:
                    self.tag_repo.add_tags(file_id, new_tags, conn=conn)
                conn.commit()
                logger.info(f"Successfully added tags {new_tags} to {len(file_ids)} files [user_id={user_id}]")
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to add tags: {e} [user_id={user_id}]", exc_info=True)
                raise

        for file_id in file_ids:
            await self._gossip_file_tags_update(file_id, user_id)

        return file_ids

    async def remove_tags_from_files(self, query_tags: List[str], tags_to_remove: List[str], user_id: str) -> tuple[List[str], List[SkippedFileInfo]]:
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
                        updated_file_ids.append(file_id)
                conn.commit()
                logger.info(
                    f"Tag removal completed: {len(updated_file_ids)} updated, {len(skipped_files)} skipped [user_id={user_id}]"
                )
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to remove tags: {e} [user_id={user_id}]", exc_info=True)
                raise

        for file_id in updated_file_ids:
            await self._gossip_file_tags_update(file_id, user_id)

        return updated_file_ids, skipped_files

    async def _gossip_file_tags_update(self, file_id: str, user_id: str):
        """
        Gossip file with updated tags after tag modification.
        """
        try:
            from controller.routes.internal_routes import _gossip_service
            from controller.distributed_config import CONTROLLER_NODE_ID
            from controller.repositories.chunk_repository import ChunkRepository
            from controller.database import get_db_connection

            if _gossip_service is None:
                return

            file = self.file_repo.get_by_id(file_id)
            if not file:
                return

            tags = self.tag_repo.get_tags_for_file(file_id)
            chunks = ChunkRepository.get_chunks_by_file(file_id)

            vector_clock = '{}'
            version = 1
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT vector_clock, version FROM files WHERE file_id = ?",
                    (file_id,)
                )
                row = cursor.fetchone()
                if row:
                    vector_clock = row["vector_clock"] if row["vector_clock"] else '{}'
                    version = row["version"] if row["version"] else 1

            chunk_locations = {}
            with get_db_connection() as conn:
                cursor = conn.cursor()
                for chunk in chunks:
                    cursor.execute(
                        "SELECT chunkserver_id FROM chunk_locations WHERE chunk_id = ?",
                        (chunk.chunk_id,)
                    )
                    rows = cursor.fetchall()
                    chunk_locations[chunk.chunk_id] = [row["chunkserver_id"] for row in rows]

            file_data = {
                'file_id': file_id,
                'name': file.name,
                'size': file.size,
                'owner_id': file.owner_id,
                'created_at': file.created_at.isoformat(),
                'deleted': 0,
                'tags': tags,
                'chunks': [
                    {
                        'chunk_id': chunk.chunk_id,
                        'chunk_index': chunk.chunk_index,
                        'size': chunk.size,
                        'checksum': chunk.checksum
                    }
                    for chunk in chunks
                ],
                'chunk_locations': chunk_locations,
                'vector_clock': vector_clock,
                'last_modified_by': CONTROLLER_NODE_ID,
                'version': version
            }

            await _gossip_service.add_to_gossip_log(
                entity_type='file',
                entity_id=file_id,
                operation='update',
                data=file_data
            )
        except Exception as e:
            logger.warning(f"Failed to gossip tag update: {e}")
