# Distributed System Implementation Plan
**RedCloud Files - AP System with Eventual Consistency**

## Executive Summary

Transform RedCloud from a single-controller system to a fully distributed AP (Available + Partition Tolerant) system with eventual consistency. This plan enables **any number** (≥1) of controller servers, chunkservers, and CLIs with automatic replication and conflict resolution.

**Target Architecture:**
- **Multiple Controllers:** Gossip protocol + Vector clocks (LWW), partition-tolerant
- **Multiple Chunkservers:** Parallel replication with **dynamic replication** based on availability
- **Multiple CLIs:** Already supported (no changes needed)
- **Deployment:** Multi-host Docker Swarm with DNS round-robin (mandatory)

**Key Requirements Met:**
- ✅ **Dynamic Scaling:** System works with any number ≥1 of each role
- ✅ **Network Partitions:** Each partition continues operating independently
- ✅ **Partition Healing:** Automatic synchronization when network reconnects
- ✅ **Full Eventual Replication:** All chunks eventually replicate to ALL chunkservers (no caps)
- ✅ **Automatic Repair:** Background service ensures full replication after partitions heal or servers join
- ✅ **Multi-Host:** Designed for multi-host deployment (mandatory)

---

## Phase 1: Controller Distribution Layer

### 1.1 Data Model Changes

**Add Vector Clocks to All Entities**

Each database entity needs versioning for conflict resolution:

```python
# New fields for all tables:
- vector_clock: JSON blob {node_id: counter}
- last_modified_by: TEXT (node_id that made last write)
- version: INTEGER (monotonic counter for quick comparison)
```

**Database Schema Changes:**
- `users` table: Add `vector_clock`, `last_modified_by`, `version`
- `files` table: Add `vector_clock`, `last_modified_by`, `version`, `deleted` (soft delete flag)
- `chunks` table: Add `vector_clock`, `last_modified_by`, `version`
- `tags` table: Add `vector_clock`, `last_modified_by`, `version`

**New Tables:**
```sql
-- Chunk location tracking (maps chunks to chunkservers)
CREATE TABLE chunk_locations (
    chunk_id TEXT NOT NULL,
    chunkserver_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY(chunk_id, chunkserver_id),
    FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
);

-- Chunkserver registry
CREATE TABLE chunkserver_nodes (
    node_id TEXT PRIMARY KEY,
    address TEXT NOT NULL,
    last_heartbeat REAL NOT NULL,
    capacity_bytes INTEGER,
    used_bytes INTEGER,
    status TEXT DEFAULT 'active'
);

-- Controller node registry
CREATE TABLE controller_nodes (
    node_id TEXT PRIMARY KEY,
    address TEXT NOT NULL,
    last_seen REAL NOT NULL,
    vector_clock TEXT NOT NULL
);

-- Gossip anti-entropy log
CREATE TABLE gossip_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    data TEXT NOT NULL,
    vector_clock TEXT NOT NULL,
    timestamp REAL NOT NULL,
    gossiped_to TEXT  -- JSON array of node_ids
);
```

### 1.2 Keep SQLite with Per-Controller Databases

**Why Keep SQLite:**
- ✅ Simple, no external dependencies
- ✅ Each controller has its own independent database file
- ✅ No shared state = no concurrency issues
- ✅ Gossip protocol handles synchronization

**Architecture:**
- Each controller: `data/controller-{node_id}/redcloud.db`
- Controllers do NOT share the same SQLite file
- Each controller's database is its local replica
- Gossip keeps databases eventually consistent

**Key Changes:**
```python
# In controller/config.py
import os

CONTROLLER_NODE_ID = os.getenv("CONTROLLER_NODE_ID", "controller-1")
DATABASE_PATH = os.getenv(
    "DATABASE_PATH", 
    f"data/controller-{CONTROLLER_NODE_ID}/redcloud.db"
)
```

**No Migration Needed:**
- Keep existing `controller/database.py` as-is
- Keep existing repository classes
- Only add vector clock columns to existing tables
- Each controller initializes its own SQLite on startup

### 1.3 Vector Clock Implementation

**New Module: `controller/vector_clock.py`**

```python
class VectorClock:
    """
    Vector clock for causality tracking and conflict resolution.
    Format: {node_id: counter}
    """
    
    def __init__(self, clock: dict[str, int] = None):
        self.clock = clock or {}
    
    def increment(self, node_id: str) -> 'VectorClock':
        """Increment this node's counter"""
        new_clock = self.clock.copy()
        new_clock[node_id] = new_clock.get(node_id, 0) + 1
        return VectorClock(new_clock)
    
    def merge(self, other: 'VectorClock') -> 'VectorClock':
        """Merge with another vector clock (max of each element)"""
        merged = {}
        all_nodes = set(self.clock.keys()) | set(other.clock.keys())
        for node in all_nodes:
            merged[node] = max(self.clock.get(node, 0), other.clock.get(node, 0))
        return VectorClock(merged)
    
    def compare(self, other: 'VectorClock') -> str:
        """
        Compare causality relationship.
        Returns: 'before', 'after', 'concurrent', 'equal'
        """
        self_greater = False
        other_greater = False
        
        all_nodes = set(self.clock.keys()) | set(other.clock.keys())
        for node in all_nodes:
            self_val = self.clock.get(node, 0)
            other_val = other.clock.get(node, 0)
            
            if self_val > other_val:
                self_greater = True
            elif other_val > self_val:
                other_greater = True
        
        if self_greater and not other_greater:
            return 'after'  # self happened after other
        elif other_greater and not self_greater:
            return 'before'  # self happened before other
        elif not self_greater and not other_greater:
            return 'equal'
        else:
            return 'concurrent'  # conflict!
    
    def to_json(self) -> str:
        return json.dumps(self.clock)
    
    @staticmethod
    def from_json(json_str: str) -> 'VectorClock':
        return VectorClock(json.loads(json_str))
```

### 1.4 Conflict Resolution (Last Write Wins)

**New Module: `controller/conflict_resolver.py`**

```python
class ConflictResolver:
    """
    Resolves conflicts using Last-Write-Wins with vector clocks.
    When concurrent writes detected, use timestamp as tiebreaker.
    """
    
    @staticmethod
    def resolve(local_entity, remote_entity) -> dict:
        """
        Resolve conflict between local and remote versions.
        
        Returns:
            {
                'action': 'keep_local' | 'take_remote' | 'merge',
                'winner': entity_to_use,
                'reason': str
            }
        """
        local_vc = VectorClock.from_json(local_entity.vector_clock)
        remote_vc = VectorClock.from_json(remote_entity.vector_clock)
        
        relationship = local_vc.compare(remote_vc)
        
        if relationship == 'after':
            return {
                'action': 'keep_local',
                'winner': local_entity,
                'reason': 'Local version causally after remote'
            }
        elif relationship == 'before':
            return {
                'action': 'take_remote',
                'winner': remote_entity,
                'reason': 'Remote version causally after local'
            }
        elif relationship == 'equal':
            return {
                'action': 'keep_local',
                'winner': local_entity,
                'reason': 'Identical versions'
            }
        else:  # concurrent
            # Last-Write-Wins: use timestamp
            local_ts = local_entity.created_at  # or last_modified
            remote_ts = remote_entity.created_at
            
            if remote_ts > local_ts:
                return {
                    'action': 'take_remote',
                    'winner': remote_entity,
                    'reason': f'Concurrent conflict - LWW favors remote ({remote_ts} > {local_ts})'
                }
            else:
                return {
                    'action': 'keep_local',
                    'winner': local_entity,
                    'reason': f'Concurrent conflict - LWW favors local ({local_ts} >= {remote_ts})'
                }
```

### 1.5 Gossip Protocol Implementation

**New Module: `controller/gossip/gossip_service.py`**

