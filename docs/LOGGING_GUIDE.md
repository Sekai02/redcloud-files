# Replication Monitoring and Logging Guide

This guide explains how to monitor and track replication in RedCloud distributed file system using existing logs and database queries.

## Overview

RedCloud tracks replication at two levels:
- **Controller Level**: Metadata replication (files, tags, chunks metadata, users)
- **Chunkserver Level**: Chunk data replication across storage servers

Both use comprehensive structured logging with correlation IDs for distributed tracing.

---

## Controller Level - Metadata Replication Tracking

### Database Tables for Monitoring

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `gossip_log` | Complete audit trail of all replicated changes | `entity_type`, `entity_id`, `operation`, `timestamp`, `gossiped_to`, `vector_clock` |
| `controller_nodes` | Registered controller peers | `node_id`, `address`, `last_seen`, `vector_clock` |
| `files` | File metadata with soft delete support | `file_id`, `name`, `owner_id`, `deleted`, `vector_clock`, `version` |
| `users` | User metadata | `user_id`, `username`, `vector_clock`, `version` |
| `chunks` | Chunk metadata | `chunk_id`, `file_id`, `vector_clock`, `version` |

### SQL Queries for Monitoring

#### Check Gossip Activity

```sql
-- Recent gossip activity (last 100 entries)
SELECT log_id, entity_type, entity_id, operation, timestamp, gossiped_to
FROM gossip_log
ORDER BY log_id DESC
LIMIT 100;

-- Count by entity type and operation
SELECT entity_type, operation, COUNT(*) as count
FROM gossip_log
GROUP BY entity_type, operation;

-- Check if specific file was gossiped
SELECT log_id, operation, timestamp, gossiped_to
FROM gossip_log
WHERE entity_type = 'file' AND entity_id = '<file_id>';

-- Files gossiped in last hour (Unix timestamp)
SELECT entity_id, operation, timestamp
FROM gossip_log
WHERE entity_type = 'file'
  AND timestamp > strftime('%s', 'now', '-1 hour');

-- See which peers received specific update
SELECT log_id, entity_id, gossiped_to
FROM gossip_log
WHERE log_id = <log_id>;
```

#### Verify File Replication Across Controllers

```sql
-- Count total files (excluding soft-deleted)
SELECT COUNT(*) as file_count
FROM files
WHERE deleted = 0;

-- List all files with details
SELECT file_id, name, owner_id, created_at, version
FROM files
WHERE deleted = 0
ORDER BY created_at DESC;

-- Check specific file exists
SELECT file_id, name, owner_id, deleted, vector_clock, version
FROM files
WHERE file_id = '<file_id>';

-- Files with their tag count
SELECT f.file_id, f.name, COUNT(t.tag) as tag_count
FROM files f
LEFT JOIN tags t ON f.file_id = t.file_id
WHERE f.deleted = 0
GROUP BY f.file_id;

-- Soft-deleted files (for debugging)
SELECT file_id, name, owner_id, created_at
FROM files
WHERE deleted = 1
ORDER BY created_at DESC;
```

**Important**: File counts should match across all controllers. If they differ, replication has failed or is lagging.

#### Check Peer Connectivity

```sql
-- See all registered controller peers
SELECT node_id, address, last_seen, vector_clock
FROM controller_nodes
ORDER BY last_seen DESC;

-- Count active peers (should be consistent across all controllers)
SELECT COUNT(*) as peer_count
FROM controller_nodes;

-- Peers not seen recently (potential failures)
SELECT node_id, address, last_seen,
       datetime(last_seen, 'unixepoch') as last_seen_readable
FROM controller_nodes
WHERE last_seen < strftime('%s', 'now', '-5 minutes');
```

#### Check User Replication

```sql
-- Count users across controllers (should match)
SELECT COUNT(*) as user_count FROM users;

-- Compare user vector clocks
SELECT user_id, username, vector_clock, version, last_modified_by
FROM users
ORDER BY user_id;
```

