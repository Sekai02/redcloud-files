Project Organization (Centralized Design)
==========================================

This document describes the project structure for the centralized tag-based file system implementation.

## Directory Structure

```
project-root/
├── controller/
│   ├── main.py                   # Entry point for Controller container
│   ├── metadata_manager.py       # Manages files, tags, and chunk metadata
│   ├── tag_query_engine.py       # Evaluates tag queries (intersection logic)
│   ├── operation_handler.py      # Handles CLI commands (add, list, delete, etc.)
│   └── chunkserver_client.py     # RPC client to communicate with Chunkserver
│
├── chunkserver/
│   ├── main.py                   # Entry point for Chunkserver container
│   ├── chunk_storage.py          # Manages chunk files on disk
│   ├── chunk_index.py            # In-memory index: chunk_id -> ChunkRecord
│   └── checksum_validator.py    # SHA-256 checksum verification
│
├── cli/
│   ├── main.py                   # Entry point for CLI client
│   ├── commands.py               # Command parsing (add, list, delete, etc.)
│   └── controller_client.py      # TCP client to communicate with Controller
│
├── common/
│   ├── protocol.py               # Shared RPC/protocol definitions
│   ├── types.py                  # Shared data types (FileMeta, ChunkDescriptor, etc.)
│   └── constants.py              # Shared constants (CHUNK_SIZE = 64 MiB, etc.)
│
├── docker/
│   ├── Dockerfile.controller     # Dockerfile for Controller
│   ├── Dockerfile.chunkserver    # Dockerfile for Chunkserver
│   └── docker-compose.yml        # Docker Compose setup for local testing
│
├── tests/
│   ├── test_controller.py
│   ├── test_chunkserver.py
│   ├── test_cli.py
│   └── integration/
│       └── test_full_flow.py     # End-to-end tests
│
├── docs/
│   └── (this centralized/ folder)
│
└── README.md
```

## Component Responsibilities

### Controller (`controller/`)
- Maintains all metadata (files, tags, chunks)
- Evaluates tag queries
- Coordinates add/delete/list operations
- Communicates with Chunkserver via RPC

### Chunkserver (`chunkserver/`)
- Stores chunk files on disk (`/data/chunks/`)
- Maintains local chunk index
- Verifies checksums on read and write
- Serves chunk read/write requests from Controller

### CLI (`cli/`)
- User-facing command-line interface
- Parses user commands
- Sends requests to Controller
- Displays results

### Common (`common/`)
- Shared protocol definitions
- Shared data types
- Constants (chunk size, network ports, etc.)

## Key Files

- `controller/metadata_manager.py`: Core metadata logic
  - `files: Map<file_id, FileMeta>`
  - `tagIndex: Map<tag, Set<file_id>>`

- `chunkserver/chunk_storage.py`: Chunk file management
  - `chunkIndex: Map<chunk_id, ChunkRecord>`
  - Disk I/O for `/data/chunks/<chunk_id>.chk`

- `common/types.py`: Data models
  - `FileMeta`
  - `ChunkDescriptor`
  - `ChunkRecord`

## Deployment

- **Controller**: Single container on Docker Swarm overlay network
- **Chunkserver**: Single container on same overlay network
- **CLI**: Runs on external machines, connects via host IP

See `CENTRALIZED_SYSTEM_DESIGN.md` for architectural details.
