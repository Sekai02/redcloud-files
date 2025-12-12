# Manual Deployment Guide for RedCloud Files

Based on the Docker configuration, here's a complete step-by-step guide to manually deploy the distributed file system without using the provided scripts:

## Prerequisites
- Docker Engine 20.10 or higher installed
- Terminal/Command Prompt with administrative privileges

---

## Step 1: Initialize Docker Swarm

First, enable Docker Swarm mode on your machine:

```bash
docker swarm init
```

If successful, you'll see output with worker/manager join tokens. Keep these for adding additional nodes later.

**Note:** If Docker Swarm is already active, skip this step.

---

## Step 2: Create Overlay Network

Create the Docker overlay network that all services will use to communicate:

```bash
docker network create --driver overlay --attachable dfs-network
```

This creates an isolated network named `dfs-network` where all containers can discover each other using DNS aliases.

---

## Step 3: Build Docker Images

Navigate to the project root directory and build each Docker image:

### Build Controller Image:
```bash
docker build -f docker/Dockerfile.controller -t redcloud-controller:latest .
```

### Build Chunkserver Image:
```bash
docker build -f docker/Dockerfile.chunkserver -t redcloud-chunkserver:latest .
```

### Build CLI Image:
```bash
docker build -f docker/Dockerfile.cli -t redcloud-cli:latest .
```

**Verify images were created:**
```bash
docker images | findstr redcloud
```

---

## Step 4: Start the Controller

Launch the controller container (metadata service):

```bash
docker run -d --network dfs-network --network-alias controller redcloud-controller:latest
```

**What this does:**
- `-d`: Runs in detached mode (background)
- `--network dfs-network`: Connects to the overlay network
- `--network-alias controller`: Sets DNS alias as "controller"
- The controller will be accessible at `http://controller:8000` within the network

**Optional - Get the container ID:**
```bash
docker ps --filter ancestor=redcloud-controller:latest
```

---

## Step 5: Start Chunkserver(s)

Launch one or more chunkserver containers (storage service):

### Single Chunkserver:
```bash
docker run -d --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
```

### Multiple Chunkservers (for load balancing):
Run the command multiple times:
```bash
docker run -d --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
docker run -d --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
docker run -d --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
```

Docker's DNS will automatically round-robin load balance requests to `chunkserver:50051` across all containers with that alias.

---

## Step 6: Launch the CLI

The CLI requires volume mounts to access files on your host machine for uploads and downloads.

### Linux / macOS

Navigate to the directory containing files you want to upload:

```bash
cd /path/to/your/files
chmod 777 .
mkdir -p downloads
chmod 777 downloads

docker run -it --rm \
    --network dfs-network \
    -v "$(pwd):/uploads" \
    -v "$(pwd)/downloads:/downloads" \
    -w /uploads \
    redcloud-cli:latest
```

### Windows PowerShell

Navigate to the directory containing files you want to upload:

```powershell
cd C:\path\to\your\files
if (-not (Test-Path "downloads")) { New-Item -ItemType Directory -Path "downloads" }

docker run -it --rm `
    --network dfs-network `
    -v "${PWD}:/uploads" `
    -v "${PWD}/downloads:/downloads" `
    -w /uploads `
    redcloud-cli:latest
```

### Windows Command Prompt

Navigate to the directory containing files you want to upload:

```cmd
cd C:\path\to\your\files
if not exist downloads mkdir downloads

docker run -it --rm ^
    --network dfs-network ^
    -v "%cd%:/uploads" ^
    -v "%cd%/downloads:/downloads" ^
    -w /uploads ^
    redcloud-cli:latest
