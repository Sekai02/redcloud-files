"""Authentication and security utilities."""

import uuid
import bcrypt
from fastapi import Header, HTTPException, status

from controller.config import API_KEY_PREFIX


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password to hash

    Returns:
        Bcrypt hash of the password
    """
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against a bcrypt hash.

    Args:
        password: Plain text password to verify
        password_hash: Bcrypt hash to verify against

    Returns:
        True if password matches hash, False otherwise
    """
    password_bytes = password.encode('utf-8')
    hash_bytes = password_hash.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hash_bytes)


def generate_api_key() -> str:
    """
    Generate a new API Key with the configured prefix.

    Returns:
        API Key string in format: {prefix}{uuid4}
    """
    return f"{API_KEY_PREFIX}{uuid.uuid4()}"


async def get_current_user(authorization: str = Header(...)) -> str:
    """
    FastAPI dependency to validate API Key and extract user_id.

    Args:
        authorization: Authorization header value (format: "Bearer <api_key>")

    Returns:
        user_id of the authenticated user

    Raises:
        HTTPException: 401 if API Key is invalid or missing
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )

    api_key = authorization.replace("Bearer ", "")

    raise NotImplementedError("API Key validation not implemented")