### Log Patterns for Monitoring

#### Watch Gossip Activity in Real-Time

```bash
# Watch all gossip events
tail -f controller_server_log_*.txt | grep -E "(Added to gossip|Sent.*updates|Received.*updates)"

# Watch file replication specifically
tail -f controller_server_log_*.txt | grep "Added file to gossip log"

# Watch conflict resolution
tail -f controller_server_log_*.txt | grep "Resolved conflict"

# Watch for errors
tail -f controller_server_log_*.txt | grep -E "(Failed to gossip|Failed to apply update)"
```

#### Key Log Messages

**Successful Replication Flow:**
```
Added to gossip log: file:abc123 (create)
Sent 5 updates to http://controller-2:8080
Received 3 updates from controller-1
Applied create for file:abc123 from gossip
```

**Conflict Resolution:**
```
Resolved conflict for file:xyz - took remote (newer version)
Taking remote version of file abc123
Keeping local version of file xyz (local is newer)
```

**Peer Management:**
```
Gossip service started
Loaded 2 peers from database
Discovered 2/2 peers via DNS
Peer consistency drift detected - only_in_db=[], only_in_memory=['node-3']
Auto-repaired: added controller-3 from database to memory
```

**Replication Failures:**
```
Failed to gossip to http://controller-2:8080: Connection refused
Failed to apply update file:xyz: Conflict resolution error
Anti-entropy with controller-2:8080 failed: Timeout
```

#### Search Historical Logs

```bash
# Find all gossip activity for a specific file
grep "<file_id>" controller_server_log_*.txt

# Count gossip send operations
grep -c "Sent.*updates to" controller_server_log_*.txt

# Find conflict resolutions
grep "Resolved conflict" controller_server_log_*.txt

# Check gossip service startup
grep "Gossip service started" controller_server_log_*.txt

# Find peer discovery events
grep "Discovered.*peers via DNS" controller_server_log_*.txt

# Check consistency check results
grep "Peer consistency" controller_server_log_*.txt
```

### Automatic Background Processes

The controller runs these monitoring loops automatically:

| Loop | Interval | Purpose | Log Indicator |
|------|----------|---------|---------------|
| Gossip Loop | 5s | Push updates to random peers (fanout=2) | `"Sent X updates to <peer>"` |
| Anti-Entropy Loop | 30s | Pull sync with random peer | `"Synced state summary from <peer>"` |
| Consistency Check | 300s (5min) | Verify DB vs memory peer registry | `"Peer consistency drift detected"` or `"Peer consistency check passed"` |

---

## Chunkserver Level - Chunk Replication Tracking

### Database Tables for Monitoring

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `chunk_locations` | Maps chunks to their replica servers | `chunk_id`, `chunkserver_id`, `created_at` |
| `chunkserver_nodes` | Registry of all chunkservers | `node_id`, `address`, `status`, `last_heartbeat`, `capacity_bytes`, `used_bytes` |
| `chunks` | Chunk metadata | `chunk_id`, `file_id`, `chunk_index`, `size`, `checksum` |

### SQL Queries for Monitoring

#### Check Chunk Replication Factor

```sql
-- Count replicas per chunk
SELECT chunk_id, COUNT(*) as replica_count
FROM chunk_locations
GROUP BY chunk_id
ORDER BY replica_count ASC;

-- Under-replicated chunks (< 3 replicas)
SELECT chunk_id, COUNT(*) as replica_count
FROM chunk_locations
GROUP BY chunk_id
HAVING COUNT(*) < 3;

-- Well-replicated chunks (>= 3 replicas)
SELECT COUNT(*) as well_replicated_count
FROM (
  SELECT chunk_id, COUNT(*) as replicas
  FROM chunk_locations
  GROUP BY chunk_id
  HAVING COUNT(*) >= 3
);

-- Replication factor distribution
SELECT replica_count, COUNT(*) as chunks_with_this_count
FROM (
  SELECT chunk_id, COUNT(*) as replica_count
  FROM chunk_locations
  GROUP BY chunk_id
)
GROUP BY replica_count
ORDER BY replica_count;
```

