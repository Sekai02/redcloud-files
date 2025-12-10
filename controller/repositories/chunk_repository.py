"""Chunk repository for database operations."""

from dataclasses import dataclass
from typing import List

from controller.database import get_db_connection


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
            
            return chunk_ids
        finally:
            if should_close:
                conn.close()
