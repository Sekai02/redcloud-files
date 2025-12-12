# RedCloud Files - Docker Deployment

Multi-host distributed file system deployment using Docker Swarm overlay networks.

## Architecture

- **Controller**: FastAPI metadata service (internal port 8000)
- **Chunkserver**: gRPC storage service (internal port 50051)
- **CLI**: Interactive client (connects to controller)

All services communicate exclusively via Docker DNS network aliases. No external ports are published.

## Prerequisites

- Docker Engine 20.10+
- Docker Swarm mode enabled

## Quick Start

### 1. Initialize Network (Manager Node)

```bash
cd docker/scripts
chmod +x *.sh
./init-network.sh
```

This creates the `dfs-network` overlay network and initializes Docker Swarm.

### 2. Build Images

```bash
./build-images.sh
```

Builds all three Docker images: `redcloud-controller`, `redcloud-chunkserver`, `redcloud-cli`.

### 3. Start Services

```bash
./run-controller.sh
./run-chunkserver.sh
```

All services are now running on the Docker overlay network.

### 4. Scale Chunkservers

```bash
./scale-chunkserver.sh 3
```

Starts 3 chunkserver containers with automatic load balancing.

### 5. Run CLI

```bash
./run-cli.sh
```

Starts interactive CLI connected to the controller via Docker DNS.

## Multi-Host Deployment

### On Additional Nodes

1. Get the join token from the manager node:

```bash
docker swarm join-token worker
```

2. On worker node, run:

```bash
./join-swarm.sh <manager-ip> <join-token>
```

3. Run containers on any node:

```bash
./run-chunkserver.sh
./run-cli.sh
```

Containers automatically connect to `dfs-network` and discover each other via DNS.

## Management Commands

### View Logs

```bash
./logs.sh
./logs.sh controller
./logs.sh chunkserver
```

### Stop All Containers

```bash
./stop-all.sh
```

### Cleanup Everything

```bash
./cleanup.sh
```

Removes all containers, network, and images.

## Service Discovery

Services use Docker DNS with network aliases:

- **controller** → All controller containers
- **chunkserver** → All chunkserver containers (round-robin load balanced)

No manual IP configuration needed.

## Environment Variables

### Controller

- `DFS_DATABASE_PATH`: SQLite database path (default: `/app/data/metadata.db`)
- `DFS_CONTROLLER_HOST`: Bind address (default: `0.0.0.0`)
- `DFS_CONTROLLER_PORT`: HTTP port (default: `8000`)
- `DFS_CHUNKSERVER_ADDRESS`: Chunkserver gRPC address (default: `chunkserver:50051`)

### Chunkserver

- `CHUNK_STORAGE_PATH`: Chunk storage directory (default: `/app/data/chunks`)
- `CHUNK_INDEX_PATH`: Index file path (default: `/app/data/chunk_index.json`)

### CLI

- `DFS_CONTROLLER_URL`: Controller endpoint (default: `http://controller:8000`)
- `DFS_CONTROLLER_HOST`: Controller hostname (default: `controller`)
- `DFS_CONTROLLER_PORT`: Controller port (default: `8000`)

## Storage

All services use ephemeral container storage. Data is lost when containers stop.

## Health Checks

Controller provides health check endpoints for testing:

```bash
docker run --rm --network dfs-network curlimages/curl http://controller:8000/health
docker run --rm --network dfs-network curlimages/curl http://controller:8000/ready
```

Or test from within CLI container:

```bash
docker exec -it <cli-container-id> python -c "import httpx; print(httpx.get('http://controller:8000/health').json())"
```

- `GET /health` - Returns 200 if controller is alive
- `GET /ready` - Verifies database and chunkserver connectivity

All testing is done from within the Docker network. No external access is available.

## Troubleshooting

### Check running containers

```bash
docker ps --filter network=dfs-network
```

### Check network

```bash
docker network inspect dfs-network
```

### Test DNS resolution

```bash
docker run --rm --network dfs-network alpine nslookup controller
docker run --rm --network dfs-network alpine nslookup chunkserver
```
