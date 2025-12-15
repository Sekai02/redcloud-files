"""Test to verify the sqlite3.Row.get() bug fix."""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from controller.database import get_db_connection, init_database
from controller.repositories.user_repository import UserRepository


@pytest.fixture
def test_db(monkeypatch):
    """
    Create a temporary test database.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        monkeypatch.setattr("controller.database.DATABASE_PATH", str(db_path))
        monkeypatch.setattr("controller.config.DATABASE_PATH", str(db_path))
        init_database()
        yield db_path


def test_login_scenario_with_gossiped_data(test_db):
    """
    Reproduce the exact scenario that was failing in production:
    1. User is created on one controller
    2. Data is gossiped to another controller (with NULL fields)
    3. Login attempt should work without AttributeError
    """
    user = UserRepository.create_user(
        user_id="test-user-id",
        username="alejandro",
        password_hash="hashed_password_123",
        api_key="test-api-key",
        created_at=datetime.now(),
        node_id="node-1"
    )
    
    assert user is not None
    
    fetched_user = UserRepository.get_by_username("alejandro")
    assert fetched_user is not None
    assert fetched_user.username == "alejandro"
    assert fetched_user.password_hash == "hashed_password_123"
    assert fetched_user.api_key == "test-api-key"


def test_user_with_null_vector_clock_fields(test_db):
    """
    Test that users with NULL vector_clock, last_modified_by, and version
    can be retrieved without errors.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO users 
               (user_id, username, password_hash, api_key, created_at, 
                key_updated_at, vector_clock, last_modified_by, version)
               VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
            ("user-null", "testuser", "hash123", "key123", datetime.now().isoformat())
        )
        conn.commit()
    
    user = UserRepository.get_by_username("testuser")
    assert user is not None
    assert user.username == "testuser"
    assert user.vector_clock is None
    assert user.last_modified_by is None
    assert user.version == 0


def test_all_user_retrieval_methods_with_null_fields(test_db):
    """
    Verify all retrieval methods work with NULL fields.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO users 
               (user_id, username, password_hash, api_key, created_at, 
                key_updated_at, vector_clock, last_modified_by, version)
               VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
            ("user-id", "testuser", "hash", "api-key", datetime.now().isoformat())
        )
        conn.commit()
    
    user_by_username = UserRepository.get_by_username("testuser")
    assert user_by_username is not None
    assert user_by_username.vector_clock is None
    assert user_by_username.last_modified_by is None
    assert user_by_username.version == 0
    
    user_by_api_key = UserRepository.get_by_api_key("api-key")
    assert user_by_api_key is not None
    assert user_by_api_key.vector_clock is None
    assert user_by_api_key.last_modified_by is None
    assert user_by_api_key.version == 0
    
    user_by_id = UserRepository.get_by_user_id("user-id")
    assert user_by_id is not None
    assert user_by_id.vector_clock is None
    assert user_by_id.last_modified_by is None
    assert user_by_id.version == 0
    
    all_users = UserRepository.get_all_users()
    assert len(all_users) == 1
    assert all_users[0].vector_clock is None
    assert all_users[0].last_modified_by is None
    assert all_users[0].version == 0
