"""
Operation applier for replication.

Applies remote operations to local database with conflict resolution.
Handles concurrent user creation and API key updates using deterministic
conflict resolution strategies.
"""

import logging
from typing import List, Optional, Set, Dict
from datetime import datetime
from collections import defaultdict
import asyncio

from common.protocol import Operation
from controller.database import get_db_connection
from controller.replication.operation_log import (
    mark_operation_applied,
    get_operation_by_id,
    get_operations_for_user
)
from controller.replication.vector_clock import VectorClock

logger = logging.getLogger(__name__)

_deferred_operations: Dict[str, Operation] = {}
_operation_dependencies: Dict[str, Set[str]] = defaultdict(set)
_skipped_file_ids: Set[str] = set()
_lock = asyncio.Lock()


class DependencyNotMetError(Exception):
    """
    Exception raised when an operation's dependency is not met.

    Args:
        dependency_description: Human-readable description of the dependency
        required_dependency: Key identifying the dependency (e.g., "file:uuid")
    """
    def __init__(self, dependency_description: str, required_dependency: str):
        self.dependency_description = dependency_description
        self.required_dependency = required_dependency
        super().__init__(dependency_description)


async def _defer_operation(operation: Operation, required_dependency: str):
    """
    Defer an operation until its dependency is satisfied.

    Args:
        operation: Operation to defer
        required_dependency: Key identifying the required dependency
    """
    async with _lock:
        _deferred_operations[operation.operation_id] = operation
        _operation_dependencies[required_dependency].add(operation.operation_id)

        logger.info(
            f"Deferred operation {operation.operation_id} "
            f"(type={operation.operation_type}) waiting for dependency: {required_dependency}"
        )


async def _check_and_apply_deferred_operations(applied_operation: Operation):
    """
    Check if any deferred operations can now be applied based on the just-applied operation.

    Args:
        applied_operation: Operation that was just successfully applied
    """
    async with _lock:
        dependency_key = _get_dependency_key(applied_operation)

        if dependency_key not in _operation_dependencies:
            return

        waiting_operation_ids = _operation_dependencies.pop(dependency_key)

        operations_to_retry = []
        for op_id in waiting_operation_ids:
            deferred_op = _deferred_operations.pop(op_id, None)
            if deferred_op:
                operations_to_retry.append(deferred_op)

    for operation in operations_to_retry:
        logger.info(
            f"Retrying deferred operation {operation.operation_id} "
            f"(dependency {dependency_key} now satisfied)"
        )

        try:
            await apply_operation(operation)
        except Exception as e:
            logger.error(
                f"Failed to apply deferred operation {operation.operation_id}: {e}",
                exc_info=True
            )


def _get_dependency_key(operation: Operation) -> str:
    """
    Get the dependency key that this operation satisfies.

    Args:
        operation: Operation to extract dependency key from

    Returns:
        Dependency key string (e.g., "file:uuid" or "user:uuid"), or empty string
    """
    if operation.operation_type == "FILE_CREATED":
        return f"file:{operation.payload['file_id']}"
    elif operation.operation_type == "USER_CREATED":
        return f"user:{operation.payload['user_id']}"

    return ""


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

    try:
        if operation.operation_type == "USER_CREATED":
            success = await _apply_user_created(operation)
        elif operation.operation_type == "API_KEY_UPDATED":
            success = await _apply_api_key_updated(operation)
        elif operation.operation_type == "FILE_CREATED":
            success = await _apply_file_created(operation)
        elif operation.operation_type == "FILE_DELETED":
            success = await _apply_file_deleted(operation)
        elif operation.operation_type == "TAGS_ADDED":
            success = await _apply_tags_added(operation)
        elif operation.operation_type == "TAGS_REMOVED":
            success = await _apply_tags_removed(operation)
        elif operation.operation_type == "CHUNKS_CREATED":
            success = await _apply_chunks_created(operation)
        else:
            logger.warning(f"Unknown operation type: {operation.operation_type}")
            return False

        if success:
            await _check_and_apply_deferred_operations(operation)

        return success

    except DependencyNotMetError as e:
        logger.info(
            f"Operation {operation.operation_id} deferred: {e.dependency_description}"
        )
        await _defer_operation(operation, e.required_dependency)
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
            logger.info(
                f"User {user_id} not found for API_KEY_UPDATED operation, deferring"
            )

            raise DependencyNotMetError(
                dependency_description=f"User {user_id} must exist before API key can be updated",
                required_dependency=f"user:{user_id}"
            )

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