#### Check Chunks for Specific File

```sql
-- See all chunks for a file and their replica counts
SELECT c.chunk_id, c.chunk_index, c.size, COUNT(cl.chunkserver_id) as replica_count
FROM chunks c
LEFT JOIN chunk_locations cl ON c.chunk_id = cl.chunk_id
WHERE c.file_id = '<file_id>'
GROUP BY c.chunk_id
ORDER BY c.chunk_index;

-- Detailed view: chunks with their server locations
SELECT c.chunk_id, c.chunk_index, cl.chunkserver_id, cn.address, cn.status
FROM chunks c
JOIN chunk_locations cl ON c.chunk_id = cl.chunk_id
JOIN chunkserver_nodes cn ON cl.chunkserver_id = cn.node_id
WHERE c.file_id = '<file_id>'
ORDER BY c.chunk_index, cl.chunkserver_id;
```

#### Check Chunkserver Health

```sql
-- All chunkservers with their status
SELECT node_id, address, status,
       datetime(last_heartbeat, 'unixepoch') as last_heartbeat_time,
       used_bytes, capacity_bytes,
       ROUND(100.0 * used_bytes / capacity_bytes, 2) as usage_percent
FROM chunkserver_nodes
ORDER BY last_heartbeat DESC;

-- Failed chunkservers
SELECT node_id, address,
       datetime(last_heartbeat, 'unixepoch') as last_seen
FROM chunkserver_nodes
WHERE status = 'failed';

-- Active chunkservers
SELECT COUNT(*) as active_count
FROM chunkserver_nodes
WHERE status = 'active';

-- Chunks on a specific chunkserver
SELECT cl.chunk_id, c.file_id, c.chunk_index, c.size
FROM chunk_locations cl
JOIN chunks c ON cl.chunk_id = c.chunk_id
WHERE cl.chunkserver_id = '<node_id>'
ORDER BY cl.created_at DESC;

-- Chunks at risk (on failed server with < 3 total replicas)
SELECT DISTINCT cl.chunk_id, COUNT(*) as total_replicas
FROM chunk_locations cl
WHERE cl.chunk_id IN (
  SELECT chunk_id FROM chunk_locations
  WHERE chunkserver_id IN (
    SELECT node_id FROM chunkserver_nodes WHERE status = 'failed'
  )
)
GROUP BY cl.chunk_id
HAVING COUNT(*) < 3;
```

### Log Patterns for Monitoring

#### Watch Replication Activity

```bash
# Watch chunk writes (replication)
tail -f controller_server_log_*.txt | grep "Writing chunk.*to.*servers"

# Watch repair service
tail -f controller_server_log_*.txt | grep -E "(Repair cycle|under-replicated|Re-replicating chunk)"

# Watch chunkserver health checks
tail -f controller_server_log_*.txt | grep -E "(Health check|marked as failed|recovered)"

# Watch chunkserver heartbeats
tail -f controller_server_log_*.txt | grep "Received heartbeat from chunkserver"
```

#### Key Log Messages

**Chunk Replication:**
```
Writing chunk abc123 to 3 servers: [cs-1, cs-2, cs-3]
Successfully wrote chunk abc123 to cs-1:9000
Retry 1/3 for chunk abc123 to cs-2:9000: Connection refused
Successfully replicated chunk abc123 to 3/3 servers
```

**Health Monitoring:**
```
Health check loop started
Chunkserver cs-2 marked as failed (last heartbeat: 120s ago)
Chunkserver cs-2 recovered (received heartbeat)
```

