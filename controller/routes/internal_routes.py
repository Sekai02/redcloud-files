"""Internal routes for gossip and peer discovery."""

from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from controller.gossip.gossip_service import GossipService
from controller.gossip.peer_registry import PeerRegistry
from controller.chunkserver_registry import ChunkserverRegistry
from controller.distributed_config import CONTROLLER_NODE_ID, CONTROLLER_ADVERTISE_ADDR
from common.logging_config import get_logger
import time

logger = get_logger(__name__)

router = APIRouter(prefix="/internal")

_gossip_service: GossipService = None
_peer_registry: PeerRegistry = None
_chunkserver_registry: ChunkserverRegistry = None


def set_gossip_service(service: GossipService):
    """Set the global gossip service instance"""
    global _gossip_service
    _gossip_service = service


def set_peer_registry(registry: PeerRegistry):
    """Set the global peer registry instance"""
    global _peer_registry
    _peer_registry = registry


def set_chunkserver_registry(registry: ChunkserverRegistry):
    """Set the global chunkserver registry instance"""
    global _chunkserver_registry
    _chunkserver_registry = registry


def get_gossip_service() -> GossipService:
    """Dependency to get gossip service"""
    return _gossip_service


def get_peer_registry() -> PeerRegistry:
    """Dependency to get peer registry"""
    return _peer_registry


def get_chunkserver_registry() -> ChunkserverRegistry:
    """Dependency to get chunkserver registry"""
    return _chunkserver_registry

@router.get("/peers")
async def get_peers(peer_registry: PeerRegistry = Depends(get_peer_registry)):
    """
    Return list of known controller peers.
    Used by new controllers to bootstrap peer discovery.
    """
    return {
        "peers": peer_registry.get_all_peers() if peer_registry else [],
        "self": {
            "node_id": CONTROLLER_NODE_ID,
            "address": CONTROLLER_ADVERTISE_ADDR
        }
    }


@router.post("/peers/register")
async def register_peer(
    peer_info: Dict[str, str],
    peer_registry: PeerRegistry = Depends(get_peer_registry),
    gossip_service: GossipService = Depends(get_gossip_service)
):
    """
    Allow controllers to register themselves.
    CRITICAL: Gossips registration to all other controllers.
    """
    node_id = peer_info["node_id"]
    address = peer_info["address"]

    await peer_registry.add_peer(node_id, address)

    if gossip_service:
        await gossip_service.add_to_gossip_log(
            entity_type="controller_peer",
            entity_id=node_id,
            operation="register",
            data={
                "node_id": node_id,
                "address": address,
                "last_seen": time.time(),
                "vector_clock": "{}"
            }
        )

    logger.info(f"Registered peer: {node_id} @ {address}")
    return {"status": "registered"}


@router.post("/peers/unregister")
async def unregister_peer(
    peer_info: Dict[str, str],
    peer_registry: PeerRegistry = Depends(get_peer_registry),
    gossip_service: GossipService = Depends(get_gossip_service)
):
    """
    Allow controllers to gracefully unregister themselves.
    Gossips removal to all other controllers.
    """
    node_id = peer_info["node_id"]

    await peer_registry.remove_peer(node_id)

    if gossip_service:
        await gossip_service.add_to_gossip_log(
            entity_type="controller_peer_remove",
            entity_id=node_id,
            operation="unregister",
            data={
                "node_id": node_id,
                "timestamp": time.time()
            }
        )

    logger.info(f"Unregistered peer: {node_id}")
    return {"status": "unregistered"}


@router.post("/gossip/receive")
async def receive_gossip_updates(
    payload: Dict[str, Any],
    gossip_service: GossipService = Depends(get_gossip_service)
):
    """Receive gossip updates from peer controller"""
    if gossip_service:
        await gossip_service.receive_gossip(
            sender_node_id=payload['sender_node_id'],
            updates=payload['updates']
        )
    return {"status": "ok"}


@router.get("/gossip/state-summary")
async def get_state_summary():
    """Return summary of local state for anti-entropy"""
    from controller.database import get_db_connection
    
    summary = {
        'files': {},
        'users': {},
        'chunks': {}
    }
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT file_id, vector_clock, version FROM files WHERE deleted = 0")
        for row in cursor.fetchall():
            summary['files'][row['file_id']] = {
                'vector_clock': row['vector_clock'] or '{}',
                'version': row['version'] or 0
            }
        
        cursor.execute("SELECT user_id, vector_clock, version FROM users")
        for row in cursor.fetchall():
            summary['users'][row['user_id']] = {
                'vector_clock': row['vector_clock'] or '{}',
                'version': row['version'] or 0
            }
        
        cursor.execute("SELECT chunk_id, vector_clock, version FROM chunks")
        for row in cursor.fetchall():
            summary['chunks'][row['chunk_id']] = {
                'vector_clock': row['vector_clock'] or '{}',
                'version': row['version'] or 0
            }
    
    return {"status": "ok", "summary": summary}