```

### Volume Mounts Explained

- **`/uploads`**: Your current directory is mounted here. Upload paths can use `uploads/` prefix, be relative (auto-resolved to `/uploads`), or be absolute paths within this directory.
- **`/downloads`**: Downloaded files are saved here automatically (maps to `./downloads` on your host). Download paths can use `downloads/` prefix, be relative (auto-resolved to `/downloads`), or be absolute paths.
- **`-w /uploads`**: Sets the working directory inside the container.

### Usage Examples

Once the CLI is running:

**Upload files:**
```
add requirements.txt [dependencies, code]
add uploads/README.md uploads/.gitignore [docs]
add chunkserver/main.py [python, server]
```

**Download files:**
```
download requirements.txt
download requirements.txt subfolder/
download requirements.txt downloads/subfolder/renamed.txt
```
Files are automatically saved to the `downloads/` directory on your host.

### Important Notes

- **Upload paths** can use `uploads/` prefix, be relative (resolved to `/uploads`), or be absolute paths within `/uploads`
- **Download paths** can use `downloads/` prefix, be relative (resolved to `/downloads`), or be absolute paths within `/downloads` or `/uploads`
- **File paths are relative** to their respective directories (`/uploads` for uploads, `/downloads` for downloads)
- Navigate to your files directory **before** starting the CLI container
- Downloads default to `/downloads/{filename}` when no output path is specified
- The container working directory is `/uploads`, so relative upload paths work naturally
- **Path validation** prevents directory traversal attacks (e.g., `../../../etc/passwd`) and restricts file access to `/uploads` and `/downloads` directories only
- **Wrong prefix errors**: Using `downloads/` in upload commands or `uploads/` in download commands will return a helpful error message
- **Security boundary**: Absolute paths outside `/uploads` and `/downloads` directories are blocked for security reasons

---

## Verification & Testing

### Check Running Containers:
```bash
docker ps --filter network=dfs-network
```

### Inspect Network:
```bash
docker network inspect dfs-network
```

### Test DNS Resolution:
```bash
docker run --rm --network dfs-network alpine nslookup controller
docker run --rm --network dfs-network alpine nslookup chunkserver
```

### Health Check (from within network):
```bash
docker run --rm --network dfs-network curlimages/curl http://controller:8000/health
```

---

## Multi-Host Deployment (Optional)

To add worker nodes on different machines:

### On Manager Node:
Get the join token:
```bash
docker swarm join-token worker
```

### On Worker Node:
Run the join command (replace with your values):
```bash
docker swarm join --token <TOKEN> <MANAGER-IP>:2377
```

Once joined, you can run chunkserver or CLI containers on any node—they'll automatically connect to the `dfs-network`.

---

## Management Commands

### View Logs:
```bash
# All containers
docker ps --filter network=dfs-network

# Specific container (replace <CONTAINER_ID>)
docker logs <CONTAINER_ID>
docker logs -f <CONTAINER_ID>  # Follow mode
```

### Stop Containers:
```bash
# Stop specific container
docker stop <CONTAINER_ID>

# Stop all RedCloud containers
docker ps --filter network=dfs-network -q | ForEach-Object { docker stop $_ }
```

### Remove Containers:
```bash
docker ps -a --filter network=dfs-network -q | ForEach-Object { docker rm $_ }
```

### Remove Network:
```bash
docker network rm dfs-network
```

### Remove Images:
```bash
docker rmi redcloud-controller:latest redcloud-chunkserver:latest redcloud-cli:latest
```

### Leave Swarm:
```bash
docker swarm leave --force
```

---

## Environment Variables (Optional Customization)

You can override default settings when starting containers:

### Controller:
```bash
docker run -d --network dfs-network --network-alias controller \
  -e DFS_DATABASE_PATH=/app/data/metadata.db \
  -e DFS_CONTROLLER_HOST=0.0.0.0 \
  -e DFS_CONTROLLER_PORT=8000 \
  -e DFS_CHUNKSERVER_ADDRESS=chunkserver:50051 \
  redcloud-controller:latest
```

### Chunkserver:
```bash
docker run -d --network dfs-network --network-alias chunkserver \
  -e CHUNK_STORAGE_PATH=/app/data/chunks \
  -e CHUNK_INDEX_PATH=/app/data/chunk_index.json \
  redcloud-chunkserver:latest
```

### CLI:
```bash
docker run -it --rm --network dfs-network \
  -e DFS_CONTROLLER_URL=http://controller:8000 \
  redcloud-cli:latest
```

---

## Important Notes

- **No External Ports**: All services communicate internally. No ports are published to the host.
- **Ephemeral Storage**: Data is stored in containers and will be lost when containers are removed.
- **DNS-Based Discovery**: Services find each other using Docker DNS (controller, chunkserver aliases).
- **Load Balancing**: Multiple chunkservers automatically load balance through the shared DNS alias.
