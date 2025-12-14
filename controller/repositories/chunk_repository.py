"""Chunk repository for database operations."""

from dataclasses import dataclass
from typing import List, Dict, Any

from common.logging_config import get_logger
from controller.database import get_db_connection

logger = get_logger(__name__)


@dataclass
class Chunk:
    chunk_id: str
    file_id: str
    chunk_index: int
    size: int
    checksum: str


class ChunkRepository:
    @staticmethod
    def create_chunks(chunks: List[Chunk], conn=None) -> None:
        if not chunks:
            return
        
        logger.debug(f"Creating {len(chunks)} chunks for file_id={chunks[0].file_id if chunks else 'unknown'}")
        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()
        
        try:
            cursor = conn.cursor()
            for chunk in chunks:
                cursor.execute(
                    """
                    INSERT INTO chunks (chunk_id, file_id, chunk_index, size, checksum)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (chunk.chunk_id, chunk.file_id, chunk.chunk_index, chunk.size, chunk.checksum)
                )
            if should_close:
                conn.commit()
            logger.info(f"Created {len(chunks)} chunks successfully")
        except Exception as e:
            logger.error(f"Failed to create chunks: {e}", exc_info=True)
            raise
        finally:
            if should_close:
                conn.close()

    @staticmethod
    def get_chunks_by_file(file_id: str) -> List[Chunk]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT chunk_id, file_id, chunk_index, size, checksum
                FROM chunks
                WHERE file_id = ?
                ORDER BY chunk_index
                """,
                (file_id,)
            )
            rows = cursor.fetchall()
            
            return [
                Chunk(
                    chunk_id=row["chunk_id"],
                    file_id=row["file_id"],
                    chunk_index=row["chunk_index"],
                    size=row["size"],
                    checksum=row["checksum"],
                )
                for row in rows
            ]

    @staticmethod
    def delete_chunks(file_id: str, conn=None) -> List[str]:
        logger.debug(f"Deleting chunks [file_id={file_id}]")
        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()

        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT chunk_id FROM chunks WHERE file_id = ?",
                (file_id,)
            )
            chunk_ids = [row["chunk_id"] for row in cursor.fetchall()]

            cursor.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
            if should_close:
                conn.commit()

            logger.info(f"Deleted {len(chunk_ids)} chunks [file_id={file_id}]")
            return chunk_ids
        except Exception as e:
            logger.error(f"Failed to delete chunks [file_id={file_id}]: {e}", exc_info=True)
            raise
        finally:
            if should_close:
                conn.close()

    @staticmethod
    def merge_chunks(file_id: str, chunks_data: List[Dict[str, Any]], conn=None) -> None:
        """
        Replace all chunks for a file atomically (used during merge).
        """
        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()

        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
            for chunk_data in chunks_data:
                cursor.execute(
                    """
                    INSERT INTO chunks (chunk_id, file_id, chunk_index, size, checksum, vector_clock, last_modified_by, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_data['chunk_id'],
                        file_id,
                        chunk_data['chunk_index'],
                        chunk_data['size'],
                        chunk_data['checksum'],
                        chunk_data.get('vector_clock', '{}'),
                        chunk_data.get('last_modified_by'),
                        chunk_data.get('version', 0)
                    )
                )
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()