**Repair Service:**
```
Repair service started
Checking replication health for 1500 chunks across 3 servers
Found 15 under-replicated chunks
Re-replicating chunk abc123 from cs-1 to cs-3
Repair cycle complete: 15/15 replications successful
Failed to re-replicate chunk xyz: No healthy source servers available
```

**Chunk Operations:**
```
Receiving chunk abc123, size=1048576
Chunk abc123 written successfully, checksum verified
Successfully read chunk abc123 from cs-2
Deleted chunk abc123 from 3/3 servers
```

#### Search Historical Logs

```bash
# Find replication activity for specific chunk
grep "<chunk_id>" controller_server_log_*.txt

# Count repair cycles
grep -c "Repair cycle complete" controller_server_log_*.txt

# Find failed replications
grep "Failed to.*replicate" controller_server_log_*.txt

# Check chunkserver registrations
grep "Received heartbeat from chunkserver" controller_server_log_*.txt | head -20

# See server failures
grep "marked as failed" controller_server_log_*.txt
```

### Automatic Background Processes

| Loop | Interval | Purpose | Log Indicator |
|------|----------|---------|---------------|
| Health Check | 10s | Mark failed chunkservers based on heartbeat timeout | `"Chunkserver X marked as failed"` |
| Repair Service | 60s | Find and repair under-replicated chunks | `"Repair cycle complete: X/Y successful"` |
| Heartbeat Processing | On-demand | Update chunkserver registry from heartbeats | `"Received heartbeat from chunkserver X"` |

---

## Testing File Replication

### Step-by-Step Replication Verification

After uploading a file to Controller 1:

**1. Wait for gossip propagation (10 seconds = 2x gossip interval)**

**2. Check Controller 1 database:**
```sql
SELECT file_id, name FROM files WHERE name = 'test-file.pdf' AND deleted = 0;
```
Note the `file_id`.

**3. Check gossip log on Controller 1:**
```sql
SELECT * FROM gossip_log
WHERE entity_type = 'file' AND entity_id = '<file_id>'
ORDER BY log_id DESC;
```
Expected: `operation='create'`, `gossiped_to` should list peer node IDs (JSON array).

**4. Check Controller 2 database:**
```sql
SELECT file_id, name, vector_clock FROM files WHERE file_id = '<file_id>';
```
Expected: File exists with same `file_id`.

**5. Check Controller 2 logs:**
```bash
grep "<file_id>" controller_server_log_2.txt
```
Expected log sequence:
```
Received 1 updates from controller-1
Applied create for file:<file_id> from gossip
Taking remote version of file <file_id>
```

**6. Check Controller 3 (same as Controller 2)**

**7. Verify tags replicated:**
```sql
SELECT tag FROM tags WHERE file_id = '<file_id>' ORDER BY tag;
```
Expected: Same tags on all controllers.

**8. Verify chunks metadata replicated:**
```sql
SELECT chunk_id, chunk_index, size, checksum
FROM chunks
WHERE file_id = '<file_id>'
ORDER BY chunk_index;
```
Expected: Same chunks on all controllers.

### Troubleshooting Replication Failures

If file doesn't appear on other controllers after 10 seconds:

**Check gossip service is running:**
```bash
grep "Gossip service started" controller_server_log_*.txt
```

**Check peer connectivity:**
```sql
SELECT * FROM controller_nodes;
```
Expected: All controllers should see all other controllers.

**Check for gossip errors:**
```bash
grep -E "(Failed to gossip|Failed to apply update)" controller_server_log_*.txt
```

**Check network connectivity:**
```bash
# From Controller 2, try to reach Controller 1
curl http://controller-1:8080/health
```

**Check if update was even logged:**
```bash
grep "Added file to gossip log" controller_server_log_1.txt | grep "<file_id>"
```
If not found: Bug in FileService gossip integration.

**Check anti-entropy:**
Wait 30 seconds for anti-entropy loop, then recheck databases.

---