```python
class GossipService:
    """
    Implements gossip protocol for state synchronization between controllers.
    
    Responsibilities:
    - Periodically exchange state with random peers
    - Push updates to peers
    - Pull updates from peers
    - Track which nodes have received which updates
    """
    
    def __init__(self, node_id: str, peers: List[str]):
        self.node_id = node_id
        self.peers = peers  # List of other controller addresses
        self.gossip_interval = 5  # seconds
        self.anti_entropy_interval = 30  # seconds
        self.running = False
    
    async def start(self):
        """Start gossip background tasks"""
        self.running = True
        asyncio.create_task(self._gossip_loop())
        asyncio.create_task(self._anti_entropy_loop())
    
    async def _gossip_loop(self):
        """Push-based gossip: send updates to random peers"""
        while self.running:
            try:
                # Get pending updates from gossip_log
                pending_updates = await self._get_pending_updates()
                
                if pending_updates:
                    # Select random peer
                    peer = random.choice(self.peers)
                    
                    # Send updates
                    await self._send_updates_to_peer(peer, pending_updates)
                
                await asyncio.sleep(self.gossip_interval)
            except Exception as e:
                logger.error(f"Gossip loop error: {e}")
    
    async def _anti_entropy_loop(self):
        """
        Pull-based anti-entropy: periodically sync with random peer.
        
        PARTITION HANDLING:
        - If peer unreachable, try next peer
        - When partition heals, this loop automatically syncs state
        - No manual intervention needed
        """
        while self.running:
            try:
                # Discover available peers dynamically
                available_peers = await self._discover_peers()
                
                if not available_peers:
                    logger.warning("No peers available for anti-entropy")
                    await asyncio.sleep(self.anti_entropy_interval)
                    continue
                
                # Try random peer
                peer = random.choice(available_peers)
                
                # Exchange vector clocks to identify differences
                local_state_summary = await self._get_state_summary()
                remote_state_summary = await self._fetch_state_summary(peer)
                
                # Identify missing/conflicting entities
                to_push, to_pull = self._compute_sync_delta(
                    local_state_summary, 
                    remote_state_summary
                )
                
                # Push what peer is missing
                if to_push:
                    await self._send_updates_to_peer(peer, to_push)
                
                # Pull what we're missing
                if to_pull:
                    await self._pull_updates_from_peer(peer, to_pull)
                
                logger.info(f"Anti-entropy sync with {peer}: pushed {len(to_push)}, pulled {len(to_pull)}")
                
                await asyncio.sleep(self.anti_entropy_interval)
            except Exception as e:
                logger.error(f"Anti-entropy error: {e}")
                await asyncio.sleep(5)  # Short retry on error
    
    async def _discover_peers(self) -> List[str]:
        """
        Discover other controller nodes dynamically.

        Uses peer registry populated by:
        1. Initial bootstrap discovery (queries /internal/peers)
        2. Gossip propagation of peer registrations

        Returns list of reachable peer addresses.
        """
        # Get peers from peer registry (populated via discovery + gossip)
        peers = self.peer_registry.get_all_peers()
        return [peer["address"] for peer in peers]
    
    async def _send_updates_to_peer(self, peer: str, updates: List[dict]):
        """Send updates to peer via HTTP"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://{peer}/internal/gossip/receive",
                json={
                    'sender_node_id': self.node_id,
                    'updates': updates
                }
            ) as resp:
                if resp.status == 200:
                    # Mark updates as gossiped to this peer
                    await self._mark_updates_gossiped(updates, peer)
    
    async def receive_gossip(self, sender_node_id: str, updates: List[dict]):
        """
        Receive and apply gossip updates from peer.
        Called by internal HTTP endpoint.
        """
        for update in updates:
            await self._apply_update(update)
    
    async def _apply_update(self, update: dict):
        """
        Apply a single update with conflict resolution.
        
        Update format:
        {
            'entity_type': 'file' | 'user' | 'chunk' | 'tag',
            'entity_id': str,
            'operation': 'create' | 'update' | 'delete',
            'data': {...},
            'vector_clock': {...},
            'timestamp': float
        }
        """
        entity_type = update['entity_type']
        entity_id = update['entity_id']
        operation = update['operation']
        remote_data = update['data']
        remote_vc = VectorClock.from_json(json.dumps(update['vector_clock']))
        
        # Fetch local version
        local_entity = await self._fetch_local_entity(entity_type, entity_id)
        
        if local_entity is None:
            # No local version, accept remote
            await self._store_entity(entity_type, remote_data)
            logger.info(f"Applied {operation} for {entity_type}:{entity_id} from gossip")
        else:
            # Conflict resolution
            local_vc = VectorClock.from_json(local_entity.vector_clock)
            resolution = ConflictResolver.resolve(local_entity, remote_data)
            
            if resolution['action'] == 'take_remote':
                await self._store_entity(entity_type, remote_data)
                logger.info(f"Resolved conflict for {entity_type}:{entity_id} - took remote")
            else:
                logger.info(f"Resolved conflict for {entity_type}:{entity_id} - kept local")
```

**New Internal API Routes: `controller/routes/gossip_routes.py`**

```python
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/internal/gossip")

@router.post("/receive")
async def receive_gossip_updates(
    payload: dict,
    gossip_service: GossipService = Depends(get_gossip_service)
):
    """Receive gossip updates from peer controller"""
    await gossip_service.receive_gossip(
        sender_node_id=payload['sender_node_id'],
        updates=payload['updates']
    )
    return {"status": "ok"}

@router.get("/state-summary")
async def get_state_summary():
    """Return summary of local state for anti-entropy"""
    # Returns map of entity_id -> vector_clock for all entities
    summary = await compute_state_summary()
    return summary
```

### 1.6 Controller Node Discovery (Compatible with `docker run`)

**Auto-Configuration (No Environment Variables Required):**

Controllers auto-generate their identity from container hostname and IP:

```python
# controller/distributed_config.py
import socket
import os
import time

def get_container_ip():
    """
    Get container's IP address on Docker network.

    Uses routing table approach to find the correct interface IP.
    This works better than gethostbyname() for containers with multiple networks.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connect to a public IP (doesn't actually send data)
        # This determines which interface would be used for routing
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]  # Get the interface IP
    except Exception:
        # Fallback to hostname resolution
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
    finally:
        s.close()
    return ip

# Auto-generated from container hostname + timestamp (e.g., "abc123def456-1702345678")
# Timestamp ensures unique ID across restarts (fixes vector clock collision)
CONTROLLER_NODE_ID = os.getenv("CONTROLLER_NODE_ID") or f"{socket.gethostname()}-{int(time.time())}"

# Use IP address for reachability (not hostname)
CONTROLLER_ADVERTISE_ADDR = os.getenv("CONTROLLER_ADVERTISE_ADDR") or f"{get_container_ip()}:8000"

# Service discovery
CONTROLLER_SERVICE_NAME = os.getenv("CONTROLLER_SERVICE_NAME", "controller")
```

**Peer Discovery via Gossip (No Static Peer List):**

Instead of static peer lists or Docker Swarm `tasks.controller` DNS, use **gossip-based peer discovery**:

1. New controller queries `controller` DNS (resolves to one random controller)
2. Requests `/internal/peers` to get full peer list
3. Registers itself with discovered peer
4. Gossip propagates new peer to all controllers

### 1.7 Peer Discovery Implementation

**New Internal Routes: `controller/routes/internal_routes.py`**

```python
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/internal")

@router.get("/peers")
async def get_peers(peer_registry: PeerRegistry = Depends(get_peer_registry)):
    """
    Return list of known controller peers.
    Used by new controllers to bootstrap peer discovery.
    """
    return {
        "peers": peer_registry.get_all_peers(),
        "self": {
            "node_id": CONTROLLER_NODE_ID,
            "address": CONTROLLER_ADVERTISE_ADDR
        }
    }

@router.post("/peers/register")
async def register_peer(
    peer_info: dict,
    peer_registry: PeerRegistry = Depends(get_peer_registry),
    gossip_service: GossipService = Depends(get_gossip_service)
):
    """
    Allow controllers to register themselves.
    CRITICAL: Gossips registration to all other controllers.
    """
    await peer_registry.add_peer(
        node_id=peer_info["node_id"],
        address=peer_info["address"]
    )

    # Gossip this registration to all other controllers
    await gossip_service.add_to_gossip_log({
        "entity_type": "controller_peer",
        "entity_id": peer_info["node_id"],
        "operation": "register",
        "data": peer_info,
        "vector_clock": gossip_service.vector_clock.to_json(),
        "timestamp": time.time()
    })

    return {"status": "registered"}
```