async def _apply_file_created(operation: Operation) -> bool:
    """
    Apply FILE_CREATED operation with conflict resolution.

    Args:
        operation: FILE_CREATED operation

    Returns:
        True if applied, False if skipped
    """
    payload = operation.payload
    file_id = payload["file_id"]
    name = payload["name"]
    owner_id = payload["owner_id"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT file_id, name FROM files WHERE owner_id = ? AND name = ?",
            (owner_id, name)
        )
        existing_file = cursor.fetchone()

        cursor.execute(
            "SELECT file_id, deleted_at FROM file_tombstones WHERE owner_id = ? AND name = ?",
            (owner_id, name)
        )
        tombstone = cursor.fetchone()

        if tombstone:
            tombstone_deleted_at = tombstone[1]
            if tombstone_deleted_at > payload["created_at"]:
                logger.info(
                    f"FILE_CREATED operation {operation.operation_id} loses to tombstone "
                    f"(deleted_at={tombstone_deleted_at} > created_at={payload['created_at']}), skipping"
                )
                mark_operation_applied(operation.operation_id, conn=conn)
                conn.commit()
                return False

            cursor.execute(
                "DELETE FROM file_tombstones WHERE owner_id = ? AND name = ?",
                (owner_id, name)
            )
            logger.info(f"Removed tombstone for ({owner_id}, {name}), creating file")

        if existing_file:
            existing_file_id = existing_file[0]

            from controller.replication.operation_log import get_operations_by_ids

            cursor.execute(
                "SELECT operation_id FROM operations WHERE operation_type = 'FILE_CREATED' "
                "AND user_id = ? AND payload LIKE ?",
                (owner_id, f'%"name": "{name}"%')
            )
            file_created_ops_rows = cursor.fetchall()

            if file_created_ops_rows:
                file_created_op_ids = [row[0] for row in file_created_ops_rows]
                file_created_ops = get_operations_by_ids(file_created_op_ids)

                all_file_created_ops = [op for op in file_created_ops if op.payload.get("name") == name]
                all_file_created_ops.append(operation)

                winner = _resolve_concurrent_file_creation(all_file_created_ops)

                if winner.operation_id != operation.operation_id:
                    logger.info(
                        f"Concurrent file creation conflict for ({owner_id}, {name}): "
                        f"operation {operation.operation_id} lost to {winner.operation_id}, skipping"
                    )
                    mark_operation_applied(operation.operation_id, conn=conn)
                    conn.commit()

                    async with _lock:
                        _skipped_file_ids.add(payload["file_id"])
                        logger.info(
                            f"Registered file_id {payload['file_id']} as skipped due to conflict resolution"
                        )

                    return False

                logger.warning(
                    f"Concurrent file creation conflict for ({owner_id}, {name}): "
                    f"operation {operation.operation_id} won, updating file"
                )

                cursor.execute(
                    """
                    UPDATE files
                    SET file_id = ?, size = ?, created_at = ?
                    WHERE owner_id = ? AND name = ?
                    """,
                    (
                        payload["file_id"],
                        payload["size"],
                        payload["created_at"],
                        owner_id,
                        name
                    )
                )

                cursor.execute("DELETE FROM tags WHERE file_id = ?", (existing_file_id,))
                for tag in payload["tags"]:
                    cursor.execute(
                        "INSERT OR IGNORE INTO tags (file_id, tag) VALUES (?, ?)",
                        (payload["file_id"], tag)
                    )
            else:
                logger.debug(f"File '{name}' already exists for owner {owner_id}, skipping FILE_CREATED")
                mark_operation_applied(operation.operation_id, conn=conn)
                conn.commit()
                return False
        else:
            cursor.execute(
                """
                INSERT INTO files (file_id, name, size, owner_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload["file_id"],
                    payload["name"],
                    payload["size"],
                    payload["owner_id"],
                    payload["created_at"]
                )
            )

            for tag in payload["tags"]:
                cursor.execute(
                    "INSERT OR IGNORE INTO tags (file_id, tag) VALUES (?, ?)",
                    (payload["file_id"], tag)
                )

            logger.info(
                f"Applied FILE_CREATED operation [operation_id={operation.operation_id}, "
                f"file_id={payload['file_id']}, name={name}]"
            )

        _merge_vector_clock(operation.vector_clock, conn=conn)
        mark_operation_applied(operation.operation_id, conn=conn)
        conn.commit()

    return True


async def _apply_file_deleted(operation: Operation) -> bool:
    """
    Apply FILE_DELETED operation with tombstone creation.

    Args:
        operation: FILE_DELETED operation

    Returns:
        True if applied, False if skipped
    """
    payload = operation.payload
    file_id = payload["file_id"]
    owner_id = payload["owner_id"]
    name = payload["name"]
    deleted_at = payload["deleted_at"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT file_id, created_at FROM files WHERE owner_id = ? AND name = ?",
            (owner_id, name)
        )
        existing_file = cursor.fetchone()

        if existing_file:
            existing_created_at = existing_file[1]

            if deleted_at < existing_created_at:
                logger.info(
                    f"FILE_DELETED operation {operation.operation_id} loses to newer file "
                    f"(deleted_at={deleted_at} < created_at={existing_created_at}), skipping"
                )
                mark_operation_applied(operation.operation_id, conn=conn)
                conn.commit()
                return False

            cursor.execute("DELETE FROM files WHERE file_id = ?", (file_id,))

            logger.info(
                f"Applied FILE_DELETED operation [operation_id={operation.operation_id}, "
                f"file_id={file_id}, name={name}]"
            )
        else:
            logger.debug(
                f"File {file_id} not found for FILE_DELETED, may have been already deleted"
            )

        cursor.execute(
            """
            INSERT OR REPLACE INTO file_tombstones
            (file_id, owner_id, name, deleted_at, deleted_by_controller_id, operation_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                owner_id,
                name,
                deleted_at,
                payload["deleted_by_controller_id"],
                operation.operation_id
            )
        )

        _merge_vector_clock(operation.vector_clock, conn=conn)
        mark_operation_applied(operation.operation_id, conn=conn)
        conn.commit()

    return True


