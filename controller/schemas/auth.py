"""Pydantic schemas for authentication endpoints."""

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    """Request model for user registration."""
    username: str
    password: str


class RegisterResponse(BaseModel):
    """Response model for user registration."""
    api_key: str
    user_id: str


class LoginRequest(BaseModel):
    """Request model for user login."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Response model for user login."""
    api_key: str