## Quick Health Check Script

Create `scripts/check_replication.sh`:

```bash
#!/bin/bash

DB_PATH="${1:-data/controller.db}"

echo "=== Replication Health Check ==="
echo "Database: $DB_PATH"
echo ""

echo "=== Controller Metadata Replication ==="
echo "Files in gossip log (last hour):"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM gossip_log WHERE entity_type='file' AND timestamp > strftime('%s', 'now', '-1 hour');"

echo ""
echo "Total files (non-deleted):"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM files WHERE deleted = 0;"

echo ""
echo "Soft-deleted files:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM files WHERE deleted = 1;"

echo ""
echo "=== Chunk Replication Health ==="
echo "Total chunks:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM chunks;"

echo ""
echo "Under-replicated chunks (< 3 replicas):"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM (SELECT chunk_id FROM chunk_locations GROUP BY chunk_id HAVING COUNT(*) < 3);"

echo ""
echo "Well-replicated chunks (>= 3 replicas):"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM (SELECT chunk_id FROM chunk_locations GROUP BY chunk_id HAVING COUNT(*) >= 3);"

echo ""
echo "Replication factor distribution:"
sqlite3 "$DB_PATH" "SELECT replica_count as 'Replicas', COUNT(*) as 'Chunk Count' FROM (SELECT chunk_id, COUNT(*) as replica_count FROM chunk_locations GROUP BY chunk_id) GROUP BY replica_count ORDER BY replica_count;"

echo ""
echo "=== Chunkserver Status ==="
sqlite3 "$DB_PATH" "SELECT status as 'Status', COUNT(*) as 'Count' FROM chunkserver_nodes GROUP BY status;"

echo ""
echo "=== Controller Peers ==="
echo "Total registered peers:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM controller_nodes;"

echo ""
echo "Peers seen in last 5 minutes:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM controller_nodes WHERE last_seen > strftime('%s', 'now', '-5 minutes');"

echo ""
echo "=== Recent Gossip Activity (last 10 entries) ==="
sqlite3 "$DB_PATH" "SELECT entity_type, entity_id, operation, datetime(timestamp, 'unixepoch') as time FROM gossip_log ORDER BY log_id DESC LIMIT 10;"
```

Usage:
```bash
chmod +x scripts/check_replication.sh

# Check specific controller
./scripts/check_replication.sh data/controller.db

# Check all controllers
for i in 1 2 3; do
  echo "=== Controller $i ==="
  ./scripts/check_replication.sh "data/controller_$i.db"
  echo ""
done
```

---

## Compare Controllers Script

Create `scripts/compare_controllers.sh`:

```bash
#!/bin/bash

echo "=== Cross-Controller Consistency Check ==="
echo ""

for controller in "$@"; do
  echo "Controller: $controller"
  echo "  Files: $(sqlite3 "$controller" 'SELECT COUNT(*) FROM files WHERE deleted=0')"
  echo "  Users: $(sqlite3 "$controller" 'SELECT COUNT(*) FROM users')"
  echo "  Chunks: $(sqlite3 "$controller" 'SELECT COUNT(*) FROM chunks')"
  echo "  Peers: $(sqlite3 "$controller" 'SELECT COUNT(*) FROM controller_nodes')"
  echo ""
done

echo "Expected: All counts should match across controllers"
```

Usage:
```bash
chmod +x scripts/compare_controllers.sh
./scripts/compare_controllers.sh data/controller_1.db data/controller_2.db data/controller_3.db
```

---

## Monitoring Checklist

### Daily Monitoring

- [ ] Check under-replicated chunks count (should be 0)
- [ ] Check failed chunkservers (should be 0 or known failures)
- [ ] Verify file counts match across all controllers
- [ ] Check gossip log activity (should show regular updates)

### After File Upload

- [ ] Wait 10 seconds
- [ ] Verify file exists on all controllers
- [ ] Check tags replicated correctly
- [ ] Verify chunks metadata replicated

