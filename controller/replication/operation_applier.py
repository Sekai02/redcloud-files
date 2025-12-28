"""
Operation applier for replication.

Applies remote operations to local database with conflict resolution.
Handles concurrent user creation and API key updates using deterministic
conflict resolution strategies.
"""

import logging
from typing import List, Optional
from datetime import datetime

from common.protocol import Operation
from controller.database import get_db_connection
from controller.replication.operation_log import (
    mark_operation_applied,
    get_operation_by_id,
    get_operations_for_user
)
from controller.replication.vector_clock import VectorClock

logger = logging.getLogger(__name__)


async def apply_operation(operation: Operation) -> bool:
    """
    Apply a remote operation to the local database.

    Args:
        operation: Operation to apply

    Returns:
        True if applied, False if skipped (already applied or stale)
    """
    existing = get_operation_by_id(operation.operation_id)

    if existing and existing.applied == 1:
        logger.debug(
            f"Operation {operation.operation_id} already applied, skipping"
        )
        return False

    if not existing:
        _store_operation(operation)

    if operation.operation_type == "USER_CREATED":
        return await _apply_user_created(operation)
    elif operation.operation_type == "API_KEY_UPDATED":
        return await _apply_api_key_updated(operation)
    else:
        logger.warning(f"Unknown operation type: {operation.operation_type}")
        return False


def _store_operation(operation: Operation) -> None:
    """
    Store operation in local operation log.

    Args:
        operation: Operation to store
    """
    from controller.replication.operation_log import insert_operation

    insert_operation(
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        user_id=operation.user_id,
        timestamp_ms=operation.timestamp_ms,
        vector_clock=operation.vector_clock,
        payload=operation.payload,
        applied=0
    )

    logger.debug(f"Stored operation {operation.operation_id} in local log")


