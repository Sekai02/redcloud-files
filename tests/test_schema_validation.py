"""Schema validation tests to prevent SQL query mismatches."""

import re
import sqlite3
import tempfile
from pathlib import Path

import pytest

from controller.database import init_database


@pytest.fixture
def test_db():
    """
    Create a temporary test database with schema.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        
        import controller.database
        import controller.config
        original_path = controller.database.DATABASE_PATH
        
        controller.database.DATABASE_PATH = str(db_path)
        controller.config.DATABASE_PATH = str(db_path)
        
        init_database()
        
        yield db_path
        
        controller.database.DATABASE_PATH = original_path
        controller.config.DATABASE_PATH = original_path


def get_table_columns(db_path: Path, table_name: str) -> set:
    """
    Get all column names for a table from the database schema.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    return columns


def extract_columns_from_query(query: str) -> set:
    """
    Extract column names from SELECT queries.
    """
    query_upper = query.upper()
    
    if "SELECT *" in query_upper:
        return {"*"}
    
    select_match = re.search(r"SELECT\s+(.*?)\s+FROM", query_upper, re.DOTALL)
    if not select_match:
        return set()
    
    columns_str = select_match.group(1)
    columns = [col.strip().split()[-1] for col in columns_str.split(",")]
    return {col.lower() for col in columns if col}


class TestUserRepositorySchema:
    """Validate UserRepository SQL queries against schema."""

    def test_users_table_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        result = cursor.fetchone()
        conn.close()
        assert result is not None

    def test_users_table_columns(self, test_db):
        columns = get_table_columns(test_db, "users")
        expected_columns = {
            "user_id",
            "username",
            "password_hash",
            "api_key",
            "created_at",
            "key_updated_at",
            "vector_clock",
            "last_modified_by",
            "version"
        }
        assert columns == expected_columns

    def test_user_repository_select_queries(self, test_db):
        from controller.repositories import user_repository
        import inspect
        
        source = inspect.getsource(user_repository)
        select_queries = re.findall(r'SELECT\s+.*?FROM\s+users', source, re.IGNORECASE | re.DOTALL)
        
        table_columns = get_table_columns(test_db, "users")
        
        for query in select_queries:
            query_columns = extract_columns_from_query(query)
            
            if "*" in query_columns:
                continue
                
            for col in query_columns:
                assert col in table_columns, f"Column {col} not in users table schema"


class TestFileRepositorySchema:
    """Validate FileRepository SQL queries against schema."""

    def test_files_table_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
        result = cursor.fetchone()
        conn.close()
        assert result is not None

    def test_files_table_columns(self, test_db):
        columns = get_table_columns(test_db, "files")
        expected_columns = {
            "file_id",
            "name",
            "size",
            "owner_id",
            "created_at",
            "deleted",
            "vector_clock",
            "last_modified_by",
            "version"
        }
        assert columns == expected_columns

    def test_file_repository_select_queries(self, test_db):
        from controller.repositories import file_repository
        import inspect
        
        source = inspect.getsource(file_repository)
        select_queries = re.findall(r'SELECT\s+.*?FROM\s+files', source, re.IGNORECASE | re.DOTALL)
        
        table_columns = get_table_columns(test_db, "files")
        
        for query in select_queries:
            query_columns = extract_columns_from_query(query)
            
            if "*" in query_columns:
                continue
                
            for col in query_columns:
                assert col in table_columns, f"Column {col} not in files table schema"


class TestChunkRepositorySchema:
    """Validate ChunkRepository SQL queries against schema."""

    def test_chunks_table_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'")
        result = cursor.fetchone()
        conn.close()
        assert result is not None

    def test_chunks_table_columns(self, test_db):
        columns = get_table_columns(test_db, "chunks")
        expected_columns = {
            "chunk_id",
            "file_id",
            "chunk_index",
            "size",
            "checksum",
            "vector_clock",
            "last_modified_by",
            "version"
        }
        assert columns == expected_columns

    def test_chunk_locations_table_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunk_locations'")
        result = cursor.fetchone()
        conn.close()
        assert result is not None


class TestTagRepositorySchema:
    """Validate TagRepository SQL queries against schema."""

    def test_tags_table_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tags'")
        result = cursor.fetchone()
        conn.close()
        assert result is not None

    def test_tags_table_columns(self, test_db):
        columns = get_table_columns(test_db, "tags")
        expected_columns = {"file_id", "tag"}
        assert columns == expected_columns


class TestDatabaseIntegrity:
    """Test database constraints and foreign keys."""

    def test_user_unique_username(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            ("id1", "duplicate", "hash1", "2025-01-01T00:00:00")
        )
        
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("id2", "duplicate", "hash2", "2025-01-01T00:00:00")
            )
        
        conn.close()

    def test_user_unique_api_key(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO users (user_id, username, password_hash, api_key, created_at) VALUES (?, ?, ?, ?, ?)",
            ("id1", "user1", "hash1", "key123", "2025-01-01T00:00:00")
        )
        
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO users (user_id, username, password_hash, api_key, created_at) VALUES (?, ?, ?, ?, ?)",
                ("id2", "user2", "hash2", "key123", "2025-01-01T00:00:00")
            )
        
        conn.close()

    def test_file_foreign_key_constraint(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO files (file_id, name, size, owner_id, created_at) VALUES (?, ?, ?, ?, ?)",
                ("file1", "test.txt", 1024, "nonexistent-user", "2025-01-01T00:00:00")
            )
        
        conn.close()

    def test_chunk_unique_file_index(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            ("user1", "testuser", "hash", "2025-01-01T00:00:00")
        )
        cursor.execute(
            "INSERT INTO files (file_id, name, size, owner_id, created_at) VALUES (?, ?, ?, ?, ?)",
            ("file1", "test.txt", 1024, "user1", "2025-01-01T00:00:00")
        )
        
        cursor.execute(
            "INSERT INTO chunks (chunk_id, file_id, chunk_index, size, checksum) VALUES (?, ?, ?, ?, ?)",
            ("chunk1", "file1", 0, 512, "abc123")
        )
        
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO chunks (chunk_id, file_id, chunk_index, size, checksum) VALUES (?, ?, ?, ?, ?)",
                ("chunk2", "file1", 0, 512, "abc456")
            )
        
        conn.close()

    def test_cascade_delete_file_chunks(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            ("user1", "testuser", "hash", "2025-01-01T00:00:00")
        )
        cursor.execute(
            "INSERT INTO files (file_id, name, size, owner_id, created_at) VALUES (?, ?, ?, ?, ?)",
            ("file1", "test.txt", 1024, "user1", "2025-01-01T00:00:00")
        )
        cursor.execute(
            "INSERT INTO chunks (chunk_id, file_id, chunk_index, size, checksum) VALUES (?, ?, ?, ?, ?)",
            ("chunk1", "file1", 0, 512, "abc123")
        )
        conn.commit()
        
        cursor.execute("DELETE FROM files WHERE file_id = ?", ("file1",))
        conn.commit()
        
        cursor.execute("SELECT * FROM chunks WHERE file_id = ?", ("file1",))
        result = cursor.fetchall()
        
        assert len(result) == 0
        
        conn.close()