### After Controller Restart

- [ ] Check gossip service started
- [ ] Verify peer discovery (all controllers visible)
- [ ] Watch for anti-entropy sync messages
- [ ] Compare file counts with other controllers

### After Network Partition Recovery

- [ ] Watch for increased anti-entropy activity
- [ ] Check for conflict resolution messages
- [ ] Verify file counts converge
- [ ] Check for any replication errors

---

## Log Levels

The system respects the `LOG_LEVEL` environment variable:

| Level | What's Logged | Use Case |
|-------|---------------|----------|
| DEBUG | All events including gossip details | Development, troubleshooting |
| INFO | Normal operations, replication events | Production monitoring |
| WARNING | Potential issues, retries, recoveries | Production alerts |
| ERROR | Failures requiring attention | Production alerts |

Set log level:
```bash
export LOG_LEVEL=DEBUG
python controller/main.py
```

---

## Key Metrics to Track

### Controller Replication

- **Gossip log entries per hour** - Shows replication activity
- **Peer count** - Should be stable (number of controllers)
- **File count consistency** - Must match across controllers
- **Conflict resolution rate** - Should be low (< 1% of updates)
- **Peer consistency drift** - Should be 0 (auto-repaired)

### Chunk Replication

- **Under-replicated chunk count** - Should be 0
- **Failed chunkserver count** - Should be 0 or stable
- **Repair success rate** - Should be 100%
- **Replication factor distribution** - Most chunks should have 3 replicas
- **Heartbeat gaps** - Max gap should be < timeout (60s default)

---

## Common Issues and Diagnosis

### Issue: Files not replicating

**Diagnosis:**
1. Check if gossip service is running: `grep "Gossip service started" logs`
2. Check peer connectivity: `SELECT * FROM controller_nodes`
3. Check for gossip errors: `grep "Failed to gossip" logs`
4. Verify FileService is calling gossip: `grep "Added file to gossip log" logs`

### Issue: Chunks under-replicated

**Diagnosis:**
1. Check chunkserver health: `SELECT * FROM chunkserver_nodes WHERE status='failed'`
2. Check repair service: `grep "Repair cycle" logs`
3. Check replication manager errors: `grep "Failed to.*replicate" logs`
4. Verify enough healthy chunkservers: Should have at least 3 active

### Issue: Conflict resolution loops

**Diagnosis:**
1. Check vector clocks: `SELECT vector_clock FROM files WHERE file_id='X'`
2. Look for concurrent modification pattern in logs
3. Verify node IDs are unique across controllers

### Issue: Peer registry out of sync

**Diagnosis:**
1. Check consistency check logs: `grep "Peer consistency" logs`
2. Verify database vs memory: Compare `controller_nodes` table with logs
3. Should auto-repair every 5 minutes
4. If persists, check TTL cleanup configuration

---

## Performance Considerations

### Log Volume

With DEBUG level logging, expect:
- ~100-500 log lines per file upload (depends on file size / chunks)
- ~20-50 log lines per gossip cycle (every 5s)
- ~10 log lines per health check cycle (every 10s)

Rotate logs regularly to prevent disk fill.

### Database Growth

Gossip log grows indefinitely. Consider periodic cleanup:

```sql
-- Delete gossip entries older than 30 days
DELETE FROM gossip_log
WHERE timestamp < strftime('%s', 'now', '-30 days');

-- Vacuum to reclaim space
VACUUM;
```

Chunk locations and chunkserver registry are bounded by actual data size.

---

## Related Documentation

- `DISTRIBUTED_SYSTEM_PLAN.md` - Architecture and replication design
- `LOGGING.md` - Logging configuration and sensitive data masking
- `DISTRIBUTED_QUICKSTART.md` - How to start multi-controller setup
- Plan file: `.claude/plans/clever-percolating-brook.md` - Implementation details
