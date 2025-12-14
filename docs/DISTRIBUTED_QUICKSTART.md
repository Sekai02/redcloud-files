# Quick Start Guide - Distributed RedCloud

## 🚀 Deploy Distributed System (3 Controllers + 5 Chunkservers)

### 1. Initialize Docker Swarm
```bash
docker swarm init
```

### 2. Create Network
```bash
docker network create --driver overlay --attachable dfs-network
```

### 3. Build Images (if needed)
```bash
cd docker/scripts
./build-images.sh
```

### 4. Deploy 3 Controllers
```bash
# Controller 1
docker run -d --name controller-1 --network dfs-network --network-alias controller redcloud-controller:latest

# Controller 2
docker run -d --name controller-2 --network dfs-network --network-alias controller redcloud-controller:latest

# Controller 3
docker run -d --name controller-3 --network dfs-network --network-alias controller redcloud-controller:latest
```

**What happens:**
- Each controller auto-generates unique ID: `container-hostname-timestamp`
- Each controller discovers others via DNS + gossip
- Controllers sync metadata via gossip protocol
- Partition tolerant: any controller can serve requests

### 5. Deploy 5 Chunkservers
```bash
# Chunkserver 1
docker run -d --name chunkserver-1 --network dfs-network redcloud-chunkserver:latest

# Chunkserver 2
docker run -d --name chunkserver-2 --network dfs-network redcloud-chunkserver:latest

# Chunkserver 3
docker run -d --name chunkserver-3 --network dfs-network redcloud-chunkserver:latest

# Chunkserver 4
docker run -d --name chunkserver-4 --network dfs-network redcloud-chunkserver:latest

# Chunkserver 5
docker run -d --name chunkserver-5 --network dfs-network redcloud-chunkserver:latest
```

**What happens:**
- Each chunkserver auto-generates unique ID
- Heartbeat registers with any controller (DNS round-robin)
- Gossip propagates registration to all controllers
- All chunks replicate to all chunkservers automatically

### 6. Deploy CLI
```bash
docker run -it --rm \
    --network dfs-network \
    -v "$(pwd):/uploads" \
    -v "$(pwd)/downloads:/downloads" \
    -w /uploads \
    redcloud-cli:latest
```

**What happens:**
- CLI connects to `controller` DNS (any controller)
- Upload: Chunks written to all 5 chunkservers in parallel
- Download: Reads from any available chunkserver with automatic failover
- Metadata changes sync across all controllers via gossip

---

## 🔍 Verify Deployment

### Check Controllers
```bash
# View controller logs
docker logs controller-1 | grep "distributed controller"
docker logs controller-2 | grep "Discovered"
docker logs controller-3 | grep "Gossip"

# Check controller health
curl http://localhost:8000/health  # (if port mapped)
```

### Check Chunkservers
```bash
# View heartbeat logs
docker logs chunkserver-1 | grep "Heartbeat"
docker logs chunkserver-2 | grep "node_id"

# Check storage stats
docker exec chunkserver-1 ls -la /app/data/chunks
```

### Check Gossip Activity
```bash
# Watch gossip synchronization
docker logs -f controller-1 | grep -E "gossip|peer|sync"
```

---

## 🧪 Test Distributed Features

### 1. Test Controller Failover
```bash
# Stop controller-1
docker stop controller-1

# CLI still works (connects to controller-2 or controller-3)
docker run -it --rm --network dfs-network redcloud-cli:latest
> login <username> <password>
> ls

# Restart controller-1 - it syncs state via gossip
docker start controller-1
```

### 2. Test Chunkserver Failover
```bash
# Upload a file
> upload test.txt tag1

# Stop 3 chunkservers
docker stop chunkserver-1 chunkserver-2 chunkserver-3

# Download still works (reads from chunkserver-4 or chunkserver-5)
> download test.txt

# Restart chunkservers - repair service replicates missing chunks
docker start chunkserver-1 chunkserver-2 chunkserver-3
```

### 3. Test Partition Healing
```bash
# Simulate partition: disconnect controller-3
docker network disconnect dfs-network controller-3

# Upload file via controller-1 or controller-2
> upload partition-test.txt tag1

# Reconnect controller-3 - it syncs via anti-entropy
docker network connect dfs-network controller-3

# Wait 30-60 seconds, then check controller-3 logs
docker logs controller-3 | grep "Anti-entropy"
```

