## Project Overview

RedCloud Files is a tag-based distributed file system written in Python. Files are organized by tags (not folders) with distributed chunk storage. The system uses a three-tier architecture:

1. **CLI** - Interactive REPL client (prompt_toolkit)
2. **Controller** - FastAPI metadata service with SQLite
3. **Chunkserver** - gRPC storage service

**Current Architecture State**: The system is currently **centralized**, not truly distributed. While multiple chunkserver containers can be run, the controller connects to a single `chunkserver:50051` endpoint. Docker DNS may load-balance, but there's no intentional chunk distribution, replication, or fault tolerance.

## Development Commands

### Running Locally (Development)

```bash
# Install dependencies
pip install -r requirements.txt

# Run controller
python -m controller.main

# Run chunkserver (separate terminal)
python -m chunkserver.main

# Run CLI (separate terminal)
python -m cli.main
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_cli.py

# Run specific test function
pytest tests/test_cli.py::test_parse_add_command -v

# Run integration tests only
pytest tests/integration/

# Run with async debugging
pytest -v -s tests/test_controller_endpoints.py
```

### Docker Deployment

```bash
# Build images
cd docker/scripts
./build-images.sh

# Initialize swarm network
./init-network.sh

# Start services
./run-controller.sh
./run-chunkserver.sh

# Scale chunkservers (creates multiple containers, but NOT distributed storage)
./scale-chunkserver.sh 3

# Run CLI (from directory with files to upload)
cd /path/to/files
./docker/scripts/run-cli.sh

# View logs
./logs.sh [controller|chunkserver]

# Stop all
./stop-all.sh

# Full cleanup
./cleanup.sh
```

## Architecture Deep Dive

### Data Flow: File Upload

1. CLI sends multipart form to `POST /files` with file + tags
2. Controller splits file into 4MB chunks with SHA-256 checksums
3. Controller streams each chunk to chunkserver via gRPC `WriteChunk` (client-streaming)
4. Chunkserver validates checksum and persists to disk
5. Controller stores metadata in SQLite (file, tags, chunks tables)
6. On failure, controller calls `DeleteChunk` RPC to cleanup orphaned chunks
7. If file with same name exists, old file is "replaced" (old chunks deleted asynchronously)

**Critical**: All chunk operations happen within a try-except that triggers cleanup on failure. See `controller/services/file_service.py:upload_file()`.

### Data Flow: File Download

1. CLI sends `GET /files/{file_id}/download` or `GET /files/by-name/{filename}/download`
2. Controller queries SQLite for chunks ordered by `chunk_index`
3. Controller calls `ReadChunk` RPC for each chunk (server-streaming)
4. Chunkserver streams chunk data in 64KB pieces
5. Controller yields chunks directly to HTTP StreamingResponse
6. CLI writes to file with progress tracking

### Data Flow: Tag Query

Tag queries use **AND logic** (files must have ALL tags):

1. CLI sends `GET /files?tags=tag1,tag2`
2. Controller uses SQL intersection query via `tag_repository.py`
3. Returns all files owned by user that have ALL specified tags

### Communication Protocols

**Controller ↔ Chunkserver (gRPC)**:
- `WriteChunk(stream ChunkMetadata, ChunkDataPiece) → WriteChunkResponse`
- `ReadChunk(chunk_id) → stream ChunkDataPiece`
- `DeleteChunk(chunk_id) → DeleteChunkResponse`
- `Ping() → PingResponse`

All messages use JSON serialization with base64-encoded binary data (see `common/protocol.py`).

**CLI ↔ Controller (HTTP)**:
- Auth: `POST /auth/register`, `POST /auth/login` → API key
- Files: `POST /files`, `GET /files`, `DELETE /files`
- Tags: `POST /files/tags`, `DELETE /files/tags`
- Downloads: `GET /files/{file_id}/download`, `GET /files/by-name/{filename}/download`

All file endpoints require `Authorization: Bearer <api_key>` header.

### Database Schema

SQLite with foreign key constraints:

```sql
users(user_id PK, username UNIQUE, password_hash, api_key UNIQUE, created_at, key_updated_at)
files(file_id PK, name, size, owner_id FK → users, created_at)
tags(file_id FK → files, tag, PRIMARY KEY(file_id, tag)) -- CASCADE DELETE
chunks(chunk_id PK, file_id FK → files, chunk_index, size, checksum, UNIQUE(file_id, chunk_index)) -- CASCADE DELETE
```

When a file is deleted, CASCADE DELETE removes associated tags and chunks automatically. The controller then sends `DeleteChunk` RPCs to clean up physical storage.

### Important Constants (`common/constants.py`)

