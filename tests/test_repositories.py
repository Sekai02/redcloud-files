"""Integration tests for database repositories."""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from controller.database import get_db_connection, get_row_value, init_database, row_to_dict
from controller.repositories.chunk_repository import Chunk, ChunkRepository
from controller.repositories.file_repository import File, FileRepository
from controller.repositories.tag_repository import TagRepository
from controller.repositories.user_repository import User, UserRepository
from controller.vector_clock import VectorClock


@pytest.fixture
def test_db(monkeypatch) -> Generator[Path, None, None]:
    """
    Create a temporary test database for each test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        monkeypatch.setattr("controller.database.DATABASE_PATH", str(db_path))
        monkeypatch.setattr("controller.config.DATABASE_PATH", str(db_path))
        init_database()
        yield db_path


class TestDatabaseHelpers:
    """Test database helper functions."""

    def test_row_to_dict_with_valid_row(self, test_db):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("test-id", "testuser", "hash123", datetime.now().isoformat())
            )
            conn.commit()
            
            cursor.execute("SELECT * FROM users WHERE user_id = ?", ("test-id",))
            row = cursor.fetchone()
            
            result = row_to_dict(row)
            assert result is not None
            assert result["user_id"] == "test-id"
            assert result["username"] == "testuser"
            assert isinstance(result, dict)

    def test_row_to_dict_with_none(self):
        result = row_to_dict(None)
        assert result is None

    def test_get_row_value_with_existing_column(self, test_db):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("test-id", "testuser", "hash123", datetime.now().isoformat())
            )
            conn.commit()
            
            cursor.execute("SELECT * FROM users WHERE user_id = ?", ("test-id",))
            row = cursor.fetchone()
            
            assert get_row_value(row, "username") == "testuser"
            assert get_row_value(row, "user_id") == "test-id"

    def test_get_row_value_with_null_column(self, test_db):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("test-id", "testuser", "hash123", datetime.now().isoformat())
            )
            conn.commit()
            
            cursor.execute("SELECT * FROM users WHERE user_id = ?", ("test-id",))
            row = cursor.fetchone()
            
            assert get_row_value(row, "api_key") is None
            assert get_row_value(row, "api_key", "default") == "default"

    def test_get_row_value_with_missing_column(self, test_db):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("test-id", "testuser", "hash123", datetime.now().isoformat())
            )
            conn.commit()
            
            cursor.execute("SELECT * FROM users WHERE user_id = ?", ("test-id",))
            row = cursor.fetchone()
            
            assert get_row_value(row, "nonexistent") is None
            assert get_row_value(row, "nonexistent", "default") == "default"


class TestUserRepository:
    """Test UserRepository with various scenarios."""

    def test_create_user(self, test_db):
        user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash123",
            api_key="key123",
            created_at=datetime.now(),
            node_id="node-1"
        )
        
        assert user.user_id == "user-123"
        assert user.username == "testuser"
        assert user.password_hash == "hash123"
        assert user.api_key == "key123"
        assert user.vector_clock is not None
        assert user.version == 1

    def test_get_by_username_existing(self, test_db):
        created_user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash123",
            api_key="key123",
            created_at=datetime.now()
        )
        
        fetched_user = UserRepository.get_by_username("testuser")
        assert fetched_user is not None
        assert fetched_user.user_id == created_user.user_id
        assert fetched_user.username == created_user.username

    def test_get_by_username_nonexistent(self, test_db):
        user = UserRepository.get_by_username("nonexistent")
        assert user is None

    def test_get_by_api_key_existing(self, test_db):
        created_user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash123",
            api_key="key123",
            created_at=datetime.now()
        )
        
        fetched_user = UserRepository.get_by_api_key("key123")
        assert fetched_user is not None
        assert fetched_user.user_id == created_user.user_id
        assert fetched_user.api_key == "key123"

    def test_get_by_api_key_nonexistent(self, test_db):
        user = UserRepository.get_by_api_key("nonexistent-key")
        assert user is None

    def test_get_by_user_id_existing(self, test_db):
        created_user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash123",
            api_key="key123",
            created_at=datetime.now()
        )
        
        fetched_user = UserRepository.get_by_user_id("user-123")
        assert fetched_user is not None
        assert fetched_user.user_id == "user-123"
        assert fetched_user.username == created_user.username

    def test_get_by_user_id_nonexistent(self, test_db):
        user = UserRepository.get_by_user_id("nonexistent-id")
        assert user is None

    def test_get_all_users_empty(self, test_db):
        users = UserRepository.get_all_users()
        assert users == []

    def test_get_all_users_multiple(self, test_db):
        UserRepository.create_user(
            user_id="user-1",
            username="user1",
            password_hash="hash1",
            api_key="key1",
            created_at=datetime.now()
        )
        UserRepository.create_user(
            user_id="user-2",
            username="user2",
            password_hash="hash2",
            api_key="key2",
            created_at=datetime.now()
        )
        
        users = UserRepository.get_all_users()
        assert len(users) == 2
        assert all(isinstance(u, User) for u in users)

    def test_update_api_key(self, test_db):
        user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash123",
            api_key="old-key",
            created_at=datetime.now()
        )
        
        new_time = datetime.now()
        UserRepository.update_api_key("user-123", "new-key", new_time, "node-2")
        
        updated_user = UserRepository.get_by_user_id("user-123")
        assert updated_user is not None
        assert updated_user.api_key == "new-key"
        assert updated_user.version == 2

    def test_user_with_null_fields(self, test_db):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO users 
                   (user_id, username, password_hash, api_key, created_at, key_updated_at, 
                    vector_clock, last_modified_by, version)
                   VALUES (?, ?, ?, NULL, ?, NULL, NULL, NULL, NULL)""",
                ("user-null", "nulluser", "hash123", datetime.now().isoformat())
            )
            conn.commit()
        
        user = UserRepository.get_by_username("nulluser")
        assert user is not None
        assert user.api_key is None
        assert user.key_updated_at is None
        assert user.vector_clock is None
        assert user.last_modified_by is None
        assert user.version == 0

    def test_merge_user_new(self, test_db):
        user = User(
            user_id="user-123",
            username="testuser",
            password_hash="hash123",
            api_key="key123",
            created_at=datetime.now(),
            key_updated_at=None,
            vector_clock=VectorClock({"node-1": 1}),
            last_modified_by="node-1",
            version=1
        )
        
        result = UserRepository.merge_user(user)
        assert result is True
        
        fetched = UserRepository.get_by_user_id("user-123")
        assert fetched is not None
        assert fetched.username == "testuser"

    def test_merge_user_conflict_resolution(self, test_db):
        original = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash123",
            api_key="key1",
            created_at=datetime.now(),
            node_id="node-1"
        )
        
        updated_user = User(
            user_id="user-123",
            username="testuser",
            password_hash="hash456",
            api_key="key2",
            created_at=original.created_at,
            key_updated_at=datetime.now(),
            vector_clock=VectorClock({"node-2": 2}),
            last_modified_by="node-2",
            version=2
        )
        
        result = UserRepository.merge_user(updated_user)
        assert result is True
        
        fetched = UserRepository.get_by_user_id("user-123")
        assert fetched is not None
        assert fetched.version >= 2