async def _apply_tags_added(operation: Operation) -> bool:
    """
    Apply TAGS_ADDED operation with set-convergent semantics.

    Args:
        operation: TAGS_ADDED operation

    Returns:
        True if applied, False if skipped
    """
    payload = operation.payload
    file_id = payload["file_id"]
    tags = payload["tags"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT file_id FROM files WHERE file_id = ?", (file_id,))
        if not cursor.fetchone():
            logger.info(
                f"File {file_id} not found for TAGS_ADDED operation, deferring"
            )

            raise DependencyNotMetError(
                dependency_description=f"File {file_id} must exist before tags can be added",
                required_dependency=f"file:{file_id}"
            )

        for tag in tags:
            cursor.execute(
                "INSERT OR IGNORE INTO tags (file_id, tag) VALUES (?, ?)",
                (file_id, tag)
            )

        logger.info(
            f"Applied TAGS_ADDED operation [operation_id={operation.operation_id}, "
            f"file_id={file_id}, tags={tags}]"
        )

        _merge_vector_clock(operation.vector_clock, conn=conn)
        mark_operation_applied(operation.operation_id, conn=conn)
        conn.commit()

    return True


async def _apply_tags_removed(operation: Operation) -> bool:
    """
    Apply TAGS_REMOVED operation with would_become_tagless validation.

    Args:
        operation: TAGS_REMOVED operation

    Returns:
        True if applied, False if skipped
    """
    payload = operation.payload
    file_id = payload["file_id"]
    tags = payload["tags"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT file_id FROM files WHERE file_id = ?", (file_id,))
        if not cursor.fetchone():
            logger.info(
                f"File {file_id} not found for TAGS_REMOVED operation, deferring"
            )

            raise DependencyNotMetError(
                dependency_description=f"File {file_id} must exist before tags can be removed",
                required_dependency=f"file:{file_id}"
            )

        cursor.execute(
            "SELECT tag FROM tags WHERE file_id = ?",
            (file_id,)
        )
        current_tags = set(row[0] for row in cursor.fetchall())

        remaining_tags = current_tags - set(tags)

        if not remaining_tags:
            logger.warning(
                f"TAGS_REMOVED operation {operation.operation_id} would leave file {file_id} tagless, skipping"
            )
            mark_operation_applied(operation.operation_id, conn=conn)
            conn.commit()
            return False

        for tag in tags:
            cursor.execute(
                "DELETE FROM tags WHERE file_id = ? AND tag = ?",
                (file_id, tag)
            )

        logger.info(
            f"Applied TAGS_REMOVED operation [operation_id={operation.operation_id}, "
            f"file_id={file_id}, tags={tags}]"
        )

        _merge_vector_clock(operation.vector_clock, conn=conn)
        mark_operation_applied(operation.operation_id, conn=conn)
        conn.commit()

    return True


async def _apply_chunks_created(operation: Operation) -> bool:
    """
    Apply CHUNKS_CREATED operation with checksum verification.

    Args:
        operation: CHUNKS_CREATED operation

    Returns:
        True if applied, False if skipped
    """
    payload = operation.payload
    file_id = payload["file_id"]
    chunks = payload["chunks"]

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT file_id FROM files WHERE file_id = ?", (file_id,))
        if not cursor.fetchone():
            async with _lock:
                is_skipped = file_id in _skipped_file_ids

            if is_skipped:
                logger.info(
                    f"File {file_id} was skipped due to conflict resolution, "
                    f"skipping dependent CHUNKS_CREATED operation {operation.operation_id}"
                )
                mark_operation_applied(operation.operation_id, conn=conn)
                conn.commit()
                return False

            logger.info(
                f"File {file_id} not found for CHUNKS_CREATED operation, deferring"
            )

            raise DependencyNotMetError(
                dependency_description=f"File {file_id} must exist before chunks can be created",
                required_dependency=f"file:{file_id}"
            )

        for chunk in chunks:
            chunk_id = chunk["chunk_id"]
            chunk_index = chunk["chunk_index"]
            size = chunk["size"]
            checksum = chunk["checksum"]

            cursor.execute(
                "SELECT checksum FROM chunks WHERE file_id = ? AND chunk_index = ?",
                (file_id, chunk_index)
            )
            existing = cursor.fetchone()

            if existing:
                existing_checksum = existing[0]
                if existing_checksum != checksum:
                    logger.error(
                        f"Chunk checksum mismatch for file {file_id} chunk {chunk_index}: "
                        f"existing={existing_checksum}, incoming={checksum}"
                    )
                    mark_operation_applied(operation.operation_id, conn=conn)
                    conn.commit()
                    return False

                logger.debug(f"Chunk already exists with matching checksum: {chunk_id}")
            else:
                cursor.execute(
                    """
                    INSERT INTO chunks (chunk_id, file_id, chunk_index, size, checksum)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (chunk_id, file_id, chunk_index, size, checksum)
                )

        logger.info(
            f"Applied CHUNKS_CREATED operation [operation_id={operation.operation_id}, "
            f"file_id={file_id}, chunks_count={len(chunks)}]"
        )

        _merge_vector_clock(operation.vector_clock, conn=conn)
        mark_operation_applied(operation.operation_id, conn=conn)
        conn.commit()

    return True


def _resolve_concurrent_file_creation(operations: List[Operation]) -> Operation:
    """
    Resolve concurrent file creation conflict using LWW + tiebreaker.

    Args:
        operations: List of FILE_CREATED operations for the same (owner_id, name)

    Returns:
        Winning operation
    """
    sorted_ops = sorted(
        operations,
        key=lambda op: (op.timestamp_ms, op.payload["file_id"])
    )
    winner = sorted_ops[0]

    logger.warning(
        f"Concurrent file creation conflict: "
        f"selected operation {winner.operation_id} from {len(operations)} candidates "
        f"(timestamp_ms={winner.timestamp_ms}, file_id={winner.payload['file_id']})"
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


async def start_deferred_operations_manager():
    """
    Background task that periodically retries deferred operations.

    Runs every 10 seconds and attempts to apply all deferred operations.
    Operations that still have unmet dependencies will remain deferred.
    """
    logger.info("Starting deferred operations retry manager")

    while True:
        try:
            await asyncio.sleep(10)

            async with _lock:
                if not _deferred_operations:
                    continue

                operations_to_retry = list(_deferred_operations.items())

            if operations_to_retry:
                logger.info(
                    f"Retrying {len(operations_to_retry)} deferred operations "
                    f"(periodic retry check)"
                )

            for op_id, operation in operations_to_retry:
                from controller.replication.operation_log import get_operation_by_id

                existing = get_operation_by_id(operation.operation_id)
                if existing and existing.applied == 1:
                    async with _lock:
                        _deferred_operations.pop(op_id, None)
                        for dep_key, waiting_ids in list(_operation_dependencies.items()):
                            if op_id in waiting_ids:
                                waiting_ids.remove(op_id)
                                if not waiting_ids:
                                    _operation_dependencies.pop(dep_key, None)

                    logger.debug(
                        f"Cleaned up already-applied deferred operation {op_id}"
                    )
                    continue

                try:
                    await apply_operation(operation)
                except Exception as e:
                    logger.debug(
                        f"Deferred operation {operation.operation_id} "
                        f"still cannot be applied: {e}"
                    )

        except Exception as e:
            logger.error(f"Error in deferred operations manager: {e}", exc_info=True)