### 4. Test Full Replication
```bash
# Upload file
> upload replicated.txt tag1

# Check chunk locations on all servers
docker exec chunkserver-1 ls /app/data/chunks  # Should have chunks
docker exec chunkserver-2 ls /app/data/chunks  # Should have chunks
docker exec chunkserver-3 ls /app/data/chunks  # Should have chunks
docker exec chunkserver-4 ls /app/data/chunks  # Should have chunks
docker exec chunkserver-5 ls /app/data/chunks  # Should have chunks
```

---

## 📊 Monitoring

### Controller Metrics
```bash
# Peer count
docker logs controller-1 | grep "Discovered.*peers"

# Gossip activity
docker logs controller-1 | grep "Sent.*updates"

# Conflict resolution
docker logs controller-1 | grep "Resolved conflict"
```

### Chunkserver Metrics
```bash
# Heartbeat status
docker logs chunkserver-1 | grep "Heartbeat sent"

# Replication activity
docker logs chunkserver-1 | grep "Successfully replicated"

# Health status
docker logs controller-1 | grep "Chunkserver.*failed"
```

### Repair Service
```bash
# Watch repair cycles
docker logs -f controller-1 | grep "Repair cycle complete"

# Check replication progress
docker logs controller-1 | grep "replications successful"
```

---

## 🛠️ Configuration (Optional)

### Custom Node IDs
```bash
docker run -d \
    -e CONTROLLER_NODE_ID=my-controller-1 \
    --network dfs-network \
    --network-alias controller \
    redcloud-controller:latest
```

### Custom Timeouts
```bash
docker run -d \
    -e HEARTBEAT_TIMEOUT=60 \
    -e REPAIR_INTERVAL=120 \
    --network dfs-network \
    --network-alias controller \
    redcloud-controller:latest
```

### Persistent Storage (Optional)
```bash
docker run -d \
    -v controller-data:/app/data \
    --network dfs-network \
    --network-alias controller \
    redcloud-controller:latest
```

---

## 🐛 Troubleshooting

### Controllers Not Discovering Each Other
```bash
# Check DNS resolution
docker exec controller-1 nslookup controller

# Check peer registry
docker logs controller-1 | grep "discover"

# Verify network
docker network inspect dfs-network
```

### Chunkservers Not Registering
```bash
# Check heartbeat
docker logs chunkserver-1 | grep -i heartbeat

# Check controller received heartbeat
docker logs controller-1 | grep "Received heartbeat"

# Verify network connectivity
docker exec chunkserver-1 ping controller
```

### Chunks Not Replicating
```bash
# Check repair service
docker logs controller-1 | grep "Repair"

# Check chunk locations
docker exec controller-1 sqlite3 /app/data/controller-*/redcloud.db \
    "SELECT COUNT(*) FROM chunk_locations"

# Verify chunkservers are healthy
docker logs controller-1 | grep "healthy.*chunkserver"
```

### Gossip Not Working
```bash
# Check gossip service started
docker logs controller-1 | grep "Gossip service started"

# Check peer connectivity
docker logs controller-1 | grep "Failed to gossip"

# Verify anti-entropy
docker logs controller-1 | grep "Anti-entropy"
```

---

## 📖 Key Concepts

### Auto-Configuration
- **Node IDs**: Auto-generated from `hostname-timestamp`
- **IP Detection**: Uses routing table to find correct interface
- **Peer Discovery**: DNS queries + gossip propagation
- **No Config Files**: Everything auto-detected

### Replication Strategy
- **Write**: Parallel to all available chunkservers
- **Read**: First available replica with automatic failover
- **Delete**: Parallel from all replicas
- **Repair**: Background service ensures full replication

### Consistency Model
- **AP System**: Available + Partition Tolerant
- **Eventual Consistency**: Changes propagate via gossip
- **Conflict Resolution**: Last-Write-Wins with vector clocks
- **Partition Healing**: Automatic via anti-entropy

---

## 🎯 Production Checklist

- [ ] Deploy ≥3 controllers (quorum for reliability)
- [ ] Deploy ≥3 chunkservers (minimum for redundancy)
- [ ] Use persistent volumes for production data
- [ ] Configure health checks and monitoring
- [ ] Set up log aggregation (ELK, Splunk, etc.)
- [ ] Configure backups for controller databases
- [ ] Test partition scenarios before production
- [ ] Document recovery procedures

---

**Ready to deploy! The system is fully operational and tested.** 🚀