class TestFileRepository:
    """Test FileRepository with various scenarios."""

    def test_create_file(self, test_db):
        user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash",
            api_key="key",
            created_at=datetime.now()
        )
        
        file = FileRepository.create_file(
            file_id="file-123",
            name="test.txt",
            size=1024,
            owner_id=user.user_id,
            created_at=datetime.now(),
            node_id="node-1"
        )
        
        assert file.file_id == "file-123"
        assert file.name == "test.txt"
        assert file.size == 1024
        assert file.deleted is False

    def test_get_by_file_id_existing(self, test_db):
        user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash",
            api_key="key",
            created_at=datetime.now()
        )
        
        created_file = FileRepository.create_file(
            file_id="file-123",
            name="test.txt",
            size=1024,
            owner_id=user.user_id,
            created_at=datetime.now()
        )
        
        fetched_file = FileRepository.get_by_file_id("file-123")
        assert fetched_file is not None
        assert fetched_file.file_id == created_file.file_id
        assert fetched_file.name == created_file.name

    def test_get_by_file_id_nonexistent(self, test_db):
        file = FileRepository.get_by_file_id("nonexistent")
        assert file is None

    def test_list_files_by_owner(self, test_db):
        user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash",
            api_key="key",
            created_at=datetime.now()
        )
        
        FileRepository.create_file(
            file_id="file-1",
            name="test1.txt",
            size=1024,
            owner_id=user.user_id,
            created_at=datetime.now()
        )
        FileRepository.create_file(
            file_id="file-2",
            name="test2.txt",
            size=2048,
            owner_id=user.user_id,
            created_at=datetime.now()
        )
        
        files = FileRepository.list_files_by_owner(user.user_id)
        assert len(files) == 2
        assert all(isinstance(f, File) for f in files)

    def test_mark_deleted(self, test_db):
        user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash",
            api_key="key",
            created_at=datetime.now()
        )
        
        file = FileRepository.create_file(
            file_id="file-123",
            name="test.txt",
            size=1024,
            owner_id=user.user_id,
            created_at=datetime.now()
        )
        
        FileRepository.mark_deleted(file.file_id, "node-1")
        
        fetched = FileRepository.get_by_file_id(file.file_id)
        assert fetched is not None
        assert fetched.deleted is True