**Peer Registry: `controller/gossip/peer_registry.py`**

```python
import asyncio
import aiohttp
import time
from controller.distributed_config import CONTROLLER_SERVICE_NAME, CONTROLLER_NODE_ID, CONTROLLER_ADVERTISE_ADDR

class PeerRegistry:
    """Maintains list of known controller peers via gossip"""

    def __init__(self):
        self.peers = {}  # {node_id: {"address": str, "last_seen": float}}
        self.lock = asyncio.Lock()

    async def discover_initial_peers(self):
        """
        Bootstrap by querying 'controller' DNS multiple times.
        DNS round-robin may return different IPs each time.
        """
        discovered = set()

        for attempt in range(10):  # Try 10 times to find different controllers
            try:
                async with aiohttp.ClientSession() as session:
                    # Query controller DNS (may get different IP each time)
                    async with session.get(
                        f"http://{CONTROLLER_SERVICE_NAME}:8000/internal/peers",
                        timeout=aiohttp.ClientTimeout(total=2)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()

                            # Add all peers from response
                            for peer in data["peers"]:
                                if peer["node_id"] != CONTROLLER_NODE_ID:
                                    discovered.add((peer["node_id"], peer["address"]))

                            # Register self with this peer
                            await session.post(
                                f"http://{CONTROLLER_SERVICE_NAME}:8000/internal/peers/register",
                                json={
                                    "node_id": CONTROLLER_NODE_ID,
                                    "address": CONTROLLER_ADVERTISE_ADDR
                                }
                            )
            except Exception:
                pass  # Ignore errors during discovery

            await asyncio.sleep(0.5)

        # Store discovered peers
        async with self.lock:
            for node_id, address in discovered:
                self.peers[node_id] = {"address": address, "last_seen": time.time()}

    def get_all_peers(self) -> list:
        """Get list of all known peers"""
        return [{"node_id": nid, "address": info["address"]} for nid, info in self.peers.items()]

    async def add_peer(self, node_id: str, address: str):
        """Add or update peer (called from gossip or registration)"""
        async with self.lock:
            self.peers[node_id] = {"address": address, "last_seen": time.time()}
```

**Update Gossip Service to Use Peer Registry:**

```python
# In controller/gossip/gossip_service.py

async def _discover_peers(self) -> List[str]:
    """Use peer registry for peer list"""
    peers = self.peer_registry.get_all_peers()
    return [peer["address"] for peer in peers]
```

**Deployment (Exact Same as Current):**

```bash
# Deploy multiple controllers - same command each time
docker run -d --network dfs-network --network-alias controller redcloud-controller:latest
docker run -d --network dfs-network --network-alias controller redcloud-controller:latest
docker run -d --network dfs-network --network-alias controller redcloud-controller:latest
```

No environment variables, no volumes needed. Controllers auto-configure and discover each other via gossip.

---

## Phase 2: Chunkserver Replication

### 2.1 Dynamic Chunk Placement Strategy

**Metadata-Tracked Placement with Dynamic Replication (No DHT)**

Instead of DHT/consistent hashing, use explicit metadata tracking with **dynamic replication factor**:

**How It Works:**
1. Controller maintains `chunk_locations` table mapping chunks to chunkservers
2. When writing a chunk, controller replicates to **all available chunkservers** (or a dynamic subset)
3. Controller stores the mapping in database
4. Gossip replicates this metadata to other controllers
5. System opportunistically increases replication as new servers join

**Full Eventual Replication Policy:**
- **Target:** Replicate to ALL available servers (no upper bounds)
- **Minimum replicas:** At least 1 (write succeeds if stored anywhere - partition tolerance)
- **Maximum replicas:** No cap - system aims for N-way replication (N = all chunkservers)
- **Repair service:** Continuously replicates until all chunks exist on all servers
- **New server joins:** Repair automatically replicates all existing chunks to it
- **Adaptive:** Automatically adjusts as servers join/leave
4. Gossip replicates this metadata to other controllers

**Placement Policies (configurable):**
- **Round-Robin:** Cycle through available chunkservers
- **Least-Loaded:** Pick servers with most free space
- **Random:** Randomly select N servers
- **Availability Zones:** Spread replicas across zones (future)

```python
# New Module: controller/chunk_placement.py

class ChunkPlacementManager:
    """ with DYNAMIC replication.
    """
    
    def __init__(self, min_replicas=1):
        """
        Initialize placement manager for full eventual replication.
        
        Args:
            min_replicas: Minimum replicas to attempt (default 1 for partition tolerance)
        
        NOTE: System replicates to ALL available chunkservers (no maximum cap).
        Repair service continuously ensures all chunks reach all servers.
        """
        self.min_replicas = min_replicas
        self._lchunkservers for a new chunk using DYNAMIC replication.
        
        Strategy: Replicate to all available servers up to max_replicas.
        This ensures maximum availability and durability.
        
        Args:
            chunk_id: UUID of chunk to place
            available_servers: List of {'node_id': str, 'address': str, 'used_bytes': int, ...}
        
        Returns:
            List of chunkserver node_ids to write to (1 to max_replicas servers)
        """
        if not available_servers:
            raise Exception("No chunkservers available")
        
        # Full Replication Strategy: Write to ALL available servers
        num_available = len(available_servers)
        
        logger.info(
            f"Full replication for chunk {chunk_id}: "
            f"Writing to ALL {num_available} available servers"
        )
        
        # Always select ALL available servers (no subset selection)
        selected = [s['node_id'] for s in available_servers]
        
        return selected
    
    async def select_chunkservers_for_read(
        self,
        chunk_id: str,
        chunk_locations: List[str]
    ) -> List[str]:
        """
        Select chunkservers to read from.
        Returns locations ordered by preference (healthy servers first).
        
        Args:
            chunk_id: UUID of chunk to read
            chunk_locations: List of chunkserver node_ids that have the chunk
        
        Returns:
            Ordered list of chunkserver node_ids to try
        """
        if not chunk_locations:
            raise FileNotFoundError(f"No locations found for chunk {chunk_id}")
        
        # Could add health checks, prefer local servers, etc.
        # For now, just return as-is (try first, then fallback)
        return chunk_locations
    
    async def get_chunk_locations(self, chunk_id: str) -> List[str]:
        """
        Retrieve list of chunkserver node_ids that store this chunk.
        Queries the chunk_locations table.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chunkserver_id 
                FROM chunk_locations 
                WHERE chunk_id = ?
            """, (chunk_id,))
            
            rows = cursor.fetchall()
            return [row['chunkserver_id'] for row in rows]
    
    async def record_chunk_location(
        self, 
        chunk_id: str, 
        chunkserver_id: str,
        conn=None
    ):
        """
        Record that a chunk is stored on a chunkserver.
        """
        should_close = False
        if conn is None:
            conn = get_db_connection().__enter__()
            should_close = True
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO chunk_locations 
                (chunk_id, chunkserver_id, created_at)
                VALUES (?, ?, ?)
            """, (chunk_id, chunkserver_id, time.time()))
            conn.commit()
        finally:
            if should_close:
                conn.__exit__(None, None, None)
    
    async def remove_chunk_location(
        self,
        chunk_id: str,
        chunkserver_id: str
    ):
        """Remove a chunk location (e.g., after deletion or server failure)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM chunk_locations
                WHERE chunk_id = ? AND chunkserver_id = ?
            """, (chunk_id, chunkserver_id))
            conn.commit()
```

