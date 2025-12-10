"""Authentication service for business logic."""

from datetime import datetime
from typing import Optional
import sqlite3

from controller.auth import hash_password, verify_password, generate_api_key
from controller.repositories.user_repository import UserRepository
from controller.exceptions import UserAlreadyExistsError, InvalidCredentialsError, InvalidAPIKeyError


class AuthService:
    def __init__(self):
        self.user_repo = UserRepository()

    def register_user(self, username: str, password: str) -> tuple[str, str]:
        existing_user = self.user_repo.get_by_username(username)
        if existing_user is not None:
            raise UserAlreadyExistsError(f"Username '{username}' already exists")
        
        from controller.utils import generate_uuid
        
        user_id = generate_uuid()
        password_hash = hash_password(password)
        api_key = generate_api_key()
        created_at = datetime.utcnow()
        
        try:
            self.user_repo.create_user(
                user_id=user_id,
                username=username,
                password_hash=password_hash,
                api_key=api_key,
                created_at=created_at,
            )
        except sqlite3.IntegrityError:
            raise UserAlreadyExistsError(f"Username '{username}' already exists")
        
        return api_key, user_id

    def login_user(self, username: str, password: str) -> str:
        user = self.user_repo.get_by_username(username)
        if user is None:
            raise InvalidCredentialsError("Invalid username or password")
        
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid username or password")
        
        new_api_key = generate_api_key()
        updated_at = datetime.utcnow()
        
        self.user_repo.update_api_key(user.user_id, new_api_key, updated_at)
        
        return new_api_key

    def validate_api_key(self, api_key: str) -> Optional[str]:
        user = self.user_repo.get_by_api_key(api_key)
        if user is None:
            return None
        return user.user_id
