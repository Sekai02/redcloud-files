"""User repository for database operations."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from common.logging_config import get_logger
from controller.database import get_db_connection

logger = get_logger(__name__)


@dataclass
class User:
    user_id: str
    username: str
    password_hash: str
    api_key: Optional[str]
    created_at: datetime
    key_updated_at: Optional[datetime]


class UserRepository:
    @staticmethod
    def create_user(
        user_id: str,
        username: str,
        password_hash: str,
        api_key: str,
        created_at: datetime,
    ) -> User:
        logger.debug(f"Creating user: {username} [user_id={user_id}]")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO users (user_id, username, password_hash, api_key, created_at, key_updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, username, password_hash, api_key, created_at.isoformat(), created_at.isoformat())
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
            )

    @staticmethod
    def get_by_username(username: str) -> Optional[User]:
        logger.debug(f"Fetching user by username: {username}")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, username, password_hash, api_key, created_at, key_updated_at FROM users WHERE username = ?",
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
            )

    @staticmethod
    def get_by_api_key(api_key: str) -> Optional[User]:
        logger.debug("Fetching user by API key")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, username, password_hash, api_key, created_at, key_updated_at FROM users WHERE api_key = ?",
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
            )

    @staticmethod
    def update_api_key(user_id: str, new_api_key: str, updated_at: datetime) -> None:
        logger.debug(f"Updating API key [user_id={user_id}]")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    UPDATE users 
                    SET api_key = ?, key_updated_at = ?
                    WHERE user_id = ?
                    """,
                    (new_api_key, updated_at.isoformat(), user_id)
                )
                conn.commit()
                logger.info(f"API key updated successfully [user_id={user_id}]")
            except Exception as e:
                logger.error(f"Failed to update API key [user_id={user_id}]: {e}", exc_info=True)
                raise
