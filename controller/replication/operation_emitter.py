"""
Operation emitter for capturing user data mutations.

Emits replicable operations when user data changes, incrementing
the local vector clock and storing operations in the operation log.
"""

import uuid
import logging
from datetime import datetime
from typing import Dict, Optional
import sqlite3

from controller.database import get_db_connection
from controller.replication.controller_id import get_controller_id
from controller.replication.operation_log import insert_operation

logger = logging.getLogger(__name__)


def get_and_increment_vector_clock(
    controller_id: str,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, int]:
    """
    Get current vector clock and increment local controller's sequence.

    Args:
        controller_id: UUID of this controller
        conn: Optional database connection

    Returns:
        Updated vector clock as dict
    """
    def _get_and_increment(cursor: sqlite3.Cursor) -> Dict[str, int]:
        cursor.execute(
            "SELECT controller_id, sequence FROM vector_clock_state"
        )
        rows = cursor.fetchall()

        vector_clock = {row[0]: row[1] for row in rows}

        current_seq = vector_clock.get(controller_id, 0)
        new_seq = current_seq + 1
        vector_clock[controller_id] = new_seq

        cursor.execute(
            """
            INSERT INTO vector_clock_state (controller_id, sequence, last_seen_at)
            VALUES (?, ?, ?)
            ON CONFLICT(controller_id) DO UPDATE SET
                sequence = excluded.sequence,
                last_seen_at = excluded.last_seen_at
            """,
            (controller_id, new_seq, datetime.utcnow().isoformat())
        )

        return vector_clock

    if conn:
        return _get_and_increment(conn.cursor())
    else:
        with get_db_connection() as db_conn:
            result = _get_and_increment(db_conn.cursor())
            db_conn.commit()
            return result


def emit_user_created(
    user_id: str,
    username: str,
    password_hash: str,
    api_key: str,
    created_at: str,
    conn: Optional[sqlite3.Connection] = None
) -> str:
    """
    Emit USER_CREATED operation.

    Args:
        user_id: UUID of the user
        username: Username
        password_hash: Bcrypt password hash
        api_key: Initial API key
        created_at: ISO8601 timestamp
        conn: Optional database connection

    Returns:
        Operation ID (UUID)
    """
    controller_id = get_controller_id()
    operation_id = str(uuid.uuid4())
    timestamp_ms = int(datetime.utcnow().timestamp() * 1000)

    vector_clock = get_and_increment_vector_clock(controller_id, conn=conn)

    payload = {
        "user_id": user_id,
        "username": username,
        "password_hash": password_hash,
        "api_key": api_key,
        "created_at": created_at
    }

    insert_operation(
        operation_id=operation_id,
        operation_type="USER_CREATED",
        user_id=user_id,
        timestamp_ms=timestamp_ms,
        vector_clock=vector_clock,
        payload=payload,
        applied=1,
        conn=conn
    )

    logger.info(
        f"Emitted USER_CREATED operation [operation_id={operation_id}, "
        f"user_id={user_id}, username={username}]"
    )

    return operation_id


def emit_api_key_updated(
    user_id: str,
    new_api_key: str,
    key_updated_at: str,
    conn: Optional[sqlite3.Connection] = None
) -> str:
    """
    Emit API_KEY_UPDATED operation.

    Args:
        user_id: UUID of the user
        new_api_key: New API key
        key_updated_at: ISO8601 timestamp
        conn: Optional database connection

    Returns:
        Operation ID (UUID)
    """
    controller_id = get_controller_id()
    operation_id = str(uuid.uuid4())
    timestamp_ms = int(datetime.utcnow().timestamp() * 1000)

    vector_clock = get_and_increment_vector_clock(controller_id, conn=conn)

    payload = {
        "user_id": user_id,
        "new_api_key": new_api_key,
        "key_updated_at": key_updated_at
    }

    insert_operation(
        operation_id=operation_id,
        operation_type="API_KEY_UPDATED",
        user_id=user_id,
        timestamp_ms=timestamp_ms,
        vector_clock=vector_clock,
        payload=payload,
        applied=1,
        conn=conn
    )

    logger.info(
        f"Emitted API_KEY_UPDATED operation [operation_id={operation_id}, "
        f"user_id={user_id}]"
    )

    return operation_id
