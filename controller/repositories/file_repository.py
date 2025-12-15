"""File repository for database operations."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any

from common.logging_config import get_logger
from controller.database import get_db_connection
from controller.vector_clock import VectorClock
from controller.conflict_resolver import ConflictResolver

logger = get_logger(__name__)


@dataclass
class File:
    file_id: str
    name: str
    size: int
    owner_id: str
    created_at: datetime


class FileRepository:
    @staticmethod
    def create_file(
        file_id: str,
        name: str,
        size: int,
        owner_id: str,
        created_at: datetime,
        conn=None
    ) -> File:
        from controller.distributed_config import CONTROLLER_NODE_ID

        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()

        try:
            cursor = conn.cursor()

            vector_clock = VectorClock({CONTROLLER_NODE_ID: 1})

            cursor.execute(
                """
                INSERT INTO files (file_id, name, size, owner_id, created_at, deleted, vector_clock, last_modified_by, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (file_id, name, size, owner_id, created_at.isoformat(), 0, vector_clock.to_json(), CONTROLLER_NODE_ID, 1)
            )
            if should_close:
                conn.commit()

            return File(
                file_id=file_id,
                name=name,
                size=size,
                owner_id=owner_id,
                created_at=created_at,
            )
        finally:
            if should_close:
                conn.close()

    @staticmethod
    def get_by_id(file_id: str) -> Optional[File]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT file_id, name, size, owner_id, created_at FROM files WHERE file_id = ? AND deleted = 0",
                (file_id,)
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return File(
                file_id=row["file_id"],
                name=row["name"],
                size=row["size"],
                owner_id=row["owner_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    @staticmethod
    def find_by_owner_and_name(owner_id: str, name: str, conn=None) -> Optional[File]:
        if conn is not None:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT file_id, name, size, owner_id, created_at FROM files WHERE owner_id = ? AND name = ? AND deleted = 0",
                (owner_id, name)
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return File(
                file_id=row["file_id"],
                name=row["name"],
                size=row["size"],
                owner_id=row["owner_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        else:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT file_id, name, size, owner_id, created_at FROM files WHERE owner_id = ? AND name = ? AND deleted = 0",
                    (owner_id, name)
                )
                row = cursor.fetchone()

                if row is None:
                    return None

                return File(
                    file_id=row["file_id"],
                    name=row["name"],
                    size=row["size"],
                    owner_id=row["owner_id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )

    @staticmethod
    def delete_file(file_id: str, conn=None) -> None:
        """
        Soft delete a file by setting deleted=1.
        """
        from controller.distributed_config import CONTROLLER_NODE_ID

        logger.debug(f"Deleting file [file_id={file_id}]")
        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()

        try:
            cursor = conn.cursor()

            cursor.execute("SELECT vector_clock, version FROM files WHERE file_id = ?", (file_id,))
            row = cursor.fetchone()

            if row:
                vc = VectorClock.from_json(row["vector_clock"]) if row["vector_clock"] else VectorClock({})
                vc = vc.increment(CONTROLLER_NODE_ID)
                new_version = row["version"] + 1

                cursor.execute(
                    """
                    UPDATE files
                    SET deleted = 1, vector_clock = ?, last_modified_by = ?, version = ?
                    WHERE file_id = ?
                    """,
                    (vc.to_json(), CONTROLLER_NODE_ID, new_version, file_id)
                )

            if should_close:
                conn.commit()
            logger.info(f"File deleted successfully [file_id={file_id}]")
        except Exception as e:
            logger.error(f"Failed to delete file [file_id={file_id}]: {e}", exc_info=True)
            raise
        finally:
            if should_close:
                conn.close()

    @staticmethod
    def query_by_tags_and_owner(tags: List[str], owner_id: str) -> List[File]:
        if not tags:
            return []

        with get_db_connection() as conn:
            cursor = conn.cursor()

            placeholders = ','.join('?' for _ in tags)
            query = f"""
                SELECT DISTINCT f.file_id, f.name, f.size, f.owner_id, f.created_at
                FROM files f
                JOIN tags t ON f.file_id = t.file_id
                WHERE f.owner_id = ?
                AND f.deleted = 0
                AND t.tag IN ({placeholders})
                GROUP BY f.file_id
                HAVING COUNT(DISTINCT t.tag) = ?
            """

            cursor.execute(query, [owner_id] + tags + [len(tags)])
            rows = cursor.fetchall()

            return [
                File(
                    file_id=row["file_id"],
                    name=row["name"],
                    size=row["size"],
                    owner_id=row["owner_id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    @staticmethod
    def merge_file(file_data: Dict[str, Any], conn=None) -> File:
        """
        Merge remote file with local version using vector clock conflict resolution.
        Handles file metadata, tags, chunks, and chunk_locations atomically.
        """
        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()

        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT file_id, name, size, owner_id, created_at, deleted,
                       vector_clock, last_modified_by, version
                FROM files WHERE file_id = ?
                """,
                (file_data['file_id'],)
            )
            local_row = cursor.fetchone()

            if local_row:
                resolution = ConflictResolver.resolve(dict(local_row), file_data)

                if resolution['action'] == 'keep_local':
                    logger.info(f"Keeping local version of file {file_data['file_id']} ({resolution['reason']})")
                    return File(
                        file_id=local_row["file_id"],
                        name=local_row["name"],
                        size=local_row["size"],
                        owner_id=local_row["owner_id"],
                        created_at=datetime.fromisoformat(local_row["created_at"]),
                    )

            logger.info(f"Taking remote version of file {file_data['file_id']}")

            cursor.execute(
                """
                INSERT OR REPLACE INTO files
                (file_id, name, size, owner_id, created_at, deleted, vector_clock, last_modified_by, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_data['file_id'],
                    file_data['name'],
                    file_data['size'],
                    file_data['owner_id'],
                    file_data['created_at'],
                    file_data.get('deleted', 0),
                    file_data.get('vector_clock', '{}'),
                    file_data.get('last_modified_by'),
                    file_data.get('version', 0)
                )
            )

            from controller.repositories.tag_repository import TagRepository
            TagRepository.replace_tags(file_data['file_id'], file_data.get('tags', []), conn=conn)

            from controller.repositories.chunk_repository import ChunkRepository
            ChunkRepository.merge_chunks(file_data['file_id'], file_data.get('chunks', []), conn=conn)

            chunk_locations = file_data.get('chunk_locations', {})
            if chunk_locations:
                import time
                for chunk_id, server_ids in chunk_locations.items():
                    for server_id in server_ids:
                        cursor.execute("""
                            INSERT OR IGNORE INTO chunk_locations (chunk_id, chunkserver_id, created_at)
                            VALUES (?, ?, ?)
                        """, (chunk_id, server_id, time.time()))

            if should_close:
                conn.commit()

            return File(
                file_id=file_data['file_id'],
                name=file_data['name'],
                size=file_data['size'],
                owner_id=file_data['owner_id'],
                created_at=datetime.fromisoformat(file_data['created_at']) if isinstance(file_data['created_at'], str) else file_data['created_at'],
            )
        finally:
            if should_close:
                conn.close()
