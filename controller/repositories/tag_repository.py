"""Tag repository for database operations."""

from typing import List

from common.logging_config import get_logger
from controller.database import get_db_connection

logger = get_logger(__name__)


class TagRepository:
    @staticmethod
    def add_tags(file_id: str, tags: List[str], conn=None) -> None:
        if not tags:
            return
        
        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()
        
        try:
            cursor = conn.cursor()
            for tag in tags:
                cursor.execute(
                    "INSERT OR IGNORE INTO tags (file_id, tag) VALUES (?, ?)",
                    (file_id, tag)
                )
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()

    @staticmethod
    def get_tags_for_file(file_id: str) -> List[str]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tag FROM tags WHERE file_id = ? ORDER BY tag",
                (file_id,)
            )
            rows = cursor.fetchall()
            return [row["tag"] for row in rows]

    @staticmethod
    def would_become_tagless(file_id: str, tags_to_remove: List[str], conn=None) -> bool:
        """
        Check if removing specified tags would leave file with zero tags.
        
        Args:
            file_id: UUID of the file
            tags_to_remove: List of tags to be removed
            conn: Optional database connection
            
        Returns:
            True if file would have no tags remaining, False otherwise
        """
        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()
        
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM tags WHERE file_id = ?",
                (file_id,)
            )
            total_tags = cursor.fetchone()["count"]
            
            if total_tags == 0:
                return True
            
            placeholders = ','.join('?' for _ in tags_to_remove)
            query = f"SELECT COUNT(*) as count FROM tags WHERE file_id = ? AND tag IN ({placeholders})"
            cursor.execute(query, [file_id] + tags_to_remove)
            tags_to_remove_count = cursor.fetchone()["count"]
            
            return total_tags - tags_to_remove_count == 0
        finally:
            if should_close:
                conn.close()

    @staticmethod
    def delete_tags(file_id: str, tags: List[str], conn=None) -> None:
        if not tags:
            return
        
        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()
        
        try:
            cursor = conn.cursor()
            placeholders = ','.join('?' for _ in tags)
            query = f"DELETE FROM tags WHERE file_id = ? AND tag IN ({placeholders})"
            cursor.execute(query, [file_id] + tags)
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()

    @staticmethod
    def query_files_by_tags(tags: List[str], owner_id: str) -> List[str]:
        if not tags:
            return []

        with get_db_connection() as conn:
            cursor = conn.cursor()

            placeholders = ','.join('?' for _ in tags)
            query = f"""
                SELECT DISTINCT t.file_id
                FROM tags t
                JOIN files f ON t.file_id = f.file_id
                WHERE f.owner_id = ?
                AND t.tag IN ({placeholders})
                GROUP BY t.file_id
                HAVING COUNT(DISTINCT t.tag) = ?
            """

            cursor.execute(query, [owner_id] + tags + [len(tags)])
            rows = cursor.fetchall()
            return [row["file_id"] for row in rows]

    @staticmethod
    def replace_tags(file_id: str, tags: List[str], conn=None) -> None:
        """
        Replace all tags for a file atomically (used during merge).
        """
        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()

        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tags WHERE file_id = ?", (file_id,))
            for tag in tags:
                cursor.execute("INSERT INTO tags (file_id, tag) VALUES (?, ?)", (file_id, tag))
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()