### 2.2 Parallel Replication Protocol (Simpler than Chain)
Uses DYNAMIC replication - writes to all available servers.
    """
    
    def __init__(self, placement_manager: ChunkPlacementManager):
        self.placement = placement_manager
        self.chunkserver_clients = {}  # node_id -> ChunkserverClient
        self.min_write_success = 1  # Minimum successful writes to consider write successful
- ⚠️ Trade-off: Controller is coordination point (but we have multiple controllers)

**How It Works:**
1. **Write:** Controller writes to N chunkservers in parallel
2. **Read:** Controller reads from any available replica (tries first, fallbacks)
3. **Delete:** Controller deletes from all replicas in parallel

**New Module: `controller/replication_manager.py`**

```python
class ReplicationManager:
    """
    Manages parallel replication for chunks across multiple chunkservers.
    Uses DYNAMIC replication - writes to all available servers.
    """
    
    def __init__(self, placement_manager: ChunkPlacementManager):
        self.placement = placement_manager
        self.chunkserver_clients = {}  # node_id -> ChunkserverClient
        self.min_write_success = 1  # Minimum successful writes to consider write successful
    
    def get_client(self, chunkserver_id: str, address: str) -> ChunkserverClient:
        """Get or create gRPC client for a chunkserver"""
        if chunkserver_id not in self.chunkserver_clients:
            self.chunkserver_clients[chunkserver_id] = ChunkserverClient(
                target=address
            )
        return self.chunkserver_clients[chunkserver_id]
    
    async def write_chunk_replicated(
        self,
        chunk_id: str,
        file_id: str,
        chunk_index: int,
        data: bytes,
        checksum: str
    ) -> bool:
        """
        Write chunk to N chunkservers in parallel.
        
        Returns True if at least one write succeeds.
        Records all successful locations in chunk_locations table.
        """
        # Get available chunkservers
        available_servers = await self._get_available_chunkservers()
        
        # Select N servers for this chunk
        target_servers = await self.placement.select_chunkservers_for_write(
            chunk_id=chunk_id,
            available_servers=available_servers
        )
        
        if not target_servers:
            raise Exception("No chunkservers available for write")
        
        logger.info(f"Writing chunk {chunk_id} to {len(target_servers)} servers: {target_servers}")
        
        # Write to all targets in parallel
        write_tasks = []
        for server_id in target_servers:
            server_info = next(s for s in available_servers if s['node_id'] == server_id)
            client = self.get_client(server_id, server_info['address'])
            
            write_tasks.append(
                self._write_to_server(
                    client=client,
                    server_id=server_id,
                    chunk_id=chunk_id,
                    file_id=file_id,
                    chunk_index=chunk_index,
                    data=data,
                    checksum=checksum
                )
            )
        
        # Wait for all writes (gather exceptions)
        results = await asyncio.gather(*write_tasks, return_exceptions=True)
        
        # Record successful writes
        successful_servers = []
        with get_db_connection() as conn:
            for server_id, result in zip(target_servers, results):
                if result is True:
                    successful_servers.append(server_id)
                    await self.placement.record_chunk_location(
                        chunk_id, server_id, conn=conn
                    )
                else:
                    logger.error(f"Failed to write chunk {chunk_id} to {server_id}: {result}")
        
        if not successf: WriteChunk, ReadChunk, DeleteChunk, Ping
    
    // List all chunks on this server (for anti-entropy and repair)
    rpc ListChunks(ListChunksRequest) returns (ListChunksResponse);
    
    // Replicate chunk from another chunkserver (for repair)
    rpc ReplicateChunk(ReplicateChunkRequest) returns (ReplicateChunkResponse);
}

message ListChunksRequest {
    // Empty - returns all chunks on this server
}

message ListChunksResponse {
    repeated ChunkInfo chunks = 1;
}

message ChunkInfo {
    string chunk_id = 1;
    string file_id = 2;
    int32 chunk_index = 3;
    int64 size = 4;
    string checksum = 5;
}

message ReplicateChunkRequest {
    string chunk_id = 1;
    string source_chunkserver_address = 2;  // Where to fetch chunk from
}

message ReplicateChunkResponse {
    bool success = 1;
    string error = 2;
}
```

**Chunkserver Implementation:**

```python
# In chunkserver/grpc_server.py

async def ListChunks(self, request, context):
    """
    List all chunks stored on this chunkserver.
    Used by controller for health checks and repair.
    """
    try:
        all_chunks = self.chunk_index.list_all_chunks()
        
        chunk_infos = []
        for chunk_id, metadata in all_chunks.items():
            chunk_infos.append(ChunkInfo(
                chunk_id=chunk_id,
                file_id=metadata['file_id'],
                chunk_index=metadata['chunk_index'],
                size=metadata['size'],
                checksum=metadata['checksum']
            ))
        
        return ListChunksResponse(chunks=chunk_infos)
    except Exception as e:
        logger.error(f"Failed to list chunks: {e}")
        context.set_code(grpc.StatusCode.INTERNAL)
        context.set_details(str(e))
        return ListChunksResponse()

async def ReplicateChunk(self, request, context):
    """
    Replicate a chunk from another chunkserver.
    Used for repair when a replica is missing.
    """
    chunk_id = request.chunk_id
    source_address = request.source_chunkserver_address
    
    try:
        # Fetch chunk from source chunkserver
        async with grpc.aio.insecure_channel(source_address) as channel:
            stub = ChunkServiceStub(channel)
            
            # Read chunk from source
            read_response = await stub.ReadChunk(
                ReadChunkRequest(chunk_id=chunk_id)
            )
            
            # Collect all data pieces
            chunk_data = b""
            async for piece in read_response:
                chunk_data += piece.data
            
            # Write locally
            self.chunk_index.write_chunk(
                chunk_id=chunk_id,
                file_id=read_response.metadata.file_id,
                chunk_index=read_response.metadata.chunk_index,
                data=chunk_data,
                expected_checksum=read_response.metadata.checksum
            )
            
            logger.info(f"Successfully replicated chunk {chunk_id} from {source_address}")
            return ReplicateChunkResponse(success=True)
            
    except Exception as e:
        logger.error(f"Failed to replicate chunk {chunk_id} from {source_address}: {e}")
        return ReplicateChunkResponse(success=False, error=str(e)
            logger.error(f"Write to {server_id} failed: {e}")
            return False
```

### 2.3 Chunkserver Changes

**New gRPC Methods in `common/protocol.proto`:**

```protobuf
service ChunkService {
    // Existing methods: WriteChunk, ReadChunk, DeleteChunk, Ping
    
    // List all chunks on this server (for anti-entropy and repair)
    rpc ListChunks(ListChunksRequest) returns (ListChunksResponse);
    
    // Replicate chunk from another chunkserver (for repair)
    rpc ReplicateChunk(ReplicateChunkRequest) returns (ReplicateChunkResponse);
}

message ListChunksRequest {
    // Empty - returns all chunks on this server
}

message ListChunksResponse {
    repeated ChunkInfo chunks = 1;
}

message ChunkInfo {
    string chunk_id = 1;
    string file_id = 2;
    int32 chunk_index = 3;
    int64 size = 4;
    string checksum = 5;
}

message ReplicateChunkRequest {
    string chunk_id = 1;
    string source_chunkserver_address = 2;  // Where to fetch chunk from
}

message ReplicateChunkResponse {
    bool success = 1;
    string error = 2;
}
```

**Chunkserver Implementation:**

```python
# In chunkserver/grpc_server.py

async def ListChunks(self, request, context):
    """
    List all chunks stored on this chunkserver.
    Used by controller for health checks and repair.
    """
    try:
        all_chunks = self.chunk_index.list_all_chunks()
        
        chunk_infos = []
        for chunk_id, metadata in all_chunks.items():
            chunk_infos.append(ChunkInfo(
                chunk_id=chunk_id,
                file_id=metadata['file_id'],
                chunk_index=metadata['chunk_index'],
                size=metadata['size'],
                checksum=metadata['checksum']
            ))
        
        return ListChunksResponse(chunks=chunk_infos)
    except Exception as e:
        logger.error(f"Failed to list chunks: {e}")
        context.set_code(grpc.StatusCode.INTERNAL)
        context.set_details(str(e))
        return ListChunksResponse()

async def ReplicateChunk(self, request, context):
    """
    Replicate a chunk from another chunkserver.
    Used for repair when a replica is missing.
    """
    chunk_id = request.chunk_id
    source_address = request.source_chunkserver_address
    
    try:
        # Fetch chunk from source chunkserver
        async with grpc.aio.insecure_channel(source_address) as channel:
            stub = ChunkServiceStub(channel)
            
            # Read chunk from source
            read_response = await stub.ReadChunk(
                ReadChunkRequest(chunk_id=chunk_id)
            )
            
            # Collect all data pieces
            chunk_data = b""
            async for piece in read_response:
                chunk_data += piece.data
            
            # Write locally
            self.chunk_index.write_chunk(
                chunk_id=chunk_id,
                file_id=read_response.metadata.file_id,
                chunk_index=read_response.metadata.chunk_index,
                data=chunk_data,
                expected_checksum=read_response.metadata.checksum
            )
            
            logger.info(f"Successfully replicated chunk {chunk_id} from {source_address}")
            return ReplicateChunkResponse(success=True)
            
    except Exception as e:
        logger.error(f"Failed to replicate chunk {chunk_id} from {source_address}: {e}")
        return ReplicateChunkResponse(success=False, error=str(e))
```

### 2.4 Chunkserver Discovery

**New Table in Controller DB:**

```sql
CREATE TABLE chunkserver_nodes (
    node_id TEXT PRIMARY KEY,
    address TEXT NOT NULL,
    last_heartbeat REAL NOT NULL,
    capacity_bytes BIGINT,
    used_bytes BIGINT,
    status TEXT DEFAULT 'active'  -- active, failed, draining
);
```

**Chunkserver Heartbeat:**

```python
# Chunkservers periodically register with controllers

async def heartbeat_loop():
    """Send periodic heartbeat to controller"""
    while True:
        try:
            await send_heartbeat_to_controller()
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")
            await asyncio.sleep(5)

async def send_heartbeat_to_controller():
    """
    Register with controller and report status.

    NOTE: Sends to 'controller' DNS (reaches one random controller).
    That controller will gossip the registration to all other controllers.
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"http://{CONTROLLER_SERVICE_NAME}/internal/chunkserver/heartbeat",
            json={
                'node_id': CHUNKSERVER_NODE_ID,
                'address': CHUNKSERVER_ADVERTISE_ADDR,  # Use IP address, not hostname
                'capacity_bytes': get_total_capacity(),
                'used_bytes': get_used_capacity()
            },
            timeout=aiohttp.ClientTimeout(total=5)
        ) as resp:
            resp.raise_for_status()
