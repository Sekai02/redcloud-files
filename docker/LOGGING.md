# RedCloud Files - Logging Guide

This document describes the logging implementation for debugging and monitoring the RedCloud Files distributed file system.

## Overview

The system now includes comprehensive logging across all three components:
- **Controller**: FastAPI metadata service
- **Chunkserver**: gRPC storage service  
- **CLI**: Interactive client

All logs output to stdout/stderr and can be viewed using Docker's native logging commands.

## Log Levels

Set the log level using the `LOG_LEVEL` environment variable:
- `DEBUG`: Detailed diagnostic information
- `INFO`: General informational messages (default)
- `WARNING`: Warning messages for potentially harmful situations
- `ERROR`: Error messages for serious problems

## Viewing Logs

### Using Docker Commands

**View live logs from all services:**
```bash
docker logs -f <container-id>
```

**View logs from specific service:**
```bash
# Find container ID first
docker ps

# Then view logs
docker logs -f <controller-container-id>
docker logs -f <chunkserver-container-id>
```

### Using Helper Script

The improved `logs.sh` script provides convenient log viewing:

```bash
# Show last 100 lines from all containers
./docker/scripts/logs.sh

# Show last 100 lines from controller
./docker/scripts/logs.sh controller

# Show last 50 lines from controller
./docker/scripts/logs.sh controller 50

# Follow controller logs in real-time
./docker/scripts/logs.sh controller 100 -f

# Follow all logs
./docker/scripts/logs.sh all 200 --follow
```

## Setting Log Levels

### Via Docker Run

When starting containers, override the log level:

```bash
docker run -d \
    --network dfs-network \
    --network-alias controller \
    -e LOG_LEVEL=DEBUG \
    redcloud-controller:latest
```

### Via Dockerfile

Edit the Dockerfile before building:

```dockerfile
ENV LOG_LEVEL=DEBUG
```

### CLI Debug Mode

The CLI supports a `--debug` flag for verbose output:

```bash
# In container
python -m cli.main --debug

# Or from host
docker run -it --rm \
    --network dfs-network \
    -v "$(pwd):/uploads" \
    -v "$(pwd)/downloads:/downloads" \
    -w /uploads \
    redcloud-cli:latest python -m cli.main --debug
```

## What Gets Logged

### Controller
- HTTP request/response details (method, path, status, duration)
- User authentication attempts (register, login, API key validation)
- File operations (upload, download, delete)
- Tag operations (add, remove, query)
- Database transactions
- Exception details with stack traces
- Request correlation IDs for tracing

### Chunkserver
- Chunk write/read/delete operations
- Checksum validation
- Index loading/saving/rebuilding
- gRPC streaming progress
- Storage errors (disk full, file not found)
- Exception details with stack traces

### CLI
- Command execution flow
- HTTP requests to controller
- Retry attempts with backoff delays
- File upload/download progress
- Configuration loading/saving
- Connection errors and timeouts
- API key operations (masked for security)

## Security Features

### Sensitive Data Masking

The logging system automatically masks sensitive information:
- Passwords in log messages
- API keys in headers and messages
- Authorization tokens
- Bearer tokens
- Secret values

Example:
```
# Original: password=mysecretpass123
# Logged:   password=***MASKED***

# Original: Authorization: Bearer dfs_abc123xyz
# Logged:   Authorization: Bearer ***MASKED***
```

## Request Tracing

Each request is assigned a unique correlation ID for tracing across services:

```
Controller log:
2025-12-12 10:30:45 - controller - INFO - Request started: POST /files [request_id=a1b2c3d4] [user_id=user123]

CLI log:
2025-12-12 10:30:45 - cli.controller_client - DEBUG - Making request: POST /files [request_id=a1b2c3d4]
```

## Troubleshooting Common Issues

### No logs appearing

1. Check container is running: `docker ps`
2. Check log level isn't too restrictive
3. Verify stdout isn't being redirected

### Logs too verbose

Set `LOG_LEVEL=WARNING` or `LOG_LEVEL=ERROR` to reduce output:

```bash
docker run -d \
    --network dfs-network \
    -e LOG_LEVEL=WARNING \
    redcloud-controller:latest
```

### Finding specific errors

Use `grep` to filter logs:

```bash
docker logs <container-id> 2>&1 | grep ERROR
docker logs <container-id> 2>&1 | grep "request_id=abc123"
docker logs <container-id> 2>&1 | grep "user_id=user456"
```

### Viewing logs after container stops

Docker retains logs for stopped containers:

```bash
docker logs <stopped-container-id>
```

## Log Format

All logs follow this format:
```
YYYY-MM-DD HH:MM:SS - logger.name - LEVEL - message
```

Example:
```
2025-12-12 10:30:45 - controller.services.auth_service - INFO - Successfully registered user: alice [user_id=123abc]
2025-12-12 10:30:46 - chunkserver.grpc_server - INFO - Chunk written successfully [chunk_id=456def]
2025-12-12 10:30:47 - cli.controller_client - DEBUG - Response received: POST /files status=201 [request_id=789ghi]
```

## Performance Considerations

- `DEBUG` level logging may impact performance in production
- Use `INFO` (default) for normal operation
- Use `WARNING` or `ERROR` for production systems with high load
- Request correlation adds minimal overhead (~5ms per request)

## Examples

### Debug Upload Issues

```bash
# Set CLI to debug mode
docker run -it --rm \
    --network dfs-network \
    -v "$(pwd):/uploads" \
    -v "$(pwd)/downloads:/downloads" \
    -e LOG_LEVEL=DEBUG \
    redcloud-cli:latest

# In another terminal, watch controller logs
./docker/scripts/logs.sh controller 100 -f
```

### Track Specific Request

1. Note the `request_id` from CLI output
2. Search controller logs: `docker logs <controller-id> 2>&1 | grep "request_id=abc123"`
3. Search chunkserver logs: `docker logs <chunkserver-id> 2>&1 | grep "request_id=abc123"`

### Monitor Authentication

```bash
./docker/scripts/logs.sh controller 100 -f | grep -E "register|login|API key"
```

### Watch File Operations

```bash
./docker/scripts/logs.sh all 200 -f | grep -E "upload|download|delete"
```
