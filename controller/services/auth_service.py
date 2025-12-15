"""Authentication service for business logic."""

from datetime import datetime
from typing import Optional
import sqlite3

from common.logging_config import get_logger
from controller.auth import hash_password, verify_password, generate_api_key
from controller.repositories.user_repository import UserRepository
from controller.exceptions import UserAlreadyExistsError, InvalidCredentialsError, InvalidAPIKeyError

logger = get_logger(__name__)


class AuthService:
    def __init__(self):
        self.user_repo = UserRepository()

    def register_user(self, username: str, password: str) -> tuple[str, str]:
        logger.info(f"Attempting to register user: {username}")
        existing_user = self.user_repo.get_by_username(username)
        if existing_user is not None:
            logger.warning(f"Registration failed: username '{username}' already exists")
            raise UserAlreadyExistsError(f"Username '{username}' already exists")

        from controller.utils import generate_uuid

        user_id = generate_uuid()
        password_hash = hash_password(password)
        api_key = generate_api_key()
        created_at = datetime.utcnow()

        try:
            user = self.user_repo.create_user(
                user_id=user_id,
                username=username,
                password_hash=password_hash,
                api_key=api_key,
                created_at=created_at,
            )
            logger.info(f"Successfully registered user: {username} [user_id={user_id}]")

            self._add_user_to_gossip(user, 'create')

        except sqlite3.IntegrityError:
            logger.warning(f"Registration failed due to integrity error: username '{username}'")
            raise UserAlreadyExistsError(f"Username '{username}' already exists")

        return api_key, user_id

    def login_user(self, username: str, password: str) -> str:
        logger.info(f"Login attempt for user: {username}")
        user = self.user_repo.get_by_username(username)
        if user is None:
            logger.warning(f"Login failed: username '{username}' not found")
            raise InvalidCredentialsError("Invalid username or password")

        if not verify_password(password, user.password_hash):
            logger.warning(f"Login failed: invalid password for username '{username}'")
            raise InvalidCredentialsError("Invalid username or password")

        new_api_key = generate_api_key()
        updated_at = datetime.utcnow()

        self.user_repo.update_api_key(user.user_id, new_api_key, updated_at)
        logger.info(f"Successfully logged in user: {username} [user_id={user.user_id}]")

        updated_user = self.user_repo.get_by_user_id(user.user_id)
        if updated_user:
            self._add_user_to_gossip(updated_user, 'update')

        return new_api_key

    def validate_api_key(self, api_key: str) -> Optional[str]:
        logger.debug("Validating API key")
        user = self.user_repo.get_by_api_key(api_key)
        if user is None:
            logger.warning("API key validation failed: invalid key")
            return None
        logger.debug(f"API key validated for user_id={user.user_id}")
        return user.user_id

    def _add_user_to_gossip(self, user, operation: str):
        try:
            from controller.routes.internal_routes import _gossip_service
            import asyncio

            if _gossip_service is None:
                logger.debug("Gossip service not available, skipping replication")
                return

            user_data = {
                'user_id': user.user_id,
                'username': user.username,
                'password_hash': user.password_hash,
                'api_key': user.api_key,
                'created_at': user.created_at.isoformat(),
                'key_updated_at': user.key_updated_at.isoformat() if user.key_updated_at else None,
                'vector_clock': user.vector_clock.to_json() if user.vector_clock else None,
                'last_modified_by': user.last_modified_by,
                'version': user.version
            }

            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_gossip_service.add_to_gossip_log(
                    entity_type='user',
                    entity_id=user.user_id,
                    operation=operation,
                    data=user_data
                ))
            else:
                loop.run_until_complete(_gossip_service.add_to_gossip_log(
                    entity_type='user',
                    entity_id=user.user_id,
                    operation=operation,
                    data=user_data
                ))

            logger.debug(f"Added user to gossip log: {user.username} ({operation})")
        except Exception as e:
            logger.warning(f"Failed to add user to gossip log: {e}")