```

### 2.5 Chunkserver Failure Detection

**Critical: Detect and mark failed chunkservers to avoid read failures.**

**New Module: `controller/chunkserver_health.py`**

```python
import asyncio
import time
from typing import Dict, Set

class ChunkserverHealthMonitor:
    """
    Monitors chunkserver health based on heartbeat timestamps.
    Marks chunkservers as failed if they miss heartbeats.
    """

    def __init__(self, chunkserver_registry, heartbeat_timeout: int = 30):
        """
        Args:
            chunkserver_registry: Registry storing chunkserver info
            heartbeat_timeout: Seconds without heartbeat before marking failed (default: 30)
        """
        self.chunkserver_registry = chunkserver_registry
        self.heartbeat_timeout = heartbeat_timeout
        self.failed_servers: Set[str] = set()  # Track failed server IDs
        self.running = False

    async def start(self):
        """Start background health monitoring"""
        self.running = True
        asyncio.create_task(self._health_check_loop())

    async def _health_check_loop(self):
        """Periodically check for failed chunkservers"""
        while self.running:
            try:
                await self._check_chunkserver_health()
                await asyncio.sleep(10)  # Check every 10 seconds
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(5)

    async def _check_chunkserver_health(self):
        """Mark chunkservers as failed if heartbeat timeout exceeded"""
        current_time = time.time()
        cutoff_time = current_time - self.heartbeat_timeout

        all_servers = await self.chunkserver_registry.get_all()

        for server in all_servers:
            server_id = server['node_id']
            last_heartbeat = server.get('last_heartbeat', 0)

            if last_heartbeat < cutoff_time:
                # Heartbeat timeout exceeded
                if server_id not in self.failed_servers:
                    logger.warning(
                        f"Chunkserver {server_id} failed (no heartbeat for "
                        f"{int(current_time - last_heartbeat)}s)"
                    )
                    self.failed_servers.add(server_id)
                    await self.chunkserver_registry.mark_failed(server_id)

                    # Trigger repair for chunks on this server
                    await self._trigger_repair_for_failed_server(server_id)
            else:
                # Heartbeat received, mark as healthy if previously failed
                if server_id in self.failed_servers:
                    logger.info(f"Chunkserver {server_id} recovered")
                    self.failed_servers.remove(server_id)
                    await self.chunkserver_registry.mark_healthy(server_id)

    async def _trigger_repair_for_failed_server(self, server_id: str):
        """
        Notify repair service that a server has failed.
        Repair service will replicate chunks to other servers.
        """
        logger.info(f"Triggering repair for failed chunkserver {server_id}")
        # Repair service will detect under-replication in its next cycle

    def is_healthy(self, server_id: str) -> bool:
        """Check if a chunkserver is currently healthy"""
        return server_id not in self.failed_servers
```

**Update Chunkserver Registry: `controller/chunkserver_registry.py`**

```python
class ChunkserverRegistry:
    """Registry for tracking chunkserver nodes and their status"""

    def __init__(self):
        self.servers = {}  # {node_id: {address, last_heartbeat, status, ...}}
        self.lock = asyncio.Lock()

    async def update_chunkserver(self, node_id: str, address: str, capacity_bytes: int, used_bytes: int):
        """Update chunkserver info from heartbeat"""
        async with self.lock:
            self.servers[node_id] = {
                'node_id': node_id,
                'address': address,
                'capacity_bytes': capacity_bytes,
                'used_bytes': used_bytes,
                'last_heartbeat': time.time(),
                'status': 'active'  # active, failed
            }

    async def mark_failed(self, node_id: str):
        """Mark chunkserver as failed"""
        async with self.lock:
            if node_id in self.servers:
                self.servers[node_id]['status'] = 'failed'

    async def mark_healthy(self, node_id: str):
        """Mark chunkserver as healthy (recovered)"""
        async with self.lock:
            if node_id in self.servers:
                self.servers[node_id]['status'] = 'active'

    async def get_healthy_servers(self) -> list:
        """Get list of healthy (active) chunkservers only"""
        async with self.lock:
            return [
                s for s in self.servers.values()
                if s.get('status') == 'active'
            ]

    async def get_all(self) -> list:
        """Get all chunkservers (including failed)"""
        async with self.lock:
            return list(self.servers.values())
```

**Update Read Path to Filter Failed Chunkservers:**

```python
# In controller/replication_manager.py

async def select_chunkservers_for_read(
    self,
    chunk_id: str,
    chunk_locations: List[str],
    health_monitor: ChunkserverHealthMonitor
) -> List[str]:
    """
    Select chunkservers to read from, preferring healthy servers.

    Args:
        chunk_id: UUID of chunk to read
        chunk_locations: List of chunkserver node_ids that have the chunk
        health_monitor: Health monitor to check server status

    Returns:
        Ordered list of chunkserver node_ids to try (healthy first)
    """
    if not chunk_locations:
        raise FileNotFoundError(f"No locations found for chunk {chunk_id}")

    # Separate healthy and failed servers
    healthy = [loc for loc in chunk_locations if health_monitor.is_healthy(loc)]
    failed = [loc for loc in chunk_locations if not health_monitor.is_healthy(loc)]

    # Return healthy servers first, failed as fallback
    return healthy + failed  # Try healthy first, fall back to failed if needed
```

**Controller Startup: Initialize Health Monitor**

```python
# In controller/main.py

async def startup():
    # ... existing initialization ...

    # Initialize chunkserver health monitor
    health_monitor = ChunkserverHealthMonitor(
        chunkserver_registry=chunkserver_registry,
        heartbeat_timeout=30  # 30 seconds
    )
    await health_monitor.start()

    logger.info("Chunkserver health monitor started")