- `CHUNK_SIZE_BYTES = 4MB` - File split threshold
- `STREAM_PIECE_SIZE_BYTES = 64KB` - gRPC streaming piece size
- `CHUNKSERVER_SERVICE_NAME = "chunkserver"` - Docker DNS alias
- `CONTROLLER_SERVICE_NAME = "controller"` - Docker DNS alias
- `CHUNKSERVER_TIMEOUT_SECONDS = 60` - RPC timeout

### Chunkserver Storage

Chunkserver uses two components:

1. **ChunkStorage** (`chunk_storage.py`) - Physical file I/O to disk
2. **ChunkIndex** (`chunk_index.py`) - In-memory index with JSON persistence

Chunks are stored as individual files named by `chunk_id` UUID. The index tracks metadata and can be rebuilt from disk by scanning all chunk files and validating checksums.

### Authentication Flow

1. User registers: `POST /auth/register {username, password}` → API key
2. API key format: `dfs_<uuid>` (see `controller/auth.py`)
3. API key stored in SQLite `users.api_key` column
4. On login, new API key generated (old one invalidated)
5. CLI stores API key in `~/.redcloud/config.json`
6. All requests include `Authorization: Bearer <api_key>` header
7. Controller validates via `auth_service.validate_api_key()` dependency

### File Versioning (Replacement)

When uploading a file with same name:
1. Controller finds existing file via `file_repo.find_by_owner_and_name()`
2. Stores old `file_id` as `replaced_file_id` in response
3. Deletes old file from database (CASCADE removes tags/chunks metadata)
4. Creates new file with new UUID
5. Asynchronously deletes old physical chunks via `_cleanup_chunks()`

This provides implicit versioning without explicit version tracking.

### Background Cleanup Task

Controller runs periodic cleanup task (`cleanup_task.py`) every 6 hours:
- Tracks orphaned chunks in `orphaned_chunks.json` log
- Retries failed deletions with exponential backoff
- Prevents storage leaks from upload failures

## Code Organization Patterns

### Repository Pattern

All database access goes through repositories:
- `file_repository.py` - File CRUD
- `user_repository.py` - User CRUD
- `tag_repository.py` - Tag associations
- `chunk_repository.py` - Chunk metadata

Repositories accept optional `conn` parameter for transaction support. Always use transactions for multi-table operations.

### Service Layer

Business logic in service classes:
- `auth_service.py` - User registration, login, API key validation
- `file_service.py` - File upload/download orchestration
- `tag_service.py` - Tag queries and management

Services instantiate repositories and chunkserver client. They handle cross-cutting concerns like cleanup on failure.

### Error Handling

Custom exceptions in `controller/exceptions.py`:
- `FileNotFoundError` - File or chunk not found
- `UnauthorizedAccessError` - Invalid API key or wrong owner
- `ChunkserverUnavailableError` - Chunkserver connectivity issues
- `ChecksumMismatchError` - Chunk corruption detected
- `StorageFullError` - Disk space exhausted
- `EmptyTagListError` - Tag validation failure

FastAPI exception handlers in `controller/main.py` convert these to appropriate HTTP responses.

### Async/Await Conventions

- All FastAPI endpoints are `async def`
- Repository methods are synchronous (SQLite is blocking)
- Chunkserver client methods are `async` (gRPC is async)
- Service methods are `async` when they call chunkserver
- Use `async for` when consuming gRPC streams

## Testing Patterns

### Fixtures (`tests/conftest.py`)

- `temp_config_dir` - Temporary `.redcloud` directory
- `temp_config` - Config instance with temp file
- `sample_file` - Single test file
- `multiple_sample_files` - Three test files

### Test Organization

- `test_cli.py` - CLI parsing and validation
- `test_cli_commands.py` - Command handler logic
- `test_controller_endpoints.py` - FastAPI endpoint tests
- `test_controller.py` - Service layer unit tests
- `test_chunkserver.py` - Chunkserver storage tests
- `tests/integration/` - Full system tests

### Running Integration Tests

Integration tests require running services:

```bash
# Terminal 1
python -m controller.main

# Terminal 2
python -m chunkserver.main

# Terminal 3
pytest tests/integration/
```

Or use Docker:

```bash
cd docker/scripts
./run-controller.sh
./run-chunkserver.sh
pytest tests/integration/
```

## CLI Command Format

All CLI commands follow these rules:

**Upload files** - Prefix with `uploads/`:
```
add uploads/file1.txt uploads/file2.py [tag1] [tag2]
```

**Download files** - Output to `downloads/` (optional explicit path):
```
download file_id
download filename downloads/subfolder/output.txt
```

