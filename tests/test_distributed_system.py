"""Simple test to verify distributed system implementation."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_vector_clock():
    """Test vector clock implementation"""
    from controller.vector_clock import VectorClock
    
    vc1 = VectorClock({'node1': 1, 'node2': 0})
    vc2 = VectorClock({'node1': 0, 'node2': 1})
    
    assert vc1.compare(vc2) == 'concurrent', "Concurrent clocks not detected"
    
    vc3 = vc1.increment('node1')
    assert vc3.clock['node1'] == 2, "Increment failed"
    
    merged = vc1.merge(vc2)
    assert merged.clock == {'node1': 1, 'node2': 1}, "Merge failed"
    
    print("✓ VectorClock tests passed")


def test_conflict_resolver():
    """Test conflict resolution"""
    from controller.conflict_resolver import ConflictResolver
    
    local = {
        'file_id': 'f1',
        'vector_clock': '{"node1": 2}',
        'created_at': 100
    }
    
    remote = {
        'file_id': 'f1',
        'vector_clock': '{"node1": 1}',
        'created_at': 90
    }
    
    result = ConflictResolver.resolve(local, remote)
    assert result['action'] == 'keep_local', "Should keep local (causally after)"
    
    concurrent_local = {
        'file_id': 'f1',
        'vector_clock': '{"node1": 1, "node2": 0}',
        'created_at': 100
    }
    
    concurrent_remote = {
        'file_id': 'f1',
        'vector_clock': '{"node1": 0, "node2": 1}',
        'created_at': 110
    }
    
    result = ConflictResolver.resolve(concurrent_local, concurrent_remote)
    assert result['action'] == 'take_remote', "Should take remote (LWW on concurrent)"
    
    print("✓ ConflictResolver tests passed")


def test_database_schema():
    """Test database schema with vector clocks"""
    import tempfile
    import os
    from controller.database import init_database, get_db_connection
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['DFS_DATABASE_PATH'] = os.path.join(tmpdir, 'test.db')
        
        init_database()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            
            assert 'chunk_locations' in tables, "chunk_locations table missing"
            assert 'chunkserver_nodes' in tables, "chunkserver_nodes table missing"
            assert 'controller_nodes' in tables, "controller_nodes table missing"
            assert 'gossip_log' in tables, "gossip_log table missing"
            
            cursor.execute("PRAGMA table_info(files)")
            columns = {row[1] for row in cursor.fetchall()}
            
            assert 'vector_clock' in columns, "vector_clock column missing from files"
            assert 'last_modified_by' in columns, "last_modified_by column missing from files"
            assert 'version' in columns, "version column missing from files"
            assert 'deleted' in columns, "deleted column missing from files"
    
    print("✓ Database schema tests passed")


def test_protocol_messages():
    """Test new protocol messages"""
    from common.protocol import ListChunksRequest, ListChunksResponse, ChunkInfo
    from common.protocol import ReplicateChunkRequest, ReplicateChunkResponse
    
    list_req = ListChunksRequest()
    serialized = list_req.to_json()
    deserialized = ListChunksRequest.from_json(serialized)
    assert deserialized is not None, "ListChunksRequest serialization failed"
    
    chunk_info = ChunkInfo(
        chunk_id='c1',
        file_id='f1',
        chunk_index=0,
        size=1024,
        checksum='abc123'
    )
    
    list_resp = ListChunksResponse(chunks=[chunk_info])
    serialized = list_resp.to_json()
    deserialized = ListChunksResponse.from_json(serialized)
    assert len(deserialized.chunks) == 1, "ListChunksResponse serialization failed"
    assert deserialized.chunks[0].chunk_id == 'c1', "ChunkInfo deserialization failed"
    
    rep_req = ReplicateChunkRequest(
        chunk_id='c1',
        source_chunkserver_address='192.168.1.1:50051'
    )
    serialized = rep_req.to_json()
    deserialized = ReplicateChunkRequest.from_json(serialized)
    assert deserialized.chunk_id == 'c1', "ReplicateChunkRequest serialization failed"
    
    rep_resp = ReplicateChunkResponse(success=True, error=None)
    serialized = rep_resp.to_json()
    deserialized = ReplicateChunkResponse.from_json(serialized)
    assert deserialized.success is True, "ReplicateChunkResponse serialization failed"
    
    print("✓ Protocol message tests passed")


def test_distributed_config():
    """Test distributed configuration"""
    import socket
    from controller.distributed_config import get_container_ip
    
    ip = get_container_ip()
    assert ip is not None, "Failed to get container IP"
    assert len(ip.split('.')) == 4, "Invalid IP format"
    
    print(f"✓ Distributed config tests passed (IP: {ip})")


if __name__ == '__main__':
    print("Running distributed system tests...\n")
    
    try:
        test_vector_clock()
        test_conflict_resolver()
        test_database_schema()
        test_protocol_messages()
        test_distributed_config()
        
        print("\n✅ All tests passed!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
