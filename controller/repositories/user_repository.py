"""User repository for database operations."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict

from common.logging_config import get_logger
from controller.database import get_db_connection
from controller.vector_clock import VectorClock

logger = get_logger(__name__)


@dataclass
class User:
    user_id: str
    username: str
    password_hash: str
    api_key: Optional[str]
    created_at: datetime
    key_updated_at: Optional[datetime]
    vector_clock: Optional[VectorClock] = None
    last_modified_by: Optional[str] = None
    version: int = 0


class UserRepository:
    @staticmethod
    def create_user(
        user_id: str,
        username: str,
        password_hash: str,
        api_key: str,
        created_at: datetime,
        node_id: Optional[str] = None,
    ) -> User:
        logger.debug(f"Creating user: {username} [user_id={user_id}]")

        if node_id is None:
            try:
                from controller.distributed_config import CONTROLLER_NODE_ID
                node_id = CONTROLLER_NODE_ID
            except ImportError:
                node_id = "standalone"

        vector_clock = VectorClock({node_id: 1})

        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO users (user_id, username, password_hash, api_key, created_at,
                                      key_updated_at, vector_clock, last_modified_by, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, username, password_hash, api_key, created_at.isoformat(),
                     created_at.isoformat(), vector_clock.to_json(), node_id, 1)
                )
                conn.commit()
                logger.info(f"User created successfully: {username} [user_id={user_id}]")
            except Exception as e:
                logger.error(f"Failed to create user {username}: {e}", exc_info=True)
                raise

            return User(
                user_id=user_id,
                username=username,
                password_hash=password_hash,
                api_key=api_key,
                created_at=created_at,
                key_updated_at=created_at,
                vector_clock=vector_clock,
                last_modified_by=node_id,
                version=1,
            )

    @staticmethod
    def get_by_username(username: str) -> Optional[User]:
        logger.debug(f"Fetching user by username: {username}")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT user_id, username, password_hash, api_key, created_at, key_updated_at,
                          vector_clock, last_modified_by, version
                   FROM users WHERE username = ?""",
                (username,)
            )
            row = cursor.fetchone()

            if row is None:
                logger.debug(f"User not found: {username}")
                return None

            logger.debug(f"User found: {username} [user_id={row['user_id']}]")
            return User(
                user_id=row["user_id"],
                username=row["username"],
                password_hash=row["password_hash"],
                api_key=row["api_key"],
                created_at=datetime.fromisoformat(row["created_at"]),
                key_updated_at=datetime.fromisoformat(row["key_updated_at"]) if row["key_updated_at"] else None,
                vector_clock=VectorClock.from_json(row["vector_clock"]) if row.get("vector_clock") else None,
                last_modified_by=row.get("last_modified_by"),
                version=row.get("version", 0),
            )

    @staticmethod
    def get_by_api_key(api_key: str) -> Optional[User]:
        logger.debug("Fetching user by API key")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT user_id, username, password_hash, api_key, created_at, key_updated_at,
                          vector_clock, last_modified_by, version
                   FROM users WHERE api_key = ?""",
                (api_key,)
            )
            row = cursor.fetchone()

            if row is None:
                logger.debug("User not found for provided API key")
                return None

            logger.debug(f"User found by API key [user_id={row['user_id']}]")
            return User(
                user_id=row["user_id"],
                username=row["username"],
                password_hash=row["password_hash"],
                api_key=row["api_key"],
                created_at=datetime.fromisoformat(row["created_at"]),
                key_updated_at=datetime.fromisoformat(row["key_updated_at"]) if row["key_updated_at"] else None,
                vector_clock=VectorClock.from_json(row["vector_clock"]) if row.get("vector_clock") else None,
                last_modified_by=row.get("last_modified_by"),
                version=row.get("version", 0),
            )

    @staticmethod
    def update_api_key(user_id: str, new_api_key: str, updated_at: datetime, node_id: Optional[str] = None) -> None:
        logger.debug(f"Updating API key [user_id={user_id}]")

        if node_id is None:
            try:
                from controller.distributed_config import CONTROLLER_NODE_ID
                node_id = CONTROLLER_NODE_ID
            except ImportError:
                node_id = "standalone"

        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """SELECT vector_clock, version FROM users WHERE user_id = ?""",
                    (user_id,)
                )
                row = cursor.fetchone()

                if row and row["vector_clock"]:
                    vector_clock = VectorClock.from_json(row["vector_clock"])
                    vector_clock.increment(node_id)
                    new_version = row["version"] + 1
                else:
                    vector_clock = VectorClock({node_id: 1})
                    new_version = 1

                cursor.execute(
                    """
                    UPDATE users
                    SET api_key = ?, key_updated_at = ?, vector_clock = ?,
                        last_modified_by = ?, version = ?
                    WHERE user_id = ?
                    """,
                    (new_api_key, updated_at.isoformat(), vector_clock.to_json(),
                     node_id, new_version, user_id)
                )
                conn.commit()
                logger.info(f"API key updated successfully [user_id={user_id}]")
            except Exception as e:
                logger.error(f"Failed to update API key [user_id={user_id}]: {e}", exc_info=True)
                raise

    @staticmethod
    def get_all_users() -> list[User]:
        logger.debug("Fetching all users")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT user_id, username, password_hash, api_key, created_at, key_updated_at,
                          vector_clock, last_modified_by, version
                   FROM users"""
            )
            rows = cursor.fetchall()

            users = []
            for row in rows:
                users.append(User(
                    user_id=row["user_id"],
                    username=row["username"],
                    password_hash=row["password_hash"],
                    api_key=row["api_key"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    key_updated_at=datetime.fromisoformat(row["key_updated_at"]) if row["key_updated_at"] else None,
                    vector_clock=VectorClock.from_json(row["vector_clock"]) if row.get("vector_clock") else None,
                    last_modified_by=row.get("last_modified_by"),
                    version=row.get("version", 0),
                ))

            logger.debug(f"Fetched {len(users)} users")
            return users

    @staticmethod
    def get_by_user_id(user_id: str) -> Optional[User]:
        logger.debug(f"Fetching user by user_id: {user_id}")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT user_id, username, password_hash, api_key, created_at, key_updated_at,
                          vector_clock, last_modified_by, version
                   FROM users WHERE user_id = ?""",
                (user_id,)
            )
            row = cursor.fetchone()

            if row is None:
                logger.debug(f"User not found: {user_id}")
                return None

            logger.debug(f"User found: {user_id}")
            return User(
                user_id=row["user_id"],
                username=row["username"],
                password_hash=row["password_hash"],
                api_key=row["api_key"],
                created_at=datetime.fromisoformat(row["created_at"]),
                key_updated_at=datetime.fromisoformat(row["key_updated_at"]) if row["key_updated_at"] else None,
                vector_clock=VectorClock.from_json(row["vector_clock"]) if row.get("vector_clock") else None,
                last_modified_by=row.get("last_modified_by"),
                version=row.get("version", 0),
            )

    @staticmethod
    def merge_user(user: User) -> bool:
        logger.debug(f"Merging user: {user.username} [user_id={user.user_id}]")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                existing = UserRepository.get_by_user_id(user.user_id)

                if existing is None:
                    logger.info(f"User does not exist locally, inserting: {user.username}")
                    cursor.execute(
                        """
                        INSERT INTO users (user_id, username, password_hash, api_key, created_at,
                                          key_updated_at, vector_clock, last_modified_by, version)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (user.user_id, user.username, user.password_hash, user.api_key,
                         user.created_at.isoformat(),
                         user.key_updated_at.isoformat() if user.key_updated_at else None,
                         user.vector_clock.to_json() if user.vector_clock else None,
                         user.last_modified_by, user.version)
                    )
                    conn.commit()
                    return True

                if existing.vector_clock is None or user.vector_clock is None:
                    logger.warning(f"Missing vector clock, using version comparison [user_id={user.user_id}]")
                    if user.version > existing.version:
                        UserRepository._update_user(cursor, user)
                        conn.commit()
                        logger.info(f"User updated (version-based): {user.username}")
                        return True
                    return False

                comparison = existing.vector_clock.compare(user.vector_clock)

                if comparison == "before":
                    UserRepository._update_user(cursor, user)
                    conn.commit()
                    logger.info(f"User updated (incoming newer): {user.username}")
                    return True
                elif comparison == "concurrent":
                    logger.info(f"Concurrent update detected, resolving conflict [user_id={user.user_id}]")
                    merged_clock = existing.vector_clock.merge(user.vector_clock)

                    if user.version > existing.version:
                        user.vector_clock = merged_clock
                        UserRepository._update_user(cursor, user)
                        conn.commit()
                        logger.info(f"User updated (LWW resolution): {user.username}")
                        return True
                    elif user.version == existing.version:
                        if (user.last_modified_by or "") > (existing.last_modified_by or ""):
                            user.vector_clock = merged_clock
                            UserRepository._update_user(cursor, user)
                            conn.commit()
                            logger.info(f"User updated (node_id tiebreak): {user.username}")
                            return True

                logger.debug(f"User not updated (local is newer or equal): {user.username}")
                return False

            except Exception as e:
                logger.error(f"Failed to merge user {user.username}: {e}", exc_info=True)
                raise

    @staticmethod
    def _update_user(cursor, user: User) -> None:
        cursor.execute(
            """
            UPDATE users
            SET username = ?, password_hash = ?, api_key = ?, created_at = ?,
                key_updated_at = ?, vector_clock = ?, last_modified_by = ?, version = ?
            WHERE user_id = ?
            """,
            (user.username, user.password_hash, user.api_key,
             user.created_at.isoformat(),
             user.key_updated_at.isoformat() if user.key_updated_at else None,
             user.vector_clock.to_json() if user.vector_clock else None,
             user.last_modified_by, user.version, user.user_id)
        )
