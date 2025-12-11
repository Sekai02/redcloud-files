# RedCloud Files

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)

**RedCloud Files** is a tag-based file system implementation in Python that organizes and retrieves files using tags instead of traditional hierarchical folders.

## Table of Contents

- [Local Development Setup](#local-development-setup)
- [Running the System](#running-the-system)
- [Using the CLI](#using-the-cli)
- [Troubleshooting](#troubleshooting)

---

## Local Development Setup

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Virtual environment (recommended)

### Installation Steps

1. **Clone the repository**

```bash
git clone https://github.com/Sekai02/redcloud-files.git
cd redcloud-files
```

2. **Create and activate virtual environment**

```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Initialize development environment**

```bash
./bin/setup-dev
```

This creates the necessary data directories:
- `./data/chunks/` - Storage for file chunks (chunkserver)
- `./data/metadata.db` - SQLite database (controller)
- `./data/chunk_index.json` - Chunk metadata index (chunkserver)
- `./data/orphaned_chunks.json` - Cleanup tracking (controller)

---

## Running the System

The system requires three components running simultaneously in separate terminals:

### Terminal 1: Start Chunkserver

```bash
./bin/run-chunkserver
```

Expected output:
```
Starting RedCloud Files Chunkserver...
Port: 50051
Data directory: ./data/chunks/

2025-12-10 19:00:00 - __main__ - INFO - Initializing chunkserver...
2025-12-10 19:00:00 - __main__ - INFO - Starting chunkserver on [::]:50051
```

### Terminal 2: Start Controller

```bash
./bin/run-controller
```

Expected output:
```
Starting RedCloud Files Controller...
Port: 8000
Database: ./data/metadata.db
Hot reload: enabled

INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

### Terminal 3: Run CLI

```bash
./bin/cli
```

Expected output:
```
Welcome to RedCloud Files CLI
Type 'help' for available commands
redcloud>
```

---

## Using the CLI

### Authentication

**Register a new user:**
```
redcloud> register alice password123
✓ Registration successful! Your API Key: dfs_abc123...
```

**Login (get new API Key):**
```
redcloud> login alice password123
✓ Login successful! Your API Key: dfs_xyz789...
```

### File Operations

**Upload a file with tags:**
```
redcloud> add document.pdf report project2025
✓ File uploaded: document.pdf
```

**List files by tags:**
```
redcloud> list report project2025
Files matching tags [report, project2025]:
- document.pdf (1.2 MB)
```

**Download a file:**
```
redcloud> download <file_id>
✓ File downloaded
```

**Delete files by tags:**
```
redcloud> delete report project2025
✓ Deleted 1 file(s)
```

**Add tags to existing files:**
```
redcloud> add-tags report important urgent
✓ Updated 1 file(s)
```

**Remove tags from files:**
```
redcloud> delete-tags report draft
✓ Updated 1 file(s)
```

---

## Troubleshooting

### Port Already in Use

**Error:** `Address already in use` or `OSError: [Errno 48]`

**Solution:**
```bash
lsof -ti:8000 | xargs kill -9
lsof -ti:50051 | xargs kill -9
```

### Chunkserver Connection Failed

**Error:** `Chunkserver unavailable: DNS resolution failed`

**Solution:** Ensure chunkserver is running first, then start controller. Check that constants.py has `CHUNKSERVER_SERVICE_NAME = "localhost"`.

### Permission Denied on Scripts

**Error:** `Permission denied: ./bin/run-chunkserver`

**Solution:**
```bash
chmod +x ./bin/run-chunkserver ./bin/run-controller ./bin/setup-dev
```

### Data Directory Not Found

**Error:** `FileNotFoundError: [Errno 2] No such file or directory: './data/chunks'`

**Solution:** Run setup script:
```bash
./bin/setup-dev
```

### Hot Reload Not Working

The controller runs with `--reload` flag for automatic code reloading during development. If changes aren't reflected:

1. Check terminal for reload messages
2. Manually restart: `Ctrl+C` then `./bin/run-controller`

### Clean Start (Reset All Data)

To wipe all data and start fresh:

```bash
rm -rf ./data/
./bin/setup-dev
```

**Warning:** This deletes all uploaded files, user accounts, and metadata!

### View Logs

All components log to stdout. To save logs to file:

```bash
./bin/run-chunkserver 2>&1 | tee chunkserver.log
./bin/run-controller 2>&1 | tee controller.log
```

---

## Architecture Overview

### Components

- **CLI**: User interface for file operations
- **Controller**: Central coordination server (FastAPI on port 8000)
  - Manages metadata (SQLite database)
  - Handles authentication (API Keys)
  - Coordinates file operations
- **Chunkserver**: Storage server (gRPC on port 50051)
  - Stores file chunks (4MB each)
  - Verifies checksums (SHA-256)
  - Manages chunk index

### Data Flow

**Upload:**
```
CLI → Controller → Split into 4MB chunks → Stream to Chunkserver → Store on disk
```

**Download:**
```
CLI → Controller → Query chunk metadata → Stream from Chunkserver → Reassemble file
```

### File Chunking

- Files split into 4MB fixed-size chunks
- Each chunk stored as separate file in `./data/chunks/`
- Network transmission uses 64KB streaming pieces
- SHA-256 checksums verify data integrity

---

## Development Notes

### Code Structure

```
redcloud-files/
├── bin/                    # Executable scripts
├── chunkserver/           # Storage server implementation
├── controller/            # Central coordination server
│   ├── routes/           # API endpoints
│   ├── services/         # Business logic
│   ├── repositories/     # Database access
│   └── schemas/          # Request/response models
├── cli/                   # Command-line interface
├── common/               # Shared code and constants
├── data/                 # Local development data (gitignored)
└── tests/                # Test suite
```

### Adding New Features

1. Make code changes
2. Controller auto-reloads (thanks to `--reload` flag)
3. Chunkserver requires manual restart
4. CLI requires restart

### Running Tests

```bash
pytest tests/
pytest tests/ --cov=controller --cov=chunkserver
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.