@router.get("/gossip/entity/{entity_type}/{entity_id}")
async def get_entity(entity_type: str, entity_id: str):
    """Return full entity data for anti-entropy pull"""
    from controller.database import get_db_connection
    from controller.repositories.tag_repository import TagRepository
    from controller.repositories.chunk_repository import ChunkRepository
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if entity_type == 'file':
            cursor.execute("SELECT * FROM files WHERE file_id = ?", (entity_id,))
            row = cursor.fetchone()
            if not row:
                return {"status": "not_found"}
            
            tags = TagRepository.get_tags_for_file(entity_id)
            chunks = ChunkRepository.get_chunks_by_file(entity_id)
            
            chunk_locations = {}
            for chunk in chunks:
                cursor.execute(
                    "SELECT chunkserver_id FROM chunk_locations WHERE chunk_id = ?",
                    (chunk.chunk_id,)
                )
                loc_rows = cursor.fetchall()
                chunk_locations[chunk.chunk_id] = [r["chunkserver_id"] for r in loc_rows]
            
            return {
                "status": "ok",
                "entity": {
                    'file_id': row['file_id'],
                    'name': row['name'],
                    'size': row['size'],
                    'owner_id': row['owner_id'],
                    'created_at': row['created_at'],
                    'deleted': row['deleted'],
                    'tags': tags,
                    'chunks': [
                        {
                            'chunk_id': c.chunk_id,
                            'chunk_index': c.chunk_index,
                            'size': c.size,
                            'checksum': c.checksum
                        }
                        for c in chunks
                    ],
                    'chunk_locations': chunk_locations,
                    'vector_clock': row['vector_clock'] or '{}',
                    'last_modified_by': row['last_modified_by'],
                    'version': row['version'] or 0
                }
            }
        
        elif entity_type == 'user':
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (entity_id,))
            row = cursor.fetchone()
            if not row:
                return {"status": "not_found"}
            
            return {
                "status": "ok",
                "entity": {
                    'user_id': row['user_id'],
                    'username': row['username'],
                    'password_hash': row['password_hash'],
                    'api_key': row['api_key'],
                    'created_at': row['created_at'],
                    'key_updated_at': row['key_updated_at'],
                    'vector_clock': row['vector_clock'] or '{}',
                    'last_modified_by': row['last_modified_by'],
                    'version': row['version'] or 0
                }
            }
        
        elif entity_type == 'chunk':
            cursor.execute("SELECT * FROM chunks WHERE chunk_id = ?", (entity_id,))
            row = cursor.fetchone()
            if not row:
                return {"status": "not_found"}
            
            return {
                "status": "ok",
                "entity": {
                    'chunk_id': row['chunk_id'],
                    'file_id': row['file_id'],
                    'chunk_index': row['chunk_index'],
                    'size': row['size'],
                    'checksum': row['checksum'],
                    'vector_clock': row['vector_clock'] or '{}',
                    'last_modified_by': row['last_modified_by'],
                    'version': row['version'] or 0
                }
            }
    
    return {"status": "not_found"}


@router.post("/chunkserver/heartbeat")
async def chunkserver_heartbeat(
    heartbeat_data: Dict[str, Any],
    chunkserver_registry: ChunkserverRegistry = Depends(get_chunkserver_registry),
    gossip_service: GossipService = Depends(get_gossip_service)
):
    """
    Receive heartbeat from chunkserver.
    Updates registry and gossips to other controllers.
    """
    node_id = heartbeat_data["node_id"]
    address = heartbeat_data["address"]
    capacity_bytes = heartbeat_data.get("capacity_bytes", 0)
    used_bytes = heartbeat_data.get("used_bytes", 0)

    if chunkserver_registry:
        await chunkserver_registry.update_chunkserver(
            node_id=node_id,
            address=address,
            capacity_bytes=capacity_bytes,
            used_bytes=used_bytes
        )

    if gossip_service:
        await gossip_service.add_to_gossip_log(
            entity_type="chunkserver",
            entity_id=node_id,
            operation="heartbeat",
            data={
                "node_id": node_id,
                "address": address,
                "last_heartbeat": time.time(),
                "capacity_bytes": capacity_bytes,
                "used_bytes": used_bytes,
                "status": "active"
            }
        )

    logger.debug(f"Received heartbeat from chunkserver {node_id} @ {address}")
    return {"status": "ok"}