```

### 2.6 Chunk Repair & Anti-Entropy

**Background Task in Controller:**
    
                # Trigger replication to new servers
                if target_servers and actual_nodes:
                    source_node = actual_nodes[0]
                    source_info = await self._get_chunkserver_info(source_node)
                    
                    for target_server in target_servers:
                        success = await self._replicate_chunk(
                            chunk_id=chunk.chunk_id,
                            source_address=source_info['address'],
                            target_server_id=target_server['node_id'],
                            target_address=target_server['address']
                        )
                        
                        if success:
                            # Record new location
                            await self.placement.record_chunk_location(
                                chunk.chunk_id,
                                target_server['node_id']
                            )
                            logger.info(
                                f"Repaired chunk {chunk.chunk_id} to {target_server['node_id']}"
        
    async def _check_replication_health(self):
        """
        Find under-replicated chunks and repair.
        
        Goal: Ensure ALL chunks exist on ALL chunkservers eventually.
        This runs continuously in background and automatically handles:
        - New chunkserver joins (replicates all chunks to it)
        - Partition healing (fills in missing chunks)
        - Failed replications (retries until successful)
        """
        all_chunks = await self.chunk_repo.get_all_chunks()
        all_servers = await self._get_available_chunkservers()
        
        if not all_servers:
            logger.warning("No chunkservers available for repair")
            return
        
        for chunk in all_chunks:
            # Get current locations
            current_locations = await self.placement.get_chunk_locations(chunk.chunk_id)
            
            # Target: ALL available servers (full replication)
            missing_servers = [
                s for s in all_servers 
                if s['node_id'] not in current_locations
            ]
            
            if missing_servers:
                logger.info(
                    f"Chunk {chunk.chunk_id} under-replicated: "
                    f"{len(current_locations)}/{len(all_servers)} replicas. "
                    f"Replicating to {len(missing_servers)} missing servers."
                )
                
                # Pick any existing replica as source
                if current_locations:
                    source_node = current_locations[0]
                    source_info = await self._get_chunkserver_info(source_node)
                    
                    # Replicate to ALL missing servers
                    for target_server in missing_servers:
                        success = await self._replicate_chunk(
                            chunk_id=chunk.chunk_id,
                            source_address=source_info['address'],
                            target_server_id=target_server['node_id'],
                            target_address=target_server['address']
                        )
                        
                        if success:
                            await self.placement.record_chunk_location(
                                chunk.chunk_id,
                                target_server['node_id']
                            )
                            logger.info(
                                f"Successfully replicated chunk {chunk.chunk_id} "
                                f"to {target_server['node_id']}"
                            )
                        else:
                            logger.error(
                                f"Failed to replicate chunk {chunk.chunk_id} "
                                f"to {target_server['node_id']} - will retry next cycle"
                            )
```

---

## Phase 3: System Configuration

### 3.1 Deployment with `docker run` (Matches Current System)

**NO CHANGES to existing deployment commands** - system auto-configures from container hostname and IP.

#### Network Setup

```bash
# Initialize Docker Swarm (if not already active)
docker swarm init

# Create overlay network for multi-host communication
docker network create --driver overlay --attachable dfs-network
```

#### Deploy Controllers

Run the same command multiple times (e.g., 3 controllers):

```bash
docker run -d --network dfs-network --network-alias controller redcloud-controller:latest
docker run -d --network dfs-network --network-alias controller redcloud-controller:latest
docker run -d --network dfs-network --network-alias controller redcloud-controller:latest
```

**What happens:**
- Each controller auto-generates unique `CONTROLLER_NODE_ID` from its container hostname
- Each controller detects its IP address and uses it for `CONTROLLER_ADVERTISE_ADDR`
- Controllers discover each other via `/internal/peers` endpoint + gossip
- Each controller creates its own SQLite database at `/app/data/controller-{hostname}/redcloud.db` (ephemeral)
- DNS round-robin distributes CLI requests across all controllers

#### Deploy Chunkservers

Run the same command multiple times (e.g., 5 chunkservers):

```bash
docker run -d --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
docker run -d --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
docker run -d --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
docker run -d --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
docker run -d --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest
```

**What happens:**
- Each chunkserver auto-generates unique `CHUNKSERVER_NODE_ID` from container hostname
- Each chunkserver advertises its IP address (e.g., `10.0.1.5:50051`)
- Heartbeat sent to `controller` DNS (reaches one random controller)
- Controller gossips chunkserver registration to all other controllers
- All controllers eventually know about all chunkservers

#### Deploy CLI

```bash
# Navigate to directory with files to upload
cd /path/to/your/files

docker run -it --rm \
    --network dfs-network \
    -v "$(pwd):/uploads" \
    -v "$(pwd)/downloads:/downloads" \
    -w /uploads \
    redcloud-cli:latest
```

**What happens:**
- CLI connects to `controller` DNS (round-robin to any controller)
- Uploads/downloads work regardless of which controller handles the request
- Gossip ensures all controllers see the same metadata eventually

#### Auto-Configuration Summary

| Component | Node ID | Advertise Address | Storage |
|-----------|---------|-------------------|---------|
| **Controller** | `hostname` (e.g., `abc123def456`) | `container_ip:8000` (e.g., `10.0.1.2:8000`) | Ephemeral `/app/data/` |
| **Chunkserver** | `hostname` (e.g., `xyz789ghi012`) | `container_ip:50051` (e.g., `10.0.1.5:50051`) | Ephemeral `/app/data/chunks/` |
| **CLI** | N/A | N/A | Volume mounts for uploads/downloads |

**No environment variables required.** No volumes required (ephemeral storage acceptable).

#### Using Existing Scripts

The existing deployment scripts in `docker/scripts/` work without modification:

```bash
cd docker/scripts

# Initialize network
./init-network.sh

# Build images
./build-images.sh

# Deploy one controller
./run-controller.sh

# Deploy multiple chunkservers
./scale-chunkserver.sh 5

# Run CLI
./run-cli.sh
```

For multiple controllers, run `./run-controller.sh` multiple times.

### 3.2 Configuration Management (Auto-Configuration)

**New Config Module: `controller/distributed_config.py`**

```python
import os
import socket
import time

def get_container_ip():
    """
    Get container's IP address on Docker network.

    Uses routing table approach to find the correct interface IP.
    Handles containers with multiple network interfaces correctly.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connect to a public IP (doesn't actually send data)
        # This determines which interface would be used for routing
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]  # Get the interface IP
    except Exception:
        # Fallback to hostname resolution
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
    finally:
        s.close()
    return ip

# Node identity (auto-generated from container hostname + timestamp)
# Timestamp ensures unique ID across restarts (prevents vector clock collision)
CONTROLLER_NODE_ID = os.getenv("CONTROLLER_NODE_ID") or f"{socket.gethostname()}-{int(time.time())}"

# Advertise address (use IP for reachability, not hostname)
CONTROLLER_ADVERTISE_ADDR = os.getenv("CONTROLLER_ADVERTISE_ADDR") or f"{get_container_ip()}:8000"

# SQLite Database (per-controller, ephemeral)
DATABASE_PATH = os.getenv("DATABASE_PATH") or f"/app/data/controller-{CONTROLLER_NODE_ID}/redcloud.db"

# Full Eventual Replication Configuration
# System aims to replicate ALL chunks to ALL available chunkservers eventually
MIN_CHUNK_REPLICAS = int(os.getenv("MIN_CHUNK_REPLICAS", "1"))  # Minimum for partition tolerance
# No MAX_REPLICAS cap - replicate to all available servers
# TARGET_REPLICATION_RATIO always 1.0 (100%) - replicate to all available servers

# Gossip
GOSSIP_INTERVAL = int(os.getenv("GOSSIP_INTERVAL", "5"))
ANTI_ENTROPY_INTERVAL = int(os.getenv("ANTI_ENTROPY_INTERVAL", "30"))
GOSSIP_FANOUT = int(os.getenv("GOSSIP_FANOUT", "2"))  # Number of peers to gossip to

# Peer discovery
# Controllers discover peers via /internal/peers endpoint + gossip
# DNS "controller" used for initial bootstrap (round-robin to find first peer)
CONTROLLER_SERVICE_NAME = os.getenv("CONTROLLER_SERVICE_NAME", "controller")
```

**Chunkserver Config Module: `chunkserver/distributed_config.py`**

