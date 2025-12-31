"""Authentication API routes."""

from fastapi import APIRouter, status

from controller.schemas.auth import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse
)
from controller.services.auth_service import AuthService

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
    auth_service = AuthService()
    api_key, user_id = auth_service.register_user(request.username, request.password)
    
    return RegisterResponse(api_key=api_key, user_id=user_id)


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
    auth_service = AuthService()
    api_key = auth_service.login_user(request.username, request.password)
    
    return LoginResponse(api_key=api_key)
