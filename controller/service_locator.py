"""Service locator for distributed components."""

from typing import Optional, TYPE_CHECKING
from controller.replication_manager import ReplicationManager
from controller.chunk_placement import ChunkPlacementManager
from controller.chunkserver_registry import ChunkserverRegistry
from controller.chunkserver_health import ChunkserverHealthMonitor

if TYPE_CHECKING:
    from controller.gossip.gossip_service import GossipService

_replication_manager: Optional[ReplicationManager] = None
_placement_manager: Optional[ChunkPlacementManager] = None
_chunkserver_registry: Optional[ChunkserverRegistry] = None
_health_monitor: Optional[ChunkserverHealthMonitor] = None
_gossip_service: Optional['GossipService'] = None


def set_replication_manager(manager: ReplicationManager):
    """Set global replication manager instance"""
    global _replication_manager
    _replication_manager = manager


def get_replication_manager() -> Optional[ReplicationManager]:
    """Get global replication manager instance"""
    return _replication_manager


def set_placement_manager(manager: ChunkPlacementManager):
    """Set global placement manager instance"""
    global _placement_manager
    _placement_manager = manager


def get_placement_manager() -> Optional[ChunkPlacementManager]:
    """Get global placement manager instance"""
    return _placement_manager


def set_chunkserver_registry(registry: ChunkserverRegistry):
    """Set global chunkserver registry instance"""
    global _chunkserver_registry
    _chunkserver_registry = registry


def get_chunkserver_registry() -> Optional[ChunkserverRegistry]:
    """Get global chunkserver registry instance"""
    return _chunkserver_registry


def set_health_monitor(monitor: ChunkserverHealthMonitor):
    """Set global health monitor instance"""
    global _health_monitor
    _health_monitor = monitor


def get_health_monitor() -> Optional[ChunkserverHealthMonitor]:
    """Get global health monitor instance"""
    return _health_monitor


def set_gossip_service(service):
    """Set global gossip service instance"""
    global _gossip_service
    _gossip_service = service


def get_gossip_service():
    """Get global gossip service instance"""
    return _gossip_service
