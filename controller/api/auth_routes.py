"""Authentication API routes."""

from fastapi import APIRouter, status

from controller.models.api_models import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """
    Register a new user account.

    Parameters:
        - username: Unique username (must not already exist)
        - password: User password (will be hashed before storage)

    Returns:
        - api_key: Generated API Key with 'dfs_' prefix
        - user_id: UUID of created user

    Raises:
        - 400: Username already exists
        - 500: Internal server error
    """
    raise NotImplementedError("User registration not implemented")


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and generate new API Key.

    Parameters:
        - username: User's username
        - password: User's password

    Returns:
        - api_key: New API Key (replaces previous key)

    Raises:
        - 401: Invalid credentials
        - 500: Internal server error
    """
    raise NotImplementedError("User login not implemented")
