"""File repository for database operations."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from controller.database import get_db_connection


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
        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()
        
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO files (file_id, name, size, owner_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (file_id, name, size, owner_id, created_at.isoformat())
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
                "SELECT file_id, name, size, owner_id, created_at FROM files WHERE file_id = ?",
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
                "SELECT file_id, name, size, owner_id, created_at FROM files WHERE owner_id = ? AND name = ?",
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
                    "SELECT file_id, name, size, owner_id, created_at FROM files WHERE owner_id = ? AND name = ?",
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
        should_close = conn is None
        if conn is None:
            conn = get_db_connection().__enter__()
        
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
            if should_close:
                conn.commit()
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