```python
import os
import socket
import time

def get_container_ip():
    """
    Get chunkserver's IP address on Docker network.

    Uses routing table approach to find the correct interface IP.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
    finally:
        s.close()
    return ip

# Node identity (auto-generated from container hostname + timestamp)
# Timestamp ensures unique ID across restarts
CHUNKSERVER_NODE_ID = os.getenv("CHUNKSERVER_NODE_ID") or f"{socket.gethostname()}-{int(time.time())}"

# Advertise address (use IP for controllers to connect via gRPC)
CHUNKSERVER_ADVERTISE_ADDR = os.getenv("CHUNKSERVER_ADVERTISE_ADDR") or f"{get_container_ip()}:50051"

# Storage paths (ephemeral)
CHUNK_STORAGE_PATH = os.getenv("CHUNK_STORAGE_PATH", "/app/data/chunks")
CHUNK_INDEX_PATH = os.getenv("CHUNK_INDEX_PATH", "/app/data/chunk_index.json")

# Controller discovery
CONTROLLER_SERVICE_NAME = os.getenv("CONTROLLER_SERVICE_NAME", "controller")
```

**Key Differences from Original Plan:**
- ✅ **No environment variables required** (all auto-detected)
- ✅ **IP-based addresses** (not hostname-based)
- ✅ **Peer discovery via gossip** (not static peer list or `tasks.controller`)
- ✅ **Compatible with `docker run`** (no Docker service templating)

---

## Phase 4: Implementation Roadmap

### Milestone 1: Controller Gossip Foundation (2-3 weeks)
1. ✅ Add vector clock columns to all SQLite tables (keep SQLite!)
2. ✅ Add `chunk_locations` table for metadata-tracked placement
3. ✅ Implement `VectorClock` class
4. ✅ Implement `ConflictResolver` class
5. ✅ Update all write operations to increment vector clocks
6. ✅ Configure per-controller SQLite databases
7. ✅ Test vector clock merging and conflict detection

### Milestone 2: Gossip Protocol (2-3 weeks)
1. ✅ Implement `GossipService` class
2. ✅ Add gossip log table and tracking
3. ✅ Implement internal gossip HTTP endpoints
4. ✅ Add vector clock columns to all SQLite tables (keep SQLite!)
2. ✅ Add `chunk_locations` table for metadata-tracked placement
3. ✅ Implement `VectorClock` class
4. ✅ Implement `ConflictResolver` class
5. ✅ Update all write operations to increment vector clocks
6. ✅ Configure per-controller SQLite databases
7. ✅ Implement `ConsistentHashRing` class
2. ✅ Add chunkserver heartbeat mechanism
3. ✅ Add chunkserver registry table in controller
4. ✅ Update controller to track available chunkservers
5. ✅ Test consistent hashing distribution

### Milestone 4: Chain Replication (3-4 weeks)
1. ✅ Extend gRPC protocol with chain replication RPCs
2. ✅ Implement `ChainReplicationManager` in controller
3. ✅ Update chunkserver to handle chain writes
4. ✅ Implement wrhunkPlacementManager` class (metadata-tracked, no DHT)
2. ✅ Add chunkserver heartbeat mechanism
3. ✅ Add chunkserver registry table in controller
4. ✅ Update controller to track available chunkservers
5. ✅ Implement round-robin placement policy
6. ✅ Test placement and location tracking-3 weeks)
1. ✅ Implement `CParallel Replication (2-3 weeks)
1. ✅ Extend gRPC protocol with ListChunks and ReplicateChunk RPCs
2. ✅ Implement `ReplicationManager` in controller
3. ✅ Update chunkserver to handle replication requests
4. ✅ Implement parallel write logic
5. ✅ Update read logic to try replicas with fallback
6. ✅ Update delete logic to remove from all replicas
7. ✅ Test parallelker Swarm deployment
2. ✅ End-to-end testing with multiple controllers
3. ✅ End-to-end testing with multiple chunkservers
4. ✅ Chaos testing (kill nodes, network partitions)
5. ✅ Performance benchmarking
6. ✅ Documentation updates

**Total Estimated Time: 12-18 weeks**

---

## Phase 5: Safety & Consistency Guarantees

### 5.1 What This Design Provides

✅ **Availability:**
- System remains available during controller failures (other controllers serve requests)
- System remains available during chunkserver failures (replicas serve data)
- No single point of failure

✅ **Partition Tolerance:**
- Network partitions between controllers: Each partition continues operating
- Gossip eventually recon1-17 weeks** (slightly faster without DHT and chain complexity)when partition heals
- Chunk replicas spread across nodes survive partitions

✅ **Eventual Consistency:**
- ControNetwork Partition Scenarios

**Scenario 1: Controller Partition**
```
Initial: [C1, C2, C3] all connected
Partition: [C1, C2] | [C3]

During Partition:
- User connects to C1 or C2: Sees files uploaded to partition A
- User connects to C3: Sees files uploaded to partition B
- Both partitions operate independently
- Each partition has its own SQLite with diverging state

After Heal:
- Gossip detects new peers
- Anti4 Trade-offs

**Why AP instead of CP?**
- File storage prioritizes availability over strong consistency
- Users tolerate eventual consistency better than downtime
- Last-write-wins is acceptable for file metadata (user uploads newer version = wins)
- Network partitions should NOT stop file uploads/downloads

**Why Full Replication to All Servers?**
- ✅ Maximum durability (survives N-1 server failures)
- ✅ Maximum availability (any server can serve any chunk)
- ✅ Simple reasoning (every server has everything)
- ✅ No configuration needed (adapts to cluster size)
- ⚠️ N× storage overhead (acceptable for small-medium datasets)
- ⚠️ N× write bandwidth (mitigated by fast local networks)

**Challenges:**
- Conflict resolution is simplistic (LWW may lose concurrent edits during partitions)
- No distributed transactions (file+chunks may temporarily diverge)
- Debugging distributed state is harder
- Storage overhead scales with cluster size (N servers = N× storage)
- Users in different partitions see completely different state during partition
Partition A (C1, CS1):
- Reads of chunk X succeed (CS1 has replica)
- New chunks written to CS1 only (only available server)

Partition B (C2, CS2, CS3):
- Reads of chunk X succeed (CS2, CS3 have replicas)
- New chunks written to CS2, CS3 (both available)

After Heal:
- Repair service detects CS1 missing new chunks
- Triggers replication: CS2 → CS1
- All chunks reach desired replication level
```

**Scenario 3: Complete Isolation (Single Node)**
```
Initial: [C1, C2, C3, CS1, CS2, CS3]
Partition: [C1, CS1] | [C2, CS2, CS3]

During Partition:
- C1 + CS1 operate independently
- Limited capacity but still functional
- Writes to CS1 only

After Heal:
- Repair service replicates chunks to other servers
- Returns to full replication
```

### 5.5 Safety Guarantees with Full Replication

**Idempotent Operations Prevent Data Corruption:**

1. **Chunkserver Write Safety:**
   - Writing same `chunk_id` twice → File overwrites (`Path.write_bytes`)
   - In-memory index update → Dictionary assignment replaces entry
   - Result: Only ONE copy of each chunk on disk (no duplicates)

2. **Controller Metadata Safety:**
   - `INSERT OR IGNORE` in `chunk_locations` → No duplicate records
   - Multiple controllers writing same chunk → All record same locations
   - Vector clocks resolve metadata conflicts deterministically (LWW)

3. **Race Condition Handling:**
   - Same chunk to same server twice → Safe (idempotent overwrite)
   - Concurrent repair tasks → Safe (wasted bandwidth, no corruption)
   - Conflicting metadata updates → Resolved via vector clocks

**Controller Coordination:**
   - Controllers do NOT coordinate with each other for chunkserver operations
   - Each controller independently decides which chunkservers to write to
   - Chunkservers accept duplicate writes safely (idempotent)
   - Gossip/anti-entropy sync metadata only (not chunk data)

**Full Replication Benefits:**
- ✅ Survives loss of N-1 chunkservers (maximum durability)
- ✅ Maximum read performance (any server can serve any chunk)
- ✅ No read hot spots (perfect load distribution)
- ✅ Simple reasoning (every server has everything eventually)

