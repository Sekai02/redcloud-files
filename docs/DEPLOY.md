# RedCloud Files - Manual Deployment

## 1. Initialize Docker Swarm

```bash
docker swarm init
```

Get join token for additional manager nodes:

```bash
docker swarm join-token manager
```

## 2. Create Network

```bash
docker network create --driver overlay --attachable dfs-network
```

## 3. Build Images

```bash
docker build -f docker/Dockerfile.controller -t redcloud-controller:latest .
docker build -f docker/Dockerfile.chunkserver -t redcloud-chunkserver:latest .
docker build -f docker/Dockerfile.cli -t redcloud-cli:latest .
```

## 4. Run Controllers

```bash
docker run -d --name controller-1 --network dfs-network --network-alias controller redcloud-controller:latest
```

Repeat on other hosts with different `--name` values. The `--network-alias controller` is mandatory.

## 5. Run Chunkservers

```bash
docker run -d --name chunkserver-1 --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
```

Repeat on other hosts with different `--name` values. The `--network-alias chunkserver` is mandatory.

## 6. Run CLI

Navigate to your files directory first, then:

```bash
docker run -it --rm \
    --network dfs-network \
    -v "$(pwd):/uploads" \
    -v "$(pwd)/downloads:/downloads" \
    -w /uploads \
    redcloud-cli:latest
```

Upload files using `uploads/` prefix. Downloads save to `downloads/` directory.

## 7. View Logs

```bash
docker logs -f <container-id>
```
