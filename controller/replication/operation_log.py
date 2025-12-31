"""
Operation log SQLite interface for replication.

Provides CRUD operations for the operations table, including
inserting new operations, querying by various criteria, and marking
operations as applied.
"""

import json
import logging
from typing import List, Optional, Dict
from datetime import datetime
import sqlite3

from controller.database import get_db_connection
from common.protocol import Operation, OperationSummary

logger = logging.getLogger(__name__)


def insert_operation(
    operation_id: str,
    operation_type: str,
    user_id: str,
    timestamp_ms: int,
    vector_clock: Dict[str, int],
    payload: Dict,
    applied: int = 0,
    conn: Optional[sqlite3.Connection] = None
) -> None:
    """
    Insert an operation into the operation log.

    Args:
        operation_id: UUID of the operation
        operation_type: Type of operation ('USER_CREATED' or 'API_KEY_UPDATED')
        user_id: UUID of the user affected
        timestamp_ms: UTC timestamp in milliseconds
        vector_clock: Vector clock as dict
        payload: Operation payload as dict
        applied: 0 if pending, 1 if applied locally
        conn: Optional database connection (uses context manager if None)
    """
    created_at = datetime.utcnow().isoformat()

    def _insert(cursor: sqlite3.Cursor):
        cursor.execute(
            """
            INSERT INTO operations
            (operation_id, operation_type, user_id, timestamp_ms, vector_clock,
             payload, applied, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation_id,
                operation_type,
                user_id,
                timestamp_ms,
                json.dumps(vector_clock),
                json.dumps(payload),
                applied,
                created_at
            )
        )

    if conn:
        _insert(conn.cursor())
    else:
        with get_db_connection() as db_conn:
            _insert(db_conn.cursor())
            db_conn.commit()

    logger.debug(f"Inserted operation {operation_id} (type={operation_type}, applied={applied})")


def get_operation_by_id(operation_id: str) -> Optional[Operation]:
    """
    Retrieve an operation by its ID.

    Args:
        operation_id: UUID of the operation

    Returns:
        Operation object if found, None otherwise
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT operation_id, operation_type, user_id, timestamp_ms,
                   vector_clock, payload, applied, created_at
            FROM operations
            WHERE operation_id = ?
            """,
            (operation_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return Operation(
            operation_id=row[0],
            operation_type=row[1],
            user_id=row[2],
            timestamp_ms=row[3],
            vector_clock=json.loads(row[4]),
            payload=json.loads(row[5]),
            applied=row[6],
            created_at=row[7]
        )


def get_recent_operations(limit: int = 100) -> List[Operation]:
    """
    Get recent operations (for gossip protocol).

    Args:
        limit: Maximum number of operations to return

    Returns:
        List of Operation objects, ordered by timestamp descending
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT operation_id, operation_type, user_id, timestamp_ms,
                   vector_clock, payload, applied, created_at
            FROM operations
            ORDER BY timestamp_ms DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = cursor.fetchall()

        return [
            Operation(
                operation_id=row[0],
                operation_type=row[1],
                user_id=row[2],
                timestamp_ms=row[3],
                vector_clock=json.loads(row[4]),
                payload=json.loads(row[5]),
                applied=row[6],
                created_at=row[7]
            )
            for row in rows
        ]


def get_all_operation_ids() -> List[str]:
    """
    Get all operation IDs (for anti-entropy protocol).

    Returns:
        List of operation IDs
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT operation_id FROM operations")
        rows = cursor.fetchall()
        return [row[0] for row in rows]


def get_operations_by_ids(operation_ids: List[str]) -> List[Operation]:
    """
    Fetch multiple operations by their IDs.

    Args:
        operation_ids: List of operation IDs to fetch

    Returns:
        List of Operation objects
    """
    if not operation_ids:
        return []

    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(operation_ids))
        cursor.execute(
            f"""
            SELECT operation_id, operation_type, user_id, timestamp_ms,
                   vector_clock, payload, applied, created_at
            FROM operations
            WHERE operation_id IN ({placeholders})
            """,
            operation_ids
        )
        rows = cursor.fetchall()

        return [
            Operation(
                operation_id=row[0],
                operation_type=row[1],
                user_id=row[2],
                timestamp_ms=row[3],
                vector_clock=json.loads(row[4]),
                payload=json.loads(row[5]),
                applied=row[6],
                created_at=row[7]
            )
            for row in rows
        ]


def get_operations_for_user(user_id: str) -> List[Operation]:
    """
    Get all operations for a specific user.

    Args:
        user_id: UUID of the user

    Returns:
        List of Operation objects for the user
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT operation_id, operation_type, user_id, timestamp_ms,
                   vector_clock, payload, applied, created_at
            FROM operations
            WHERE user_id = ?
            ORDER BY timestamp_ms ASC
            """,
            (user_id,)
        )
        rows = cursor.fetchall()

        return [
            Operation(
                operation_id=row[0],
                operation_type=row[1],
                user_id=row[2],
                timestamp_ms=row[3],
                vector_clock=json.loads(row[4]),
                payload=json.loads(row[5]),
                applied=row[6],
                created_at=row[7]
            )
            for row in rows
        ]


def mark_operation_applied(operation_id: str, conn: Optional[sqlite3.Connection] = None) -> None:
    """
    Mark an operation as applied.

    Args:
        operation_id: UUID of the operation
        conn: Optional database connection
    """
    def _update(cursor: sqlite3.Cursor):
        cursor.execute(
            "UPDATE operations SET applied = 1 WHERE operation_id = ?",
            (operation_id,)
        )

    if conn:
        _update(conn.cursor())
    else:
        with get_db_connection() as db_conn:
            _update(db_conn.cursor())
            db_conn.commit()

    logger.debug(f"Marked operation {operation_id} as applied")


def get_recent_operation_summaries(limit: int = 100) -> List[OperationSummary]:
    """
    Get recent operation summaries for gossip protocol.

    Args:
        limit: Maximum number of summaries to return

    Returns:
        List of OperationSummary objects
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT operation_id, operation_type, user_id, timestamp_ms, vector_clock
            FROM operations
            ORDER BY timestamp_ms DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = cursor.fetchall()

        return [
            OperationSummary(
                operation_id=row[0],
                operation_type=row[1],
                user_id=row[2],
                timestamp_ms=row[3],
                vector_clock=json.loads(row[4])
            )
            for row in rows
        ]