**Tag queries** - AND logic (all tags required):
```
list [tag1] [tag2]
delete [tag1] [tag2]
add-tags [query_tag1] [query_tag2] [new_tag1] [new_tag2]
delete-tags [query_tag1] [query_tag2] [remove_tag1]
```

## Docker Networking

Services use Docker overlay network with DNS aliases:
- `controller` → Controller container(s)
- `chunkserver` → Chunkserver container(s)

Docker DNS provides round-robin load balancing for multiple containers with same alias. However, this is **NOT** true distributed storage:
- No chunk placement strategy
- No replication
- No failure recovery
- Random chunk distribution via DNS round-robin

## Configuration

### Environment Variables

**Controller**:
- `DFS_DATABASE_PATH` - SQLite file path (default: `/app/data/metadata.db`)
- `DFS_CONTROLLER_HOST` - Bind address (default: `0.0.0.0`)
- `DFS_CONTROLLER_PORT` - HTTP port (default: `8000`)

**Chunkserver**:
- `CHUNK_STORAGE_PATH` - Chunk directory (default: `/app/data/chunks`)
- `CHUNK_INDEX_PATH` - Index JSON file (default: `/app/data/chunk_index.json`)

**CLI**:
- `DFS_CONTROLLER_HOST` - Hostname only (default: `controller`)
- `DFS_CONTROLLER_PORT` - Port only (default: `8000`)

### Config Files

CLI stores user config in `~/.redcloud/config.json`:
```json
{
  "controller_host": "controller",
  "controller_port": 8000,
  "api_key": "dfs_<uuid>",
  "username": "user"
}
```

## Important Implementation Notes

### Chunk Checksums

Every chunk has SHA-256 checksum:
1. Controller calculates before sending to chunkserver
2. Chunkserver validates incrementally during streaming upload
3. Mismatch triggers `ChecksumMismatchError`
4. Controller cleanup triggered on checksum failure

### Transaction Boundaries

Database transactions must wrap multi-table operations:

```python
with get_db_connection() as conn:
    try:
        self.file_repo.create_file(..., conn=conn)
        self.tag_repo.add_tags(..., conn=conn)
        self.chunk_repo.create_chunks(..., conn=conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

### Streaming Best Practices

gRPC streaming cannot use retry logic (stream is consumed once):

```python
async def read_chunk(self, chunk_id: str) -> AsyncIterator[bytes]:
    # No retry wrapper - stream must succeed or fail
    async for piece in self._read_chunk_internal(chunk_id):
        yield piece
```

Only unary RPCs (WriteChunk, DeleteChunk) use retry with exponential backoff.

### Path Security

CLI enforces mandatory path prefixes:
- Uploads must start with `uploads/`
- Downloads must start with `downloads/` (if explicit path given)

This prevents directory traversal when running in Docker containers with volume mounts.

## Common Development Tasks

### Adding New RPC Method

1. Define request/response dataclasses in `common/protocol.py`
2. Add method to `ChunkserverClient` in `controller/chunkserver_client.py`
3. Implement in `ChunkserverServicer` in `chunkserver/grpc_server.py`
4. Update `ChunkserverService` RPC list

### Adding New API Endpoint

1. Define Pydantic schemas in `controller/schemas/`
2. Add endpoint to appropriate route file in `controller/routes/`
3. Implement business logic in `controller/services/`
4. Add repository methods if needed in `controller/repositories/`
5. Add exception handler in `controller/main.py` if using custom exception
6. Add tests in `tests/test_controller_endpoints.py`

### Adding New CLI Command

1. Add command keyword to `cli/constants.py:COMMANDS`
2. Add parser logic in `cli/parser.py`
3. Define command dataclass in `cli/models.py`
4. Implement handler in `cli/commands.py`
5. Add help text to `cli/constants.py:HELP_TEXT`
6. Add controller client method in `cli/controller_client.py` if needed
7. Add tests in `tests/test_cli.py` and `tests/test_cli_commands.py`

### Database Schema Migration

No migration framework - modify `controller/database.py:init_database()`:
1. Add new table or column in CREATE statements
2. Add indexes if needed
3. Database recreated on controller restart (ephemeral containers)
4. For persistent deployments, manually migrate SQLite file

## Known Limitations

- **Not truly distributed**: Single chunkserver endpoint, no chunk placement strategy
- **No replication**: Each chunk exists on one node only (random via DNS)
- **No fault tolerance**: Chunkserver failure = data loss for its chunks
- **Centralized metadata**: Single SQLite database (not distributed)
- **No encryption**: Data in transit and at rest unencrypted
- **No compression**: Chunks stored as-is
- **AND-only queries**: Tag queries require all tags (no OR/NOT)
- **Owner-only access**: No sharing or permissions system
- **No chunk coordination**: Controller doesn't track which chunkserver has which chunk