async def _apply_user_created(operation: Operation) -> bool:
    """
    Apply USER_CREATED operation with conflict resolution.

    Args:
        operation: USER_CREATED operation

    Returns:
        True if applied, False if skipped
    """
    payload = operation.payload
    username = payload["username"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT user_id FROM users WHERE username = ?",
            (username,)
        )
        existing_user = cursor.fetchone()

        if existing_user:
            existing_user_id = existing_user[0]

            user_operations = get_operations_for_user(existing_user_id)
            user_created_ops = [
                op for op in user_operations
                if op.operation_type == "USER_CREATED"
            ]

            all_operations = get_operations_for_user(operation.user_id)
            current_created_ops = [
                op for op in all_operations
                if op.operation_type == "USER_CREATED"
            ]

            all_user_created_ops = user_created_ops + current_created_ops

            if len(all_user_created_ops) > 1:
                winner = _resolve_concurrent_user_creation(all_user_created_ops)

                if winner.operation_id != operation.operation_id:
                    logger.info(
                        f"Concurrent user creation conflict for username '{username}': "
                        f"operation {operation.operation_id} lost to {winner.operation_id}, skipping"
                    )
                    mark_operation_applied(operation.operation_id, conn=conn)
                    conn.commit()
                    return False

                logger.warning(
                    f"Concurrent user creation conflict for username '{username}': "
                    f"operation {operation.operation_id} won, updating user"
                )

                cursor.execute(
                    """
                    UPDATE users
                    SET user_id = ?, password_hash = ?, api_key = ?, created_at = ?, key_updated_at = ?
                    WHERE username = ?
                    """,
                    (
                        payload["user_id"],
                        payload["password_hash"],
                        payload["api_key"],
                        payload["created_at"],
                        payload["created_at"],
                        username
                    )
                )
            else:
                logger.debug(f"User '{username}' already exists, skipping USER_CREATED")
                mark_operation_applied(operation.operation_id, conn=conn)
                conn.commit()
                return False
        else:
            cursor.execute(
                """
                INSERT INTO users (user_id, username, password_hash, api_key, created_at, key_updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["user_id"],
                    payload["username"],
                    payload["password_hash"],
                    payload["api_key"],
                    payload["created_at"],
                    payload["created_at"]
                )
            )

            logger.info(
                f"Applied USER_CREATED operation [operation_id={operation.operation_id}, "
                f"user_id={payload['user_id']}, username={username}]"
            )

        _merge_vector_clock(operation.vector_clock, conn=conn)
        mark_operation_applied(operation.operation_id, conn=conn)
        conn.commit()

    return True


async def _apply_api_key_updated(operation: Operation) -> bool:
    """
    Apply API_KEY_UPDATED operation with LWW + causality.

    Args:
        operation: API_KEY_UPDATED operation

    Returns:
        True if applied, False if skipped
    """
    payload = operation.payload
    user_id = payload["user_id"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT api_key, key_updated_at FROM users WHERE user_id = ?",
            (user_id,)
        )
        user_row = cursor.fetchone()

        if not user_row:
            logger.warning(
                f"User {user_id} not found for API_KEY_UPDATED operation, skipping"
            )
            mark_operation_applied(operation.operation_id, conn=conn)
            conn.commit()
            return False

        current_api_key = user_row[0]
        current_key_updated_at = user_row[1]

        user_operations = get_operations_for_user(user_id)
        api_key_ops = [
            op for op in user_operations
            if op.operation_type == "API_KEY_UPDATED" and op.applied == 1
        ]

        if api_key_ops:
            latest_applied_op = max(api_key_ops, key=lambda op: op.timestamp_ms)

            incoming_clock = VectorClock(clocks=operation.vector_clock)
            current_clock = VectorClock(clocks=latest_applied_op.vector_clock)

            if incoming_clock.happens_before(current_clock):
                logger.debug(
                    f"API_KEY_UPDATED operation {operation.operation_id} is stale "
                    f"(causally earlier), skipping"
                )
                mark_operation_applied(operation.operation_id, conn=conn)
                conn.commit()
                return False

            if current_clock.happens_before(incoming_clock):
                logger.debug(
                    f"API_KEY_UPDATED operation {operation.operation_id} is causal successor, applying"
                )
                should_apply = True
            else:
                incoming_timestamp_ms = operation.timestamp_ms
                current_timestamp_ms = latest_applied_op.timestamp_ms

                if incoming_timestamp_ms > current_timestamp_ms:
                    logger.info(
                        f"Concurrent API_KEY_UPDATED: operation {operation.operation_id} "
                        f"wins (LWW: {incoming_timestamp_ms} > {current_timestamp_ms})"
                    )
                    should_apply = True
                elif incoming_timestamp_ms < current_timestamp_ms:
                    logger.debug(
                        f"Concurrent API_KEY_UPDATED: operation {operation.operation_id} "
                        f"loses (LWW: {incoming_timestamp_ms} < {current_timestamp_ms}), skipping"
                    )
                    mark_operation_applied(operation.operation_id, conn=conn)
                    conn.commit()
                    return False
                else:
                    if operation.operation_id < latest_applied_op.operation_id:
                        logger.info(
                            f"Concurrent API_KEY_UPDATED with same timestamp: "
                            f"operation {operation.operation_id} wins (UUID tiebreaker)"
                        )
                        should_apply = True
                    else:
                        logger.debug(
                            f"Concurrent API_KEY_UPDATED with same timestamp: "
                            f"operation {operation.operation_id} loses (UUID tiebreaker), skipping"
                        )
                        mark_operation_applied(operation.operation_id, conn=conn)
                        conn.commit()
                        return False

            if should_apply:
                cursor.execute(
                    """
                    UPDATE users
                    SET api_key = ?, key_updated_at = ?
                    WHERE user_id = ?
                    """,
                    (
                        payload["new_api_key"],
                        payload["key_updated_at"],
                        user_id
                    )
                )

                logger.info(
                    f"Applied API_KEY_UPDATED operation [operation_id={operation.operation_id}, "
                    f"user_id={user_id}]"
                )
        else:
            cursor.execute(
                """
                UPDATE users
                SET api_key = ?, key_updated_at = ?
                WHERE user_id = ?
                """,
                (
                    payload["new_api_key"],
                    payload["key_updated_at"],
                    user_id
                )
            )

            logger.info(
                f"Applied API_KEY_UPDATED operation (first for user) "
                f"[operation_id={operation.operation_id}, user_id={user_id}]"
            )

        _merge_vector_clock(operation.vector_clock, conn=conn)
        mark_operation_applied(operation.operation_id, conn=conn)
        conn.commit()

    return True


def _resolve_concurrent_user_creation(operations: List[Operation]) -> Operation:
    """
    Resolve concurrent user creation conflict using deterministic tiebreaker.

    Args:
        operations: List of USER_CREATED operations for the same username

    Returns:
        Winning operation
    """
    sorted_ops = sorted(operations, key=lambda op: (op.timestamp_ms, op.user_id))
    winner = sorted_ops[0]

    logger.warning(
        f"Concurrent user creation conflict: "
        f"selected operation {winner.operation_id} from {len(operations)} candidates "
        f"(timestamp={winner.timestamp_ms}, user_id={winner.user_id})"
    )

    return winner


def _merge_vector_clock(vector_clock: dict, conn) -> None:
    """
    Merge remote vector clock into local state.

    Args:
        vector_clock: Remote vector clock as dict
        conn: Database connection
    """
    cursor = conn.cursor()

    for controller_id, sequence in vector_clock.items():
        cursor.execute(
            "SELECT sequence FROM vector_clock_state WHERE controller_id = ?",
            (controller_id,)
        )
        row = cursor.fetchone()

        current_seq = row[0] if row else 0
        new_seq = max(current_seq, sequence)

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
