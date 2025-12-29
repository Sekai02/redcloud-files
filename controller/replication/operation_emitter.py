"""
Operation emitter for capturing controller metadata mutations.

Emits replicable operations when controller metadata changes, incrementing
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


def emit_file_created(
    file_id: str,
    name: str,
    size: int,
    owner_id: str,
    created_at: str,
    tags: list,
    replaced_file_id: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None
) -> str:
    """
    Emit FILE_CREATED operation.

    Args:
        file_id: UUID of the file
        name: File name
        size: File size in bytes
        owner_id: UUID of the owner
        created_at: ISO8601 timestamp
        tags: List of tags
        replaced_file_id: UUID of replaced file if this is a replacement
        conn: Optional database connection

    Returns:
        Operation ID (UUID)
    """
    controller_id = get_controller_id()
    operation_id = str(uuid.uuid4())
    timestamp_ms = int(datetime.utcnow().timestamp() * 1000)

    vector_clock = get_and_increment_vector_clock(controller_id, conn=conn)

    payload = {
        "file_id": file_id,
        "name": name,
        "size": size,
        "owner_id": owner_id,
        "created_at": created_at,
        "tags": tags,
        "replaced_file_id": replaced_file_id
    }

    insert_operation(
        operation_id=operation_id,
        operation_type="FILE_CREATED",
        user_id=owner_id,
        timestamp_ms=timestamp_ms,
        vector_clock=vector_clock,
        payload=payload,
        applied=1,
        conn=conn
    )

    logger.info(
        f"Emitted FILE_CREATED operation [operation_id={operation_id}, "
        f"file_id={file_id}, name={name}, owner_id={owner_id}]"
    )

    return operation_id


def emit_file_deleted(
    file_id: str,
    owner_id: str,
    name: str,
    deleted_at: str,
    chunk_ids: list,
    conn: Optional[sqlite3.Connection] = None
) -> str:
    """
    Emit FILE_DELETED operation.

    Args:
        file_id: UUID of the file
        owner_id: UUID of the owner
        name: File name
        deleted_at: ISO8601 timestamp
        chunk_ids: List of chunk IDs that were deleted
        conn: Optional database connection

    Returns:
        Operation ID (UUID)
    """
    controller_id = get_controller_id()
    operation_id = str(uuid.uuid4())
    timestamp_ms = int(datetime.utcnow().timestamp() * 1000)

    vector_clock = get_and_increment_vector_clock(controller_id, conn=conn)

    payload = {
        "file_id": file_id,
        "owner_id": owner_id,
        "name": name,
        "deleted_at": deleted_at,
        "deleted_by_controller_id": controller_id,
        "chunk_ids": chunk_ids
    }

    insert_operation(
        operation_id=operation_id,
        operation_type="FILE_DELETED",
        user_id=owner_id,
        timestamp_ms=timestamp_ms,
        vector_clock=vector_clock,
        payload=payload,
        applied=1,
        conn=conn
    )

    logger.info(
        f"Emitted FILE_DELETED operation [operation_id={operation_id}, "
        f"file_id={file_id}, name={name}, owner_id={owner_id}]"
    )

    return operation_id


def emit_tags_added(
    file_id: str,
    tags: list,
    owner_id: str,
    conn: Optional[sqlite3.Connection] = None
) -> str:
    """
    Emit TAGS_ADDED operation.

    Args:
        file_id: UUID of the file
        tags: List of tags to add
        owner_id: UUID of the file owner
        conn: Optional database connection

    Returns:
        Operation ID (UUID)
    """
    controller_id = get_controller_id()
    operation_id = str(uuid.uuid4())
    timestamp_ms = int(datetime.utcnow().timestamp() * 1000)

    vector_clock = get_and_increment_vector_clock(controller_id, conn=conn)

    payload = {
        "file_id": file_id,
        "tags": tags,
        "owner_id": owner_id
    }

    insert_operation(
        operation_id=operation_id,
        operation_type="TAGS_ADDED",
        user_id=owner_id,
        timestamp_ms=timestamp_ms,
        vector_clock=vector_clock,
        payload=payload,
        applied=1,
        conn=conn
    )

    logger.info(
        f"Emitted TAGS_ADDED operation [operation_id={operation_id}, "
        f"file_id={file_id}, tags={tags}]"
    )

    return operation_id


def emit_tags_removed(
    file_id: str,
    tags: list,
    owner_id: str,
    conn: Optional[sqlite3.Connection] = None
) -> str:
    """
    Emit TAGS_REMOVED operation.

    Args:
        file_id: UUID of the file
        tags: List of tags to remove
        owner_id: UUID of the file owner
        conn: Optional database connection

    Returns:
        Operation ID (UUID)
    """
    controller_id = get_controller_id()
    operation_id = str(uuid.uuid4())
    timestamp_ms = int(datetime.utcnow().timestamp() * 1000)

    vector_clock = get_and_increment_vector_clock(controller_id, conn=conn)

    payload = {
        "file_id": file_id,
        "tags": tags,
        "owner_id": owner_id
    }

    insert_operation(
        operation_id=operation_id,
        operation_type="TAGS_REMOVED",
        user_id=owner_id,
        timestamp_ms=timestamp_ms,
        vector_clock=vector_clock,
        payload=payload,
        applied=1,
        conn=conn
    )

    logger.info(
        f"Emitted TAGS_REMOVED operation [operation_id={operation_id}, "
        f"file_id={file_id}, tags={tags}]"
    )

    return operation_id


def emit_chunks_created(
    file_id: str,
    chunks: list,
    owner_id: str,
    conn: Optional[sqlite3.Connection] = None
) -> str:
    """
    Emit CHUNKS_CREATED operation.

    Args:
        file_id: UUID of the file
        chunks: List of chunk dictionaries with chunk_id, chunk_index, size, checksum
        owner_id: UUID of the file owner
        conn: Optional database connection

    Returns:
        Operation ID (UUID)
    """
    controller_id = get_controller_id()
    operation_id = str(uuid.uuid4())
    timestamp_ms = int(datetime.utcnow().timestamp() * 1000)

    vector_clock = get_and_increment_vector_clock(controller_id, conn=conn)

    payload = {
        "file_id": file_id,
        "chunks": chunks,
        "owner_id": owner_id
    }

    insert_operation(
        operation_id=operation_id,
        operation_type="CHUNKS_CREATED",
        user_id=owner_id,
        timestamp_ms=timestamp_ms,
        vector_clock=vector_clock,
        payload=payload,
        applied=1,
        conn=conn
    )

    logger.info(
        f"Emitted CHUNKS_CREATED operation [operation_id={operation_id}, "
        f"file_id={file_id}, chunks_count={len(chunks)}]"
    )

    return operation_id
