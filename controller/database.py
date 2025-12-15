"""Database schema and connection management for SQLite."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, Optional

from controller.config import DATABASE_PATH


def init_database() -> None:
    """
    Initialize database and create tables if they don't exist.
    """
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                api_key TEXT UNIQUE,
                created_at TEXT NOT NULL,
                key_updated_at TEXT,
                vector_clock TEXT DEFAULT '{}',
                last_modified_by TEXT,
                version INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                size INTEGER NOT NULL,
                owner_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                deleted INTEGER DEFAULT 0,
                vector_clock TEXT DEFAULT '{}',
                last_modified_by TEXT,
                version INTEGER DEFAULT 0,
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
                vector_clock TEXT DEFAULT '{}',
                last_modified_by TEXT,
                version INTEGER DEFAULT 0,
                UNIQUE(file_id, chunk_index),
                FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunk_locations (
                chunk_id TEXT NOT NULL,
                chunkserver_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(chunk_id, chunkserver_id),
                FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunkserver_nodes (
                node_id TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                last_heartbeat REAL NOT NULL,
                capacity_bytes INTEGER,
                used_bytes INTEGER,
                status TEXT DEFAULT 'active'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS controller_nodes (
                node_id TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                last_seen REAL NOT NULL,
                vector_clock TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gossip_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                data TEXT NOT NULL,
                vector_clock TEXT NOT NULL,
                timestamp REAL NOT NULL,
                gossiped_to TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_files_owner_name ON files(owner_id, name)
        """)

        conn.commit()


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """
    Safely convert a sqlite3.Row to a dictionary with NULL handling.
    
    Args:
        row: A sqlite3.Row object or None
        
    Returns:
        Dictionary with column names as keys, or None if row is None
    """
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def get_row_value(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    """
    Safely get a value from a sqlite3.Row with NULL handling.
    
    Args:
        row: A sqlite3.Row object
        key: Column name to retrieve
        default: Default value if column is NULL or missing
        
    Returns:
        Column value or default if NULL/missing
    """
    try:
        value = row[key]
        return value if value is not None else default
    except (KeyError, IndexError):
        return default