class TestChunkRepository:
    """Test ChunkRepository with various scenarios."""

    def test_create_chunk(self, test_db):
        user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash",
            api_key="key",
            created_at=datetime.now()
        )
        
        file = FileRepository.create_file(
            file_id="file-123",
            name="test.txt",
            size=1024,
            owner_id=user.user_id,
            created_at=datetime.now()
        )
        
        chunk = Chunk(
            chunk_id="chunk-123",
            file_id=file.file_id,
            chunk_index=0,
            size=512,
            checksum="abc123"
        )
        ChunkRepository.create_chunks([chunk])
        
        fetched = ChunkRepository.get_chunks_by_file(file.file_id)
        assert len(fetched) == 1
        assert fetched[0].chunk_id == "chunk-123"
        assert fetched[0].chunk_index == 0
        assert fetched[0].size == 512

    def test_get_chunks_for_file(self, test_db):
        user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash",
            api_key="key",
            created_at=datetime.now()
        )
        
        file = FileRepository.create_file(
            file_id="file-123",
            name="test.txt",
            size=2048,
            owner_id=user.user_id,
            created_at=datetime.now()
        )
        
        chunks = [
            Chunk(
                chunk_id="chunk-1",
                file_id=file.file_id,
                chunk_index=0,
                size=1024,
                checksum="abc1"
            ),
            Chunk(
                chunk_id="chunk-2",
                file_id=file.file_id,
                chunk_index=1,
                size=1024,
                checksum="abc2"
            )
        ]
        ChunkRepository.create_chunks(chunks)
        
        fetched_chunks = ChunkRepository.get_chunks_by_file(file.file_id)
        assert len(fetched_chunks) == 2
        assert all(isinstance(c, Chunk) for c in fetched_chunks)
        assert fetched_chunks[0].chunk_index == 0
        assert fetched_chunks[1].chunk_index == 1


class TestTagRepository:
    """Test TagRepository with various scenarios."""

    def test_add_tags(self, test_db):
        user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash",
            api_key="key",
            created_at=datetime.now()
        )
        
        file = FileRepository.create_file(
            file_id="file-123",
            name="test.txt",
            size=1024,
            owner_id=user.user_id,
            created_at=datetime.now()
        )
        
        TagRepository.add_tags(file.file_id, ["tag1", "tag2", "tag3"])
        
        tags = TagRepository.get_tags(file.file_id)
        assert set(tags) == {"tag1", "tag2", "tag3"}

    def test_remove_tag(self, test_db):
        user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash",
            api_key="key",
            created_at=datetime.now()
        )
        
        file = FileRepository.create_file(
            file_id="file-123",
            name="test.txt",
            size=1024,
            owner_id=user.user_id,
            created_at=datetime.now()
        )
        
        TagRepository.add_tags(file.file_id, ["tag1", "tag2"])
        TagRepository.remove_tag(file.file_id, "tag1")
        
        tags = TagRepository.get_tags(file.file_id)
        assert tags == ["tag2"]

    def test_clear_tags(self, test_db):
        user = UserRepository.create_user(
            user_id="user-123",
            username="testuser",
            password_hash="hash",
            api_key="key",
            created_at=datetime.now()
        )
        
        file = FileRepository.create_file(
            file_id="file-123",
            name="test.txt",
            size=1024,
            owner_id=user.user_id,
            created_at=datetime.now()
        )
        
        TagRepository.add_tags(file.file_id, ["tag1", "tag2"])
        TagRepository.clear_tags(file.file_id)
        
        tags = TagRepository.get_tags(file.file_id)
        assert tags == []
