"""Common schemas used across multiple endpoints."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Response model for errors."""
    detail: str
    code: str
