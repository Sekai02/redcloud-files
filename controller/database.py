"""Database schema and connection management for SQLite."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from controller.config import DATABASE_PATH


def _migrate_user_operations_to_operations(cursor: sqlite3.Cursor) -> None:
    """
    Migrate user_operations table to operations table.
    """
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='user_operations'
    """)

    if cursor.fetchone():
        cursor.execute("ALTER TABLE user_operations RENAME TO operations")

        cursor.execute("DROP INDEX IF EXISTS idx_user_ops_user_id")
        cursor.execute("DROP INDEX IF EXISTS idx_user_ops_timestamp")
        cursor.execute("DROP INDEX IF EXISTS idx_user_ops_applied")


def init_database() -> None:
    """
    Initialize database and create tables if they don't exist.
    """
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        _migrate_user_operations_to_operations(cursor)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                api_key TEXT UNIQUE,
                created_at TEXT NOT NULL,
                key_updated_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                size INTEGER NOT NULL,
                owner_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(owner_id) REFERENCES users(user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                file_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY(file_id, tag),
                FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                size INTEGER NOT NULL,
                checksum TEXT NOT NULL,
                UNIQUE(file_id, chunk_index),
                FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS operations (
                operation_id TEXT PRIMARY KEY,
                operation_type TEXT NOT NULL,
                user_id TEXT NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                vector_clock TEXT NOT NULL,
                payload TEXT NOT NULL,
                applied INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vector_clock_state (
                controller_id TEXT PRIMARY KEY,
                sequence INTEGER NOT NULL,
                last_seen_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS peer_state (
                peer_address TEXT PRIMARY KEY,
                peer_controller_id TEXT,
                last_gossip_at TEXT,
                last_vector_clock TEXT,
                is_alive INTEGER DEFAULT 1
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_tombstones (
                file_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                name TEXT NOT NULL,
                deleted_at TEXT NOT NULL,
                deleted_by_controller_id TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                FOREIGN KEY(owner_id) REFERENCES users(user_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_files_owner_name ON files(owner_id, name)
        """)

        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_files_owner_name_unique ON files(owner_id, name)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tombstones_owner_name ON file_tombstones(owner_id, name)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tombstones_deleted_at ON file_tombstones(deleted_at)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ops_user_id ON operations(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ops_timestamp ON operations(timestamp_ms)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ops_applied ON operations(applied)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ops_type ON operations(operation_type)
        """)

        conn.commit()


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