**Full Replication Trade-offs:**
- ⚠️ N× storage overhead (10 servers = 10× storage required)
- ⚠️ N× write bandwidth during uploads (sends to all servers)
- ⚠️ Longer partition healing (more data to synchronize)
- ⚠️ Not suitable for massive datasets without sufficient storage

**When Full Replication is Appropriate:**
- Small to medium datasets (<10TB total across all replicas)
- High availability requirements (99.99%+ uptime)
- Fast local network (10Gbps+ between servers)
- Storage is cheaper than downtime
- Read-heavy workloads (benefit from perfect distribution)

---

## Phase 6: System Integration

### 6.1 Key Design Principles

This system implements a distributed AP (Available + Partition Tolerant) file system with **partition tolerance** and **full eventual replication**:

1. **Controllers:** Per-controller SQLite + Gossip + Vector Clocks for eventual consistency
2. **Chunkservers:** Metadata-tracked placement + Parallel replication to ALL servers
3. **Deployment:** Multi-host Docker Swarm with DNS discovery (mandatory)

**Architecture Highlights:**
- ✅ **Any Number ≥1:** Works with 1 to 1000+ nodes per role
- ✅ **Partition Tolerant:** Each partition operates independently, heals automatically
- ✅ **Full Replication:** All chunks eventually on all chunkservers (no caps)
- ✅ **Simple:** Proven patterns (gossip, parallel replication, metadata tracking)
- ✅ **Safe:** Deterministic conflict resolution, checksums, repair, idempotent operations
- ✅ **Scalable:** Horizontal scaling for controllers, chunkservers, and CLIs

**Partition Handling:**
- Controllers use gossip + vector clocks to detect and resolve conflicts
- Chunkservers receive writes from controllers (full replication to all available)
- Anti-entropy automatically syncs metadata when partitions heal
- Repair service automatically syncs chunk data when partitions heal
- No manual intervention needed for partition recovery

The implementation prioritizes **availability** and **partition tolerance** with **eventual consistency**, making it ideal for distributed file storage across **multiple hosts** where users value uptime and partition tolerance over strong consistency.

---

## Phase 7: Future Enhancements

❌ **Strong Consistency:**
- Two users uploading to different controllers may temporarily see different file lists
- File metadata changes may take seconds to propagate during normal operation
- During partitions, different partitions have completely different views

❌ **Immediate Consistency:**
- Write to controller-1, immediate read from controller-2 may miss the write
- Gossip latency: 5-30 seconds typical
- Partition healing may take minutes depending on data volume

❌ **Linearizability:**
- Operations are not globally ordered
- Concurrent operations may resolve differently on different controllers
- During partitions, no global ordering exists at all

---

## Phase 7: Future Enhancements

### 6.1 Optimizations
- **Merkle Trees:** Faster anti-entropy by comparing tree hashes
- **Gossip Optimization:** Probabilistic gossip to reduce message overhead
- **Read-Your-Writes:** Sticky sessions so users read from same controller

### 6.2 Advanced Features
- **Erasure Coding:** Replace replication with Reed-Solomon for space efficiency
- **Multi-DC Support:** Replicate across data centers with WAN-aware gossip
- **Stronger Consistency:** Implement Paxos/Raft for critical operations (user auth)

### 6.3 Monitoring
- **Metrics:** Expose Prometheus metrics for gossip lag, replication health
- **Distributed Tracing:** OpenTelemetry for request tracing across nodes
- **Alerting:** Alert on under-replicated chunks, gossip stalls

---

## Summary

This plan transforms RedCloud into a distributed AP system with **full eventual replication**:

1. **Controllers:** Per-controller SQLite (ephemeral) + Gossip + Vector Clocks for eventual consistency
2. **Chunkservers:** Metadata-tracked placement + Parallel replication to ALL servers
3. **Deployment:** `docker run` commands (NO docker-compose, NO docker service) with auto-configuration

**Key Design Principles:**
- **Simple:** Proven patterns (gossip, parallel replication, metadata tracking)
- **Safe:** Deterministic conflict resolution, checksums, repair, idempotent operations
- **Scalable:** Horizontal scaling for controllers, chunkservers, and CLIs
- **Durable:** Full replication - all chunks eventually on all chunkservers
- **Auto-Configured:** No environment variables or volumes required

The implementation prioritizes **availability** and **partition tolerance** with **eventual consistency** and **full replication**, making it suitable for distributed file storage where users value maximum uptime and durability.

---

## Deployment Compatibility Summary

### What Changed from Original Plan

| Aspect | Original Plan | Updated Plan (docker run compatible) |
|--------|--------------|-------------------------------------|
| **Deployment Method** | docker stack deploy + compose file | `docker run` (same command for all instances) |
| **Node IDs** | `{{.Task.Name}}` templating | Auto-generated from container hostname |
| **Advertise Addresses** | Hostname-based (e.g., "controller-1:8000") | IP-based (e.g., "10.0.1.2:8000") |
| **Peer Discovery** | DNS `tasks.controller` (Swarm services) | Gossip via `/internal/peers` endpoint |
| **Environment Variables** | Required per instance | Optional (auto-detected) |
| **Volumes** | Named volumes per replica | Ephemeral (acceptable for dev/demo) |
| **Scripts** | New scripts required | Existing scripts work as-is |

### All Distributed Features Preserved ✅

- ✅ **Multiple controllers** with gossip protocol
- ✅ **Vector clocks** for conflict resolution
- ✅ **Full replication** to all chunkservers
- ✅ **Partition tolerance** and automatic healing
- ✅ **Chunk repair service** with anti-entropy
- ✅ **Heartbeat-based** chunkserver discovery
- ✅ **Last-write-wins** conflict resolution
- ✅ **Eventual consistency** guarantees

### Deployment Commands (No Changes)

```bash
# Existing commands work without modification:
docker run -d --network dfs-network --network-alias controller redcloud-controller:latest
docker run -d --network dfs-network --network-alias chunkserver redcloud-chunkserver:latest

# Or use existing scripts:
./docker/scripts/run-controller.sh
./docker/scripts/scale-chunkserver.sh 5
```

**Result:** Distributed system implementation fully compatible with current `docker run` deployment approach.

---

## Critical Fixes Applied

The following critical issues were identified and fixed in this plan:

### **Fix #1: Peer Registry Gossip** 🔴 **CRITICAL**
- **Issue**: Controller peer registrations were not gossiped to other controllers
- **Impact**: Incomplete peer discovery across cluster
- **Fix**: Added `gossip_service` dependency to `/internal/peers/register` endpoint
- **Location**: Section 1.7, line 501-526

### **Fix #2: Heartbeat Address** ⚠️ **IMPORTANT**
- **Issue**: Heartbeat was sending hostname instead of IP address
- **Impact**: Controllers couldn't connect to chunkservers
- **Fix**: Use `CHUNKSERVER_ADVERTISE_ADDR` (IP-based) in heartbeat payload
- **Location**: Section 2.4, line 1141-1159

### **Fix #3: IP Detection** 🔴 **CRITICAL**
- **Issue**: `gethostbyname()` returns first IP, which might be wrong network
- **Impact**: Controllers/chunkservers advertise unreachable IP addresses
- **Fix**: Use routing table approach (`socket.connect()` to determine interface)
- **Location**: Sections 1.6 (line 455-474), 3.2 (line 1363-1382, 1418-1433)

### **Fix #4: Vector Clock Collision Across Restarts** 🔴 **CRITICAL**
- **Issue**: Same hostname after restart → same vector clock → causality broken
- **Impact**: Conflict resolution invalid across restarts
- **Fix**: Add timestamp to node ID: `f"{hostname}-{int(time.time())}"`
- **Location**: Sections 1.6 (line 478), 3.2 (line 1386, 1437)

### **Fix #7: Chunkserver Failure Detection** 🔴 **CRITICAL**
- **Issue**: No mechanism to detect and mark failed chunkservers
- **Impact**: Reads fail when trying dead chunkservers, no automatic repair
- **Fix**: Added `ChunkserverHealthMonitor` with 30s heartbeat timeout
- **Location**: Section 2.5 (new section, line 1162-1345)

**All critical bugs fixed. System is now production-ready for implementation.**
