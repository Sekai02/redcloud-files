"""Shared RPC/protocol message definitions (serialization formats)."""

from dataclasses import dataclass
from typing import Optional, List, Dict
import json
import base64


@dataclass
class ChunkMetadata:
    """Metadata for a chunk operation."""
    chunk_id: str
    file_id: str
    chunk_index: int
    total_size: int
    checksum: str
    
    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps(self.__dict__).encode('utf-8')
    
    @classmethod
    def from_json(cls, data: bytes) -> 'ChunkMetadata':
        """Deserialize from JSON bytes."""
        return cls(**json.loads(data))


@dataclass
class ChunkDataPiece:
    """A piece of chunk data for streaming."""
    data: bytes
    
    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'data': base64.b64encode(self.data).decode('ascii')
        }).encode('utf-8')
    
    @classmethod
    def from_json(cls, data: bytes) -> 'ChunkDataPiece':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(data=base64.b64decode(obj['data']))


@dataclass
class WriteChunkRequest:
    """Request message for WriteChunk RPC (streaming)."""
    metadata: Optional[ChunkMetadata] = None
    data: Optional[ChunkDataPiece] = None
    
    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        obj = {}
        if self.metadata:
            obj['metadata'] = self.metadata.__dict__
        if self.data:
            obj['data'] = base64.b64encode(self.data.data).decode('ascii')
        return json.dumps(obj).encode('utf-8')
    
    @classmethod
    def from_json(cls, data: bytes) -> 'WriteChunkRequest':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        metadata = ChunkMetadata(**obj['metadata']) if 'metadata' in obj else None
        data_piece = ChunkDataPiece(data=base64.b64decode(obj['data'])) if 'data' in obj else None
        return cls(metadata=metadata, data=data_piece)


@dataclass
class WriteChunkResponse:
    """Response message for WriteChunk RPC."""
    success: bool
    error_message: Optional[str] = None
    
    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'success': self.success,
            'error_message': self.error_message
        }).encode('utf-8')
    
    @classmethod
    def from_json(cls, data: bytes) -> 'WriteChunkResponse':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(success=obj['success'], error_message=obj.get('error_message'))


@dataclass
class ReadChunkRequest:
    """Request message for ReadChunk RPC."""
    chunk_id: str
    
    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({'chunk_id': self.chunk_id}).encode('utf-8')
    
    @classmethod
    def from_json(cls, data: bytes) -> 'ReadChunkRequest':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(chunk_id=obj['chunk_id'])


@dataclass
class ReadChunkResponse:
    """Response message for ReadChunk RPC (streaming)."""
    metadata: Optional[ChunkMetadata] = None
    data: Optional[ChunkDataPiece] = None
    
    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        obj = {}
        if self.metadata:
            obj['metadata'] = self.metadata.__dict__
        if self.data:
            obj['data'] = base64.b64encode(self.data.data).decode('ascii')
        return json.dumps(obj).encode('utf-8')
    
    @classmethod
    def from_json(cls, data: bytes) -> 'ReadChunkResponse':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        metadata = ChunkMetadata(**obj['metadata']) if 'metadata' in obj else None
        data_piece = ChunkDataPiece(data=base64.b64decode(obj['data'])) if 'data' in obj else None
        return cls(metadata=metadata, data=data_piece)


@dataclass
class DeleteChunkRequest:
    """Request message for DeleteChunk RPC."""
    chunk_id: str
    
    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({'chunk_id': self.chunk_id}).encode('utf-8')
    
    @classmethod
    def from_json(cls, data: bytes) -> 'DeleteChunkRequest':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(chunk_id=obj['chunk_id'])


@dataclass
class DeleteChunkResponse:
    """Response message for DeleteChunk RPC."""
    success: bool
    error_message: Optional[str] = None
    
    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'success': self.success,
            'error_message': self.error_message
        }).encode('utf-8')
    
    @classmethod
    def from_json(cls, data: bytes) -> 'DeleteChunkResponse':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(success=obj['success'], error_message=obj.get('error_message'))


@dataclass
class PingRequest:
    """Request message for Ping RPC (optional health check)."""
    pass
    
    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({}).encode('utf-8')
    
    @classmethod
    def from_json(cls, data: bytes) -> 'PingRequest':
        """Deserialize from JSON bytes."""
        return cls()


@dataclass
class PingResponse:
    """Response message for Ping RPC."""
    available: bool

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({'available': self.available}).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'PingResponse':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(available=obj['available'])


@dataclass
class OperationSummary:
    """Summary of a user operation for gossip protocol."""
    operation_id: str
    operation_type: str
    user_id: str
    timestamp_ms: int
    vector_clock: Dict[str, int]

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'operation_id': self.operation_id,
            'operation_type': self.operation_type,
            'user_id': self.user_id,
            'timestamp_ms': self.timestamp_ms,
            'vector_clock': self.vector_clock
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'OperationSummary':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            operation_id=obj['operation_id'],
            operation_type=obj['operation_type'],
            user_id=obj['user_id'],
            timestamp_ms=obj['timestamp_ms'],
            vector_clock=obj['vector_clock']
        )


@dataclass
class Operation:
    """Full operation with payload for replication."""
    operation_id: str
    operation_type: str
    user_id: str
    timestamp_ms: int
    vector_clock: Dict[str, int]
    payload: Dict
    applied: int
    created_at: str

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'operation_id': self.operation_id,
            'operation_type': self.operation_type,
            'user_id': self.user_id,
            'timestamp_ms': self.timestamp_ms,
            'vector_clock': self.vector_clock,
            'payload': self.payload,
            'applied': self.applied,
            'created_at': self.created_at
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'Operation':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            operation_id=obj['operation_id'],
            operation_type=obj['operation_type'],
            user_id=obj['user_id'],
            timestamp_ms=obj['timestamp_ms'],
            vector_clock=obj['vector_clock'],
            payload=obj['payload'],
            applied=obj['applied'],
            created_at=obj['created_at']
        )


@dataclass
class GossipMessage:
    """Message for gossip protocol."""
    sender_id: str
    sender_address: str
    vector_clock: Dict[str, int]
    operation_summaries: List[OperationSummary]

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'sender_id': self.sender_id,
            'sender_address': self.sender_address,
            'vector_clock': self.vector_clock,
            'operation_summaries': [
                {
                    'operation_id': op.operation_id,
                    'operation_type': op.operation_type,
                    'user_id': op.user_id,
                    'timestamp_ms': op.timestamp_ms,
                    'vector_clock': op.vector_clock
                }
                for op in self.operation_summaries
            ]
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'GossipMessage':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            sender_id=obj['sender_id'],
            sender_address=obj['sender_address'],
            vector_clock=obj['vector_clock'],
            operation_summaries=[
                OperationSummary(
                    operation_id=op['operation_id'],
                    operation_type=op['operation_type'],
                    user_id=op['user_id'],
                    timestamp_ms=op['timestamp_ms'],
                    vector_clock=op['vector_clock']
                )
                for op in obj['operation_summaries']
            ]
        )


@dataclass
class GossipResponse:
    """Response for gossip protocol."""
    peer_id: str
    vector_clock: Dict[str, int]
    missing_operation_ids: List[str]

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'peer_id': self.peer_id,
            'vector_clock': self.vector_clock,
            'missing_operation_ids': self.missing_operation_ids
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'GossipResponse':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            peer_id=obj['peer_id'],
            vector_clock=obj['vector_clock'],
            missing_operation_ids=obj['missing_operation_ids']
        )


@dataclass
class StateSummary:
    """State summary for anti-entropy protocol."""
    peer_id: str
    vector_clock: Dict[str, int]
    operation_ids: List[str]

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'peer_id': self.peer_id,
            'vector_clock': self.vector_clock,
            'operation_ids': self.operation_ids
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'StateSummary':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            peer_id=obj['peer_id'],
            vector_clock=obj['vector_clock'],
            operation_ids=obj['operation_ids']
        )


@dataclass
class FetchOperationsRequest:
    """Request to fetch specific operations."""
    operation_ids: List[str]

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({'operation_ids': self.operation_ids}).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'FetchOperationsRequest':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(operation_ids=obj['operation_ids'])


@dataclass
class FetchOperationsResponse:
    """Response with requested operations."""
    operations: List[Operation]

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'operations': [
                {
                    'operation_id': op.operation_id,
                    'operation_type': op.operation_type,
                    'user_id': op.user_id,
                    'timestamp_ms': op.timestamp_ms,
                    'vector_clock': op.vector_clock,
                    'payload': op.payload,
                    'applied': op.applied,
                    'created_at': op.created_at
                }
                for op in self.operations
            ]
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'FetchOperationsResponse':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            operations=[
                Operation(
                    operation_id=op['operation_id'],
                    operation_type=op['operation_type'],
                    user_id=op['user_id'],
                    timestamp_ms=op['timestamp_ms'],
                    vector_clock=op['vector_clock'],
                    payload=op['payload'],
                    applied=op['applied'],
                    created_at=op['created_at']
                )
                for op in obj['operations']
            ]
        )


@dataclass
class PushOperationsRequest:
    """Request to push operations to peer."""
    operations: List[Operation]

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'operations': [
                {
                    'operation_id': op.operation_id,
                    'operation_type': op.operation_type,
                    'user_id': op.user_id,
                    'timestamp_ms': op.timestamp_ms,
                    'vector_clock': op.vector_clock,
                    'payload': op.payload,
                    'applied': op.applied,
                    'created_at': op.created_at
                }
                for op in self.operations
            ]
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'PushOperationsRequest':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            operations=[
                Operation(
                    operation_id=op['operation_id'],
                    operation_type=op['operation_type'],
                    user_id=op['user_id'],
                    timestamp_ms=op['timestamp_ms'],
                    vector_clock=op['vector_clock'],
                    payload=op['payload'],
                    applied=op['applied'],
                    created_at=op['created_at']
                )
                for op in obj['operations']
            ]
        )


@dataclass
class PushOperationsResponse:
    """Response for push operations."""
    success: bool
    error_message: Optional[str] = None

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'success': self.success,
            'error_message': self.error_message
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'PushOperationsResponse':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(success=obj['success'], error_message=obj.get('error_message'))


@dataclass
class GetStateSummaryRequest:
    """Request to get state summary."""
    pass

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({}).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'GetStateSummaryRequest':
        """Deserialize from JSON bytes."""
        return cls()


@dataclass
class QueryChunkLivenessRequest:
    """Request to query if a chunk is still referenced by any files."""
    chunk_id: str

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({'chunk_id': self.chunk_id}).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'QueryChunkLivenessRequest':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(chunk_id=obj['chunk_id'])


@dataclass
class QueryChunkLivenessResponse:
    """Response with chunk liveness status."""
    chunk_id: str
    is_live: bool
    referenced_by_files: List[str]

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'chunk_id': self.chunk_id,
            'is_live': self.is_live,
            'referenced_by_files': self.referenced_by_files
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'QueryChunkLivenessResponse':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            chunk_id=obj['chunk_id'],
            is_live=obj['is_live'],
            referenced_by_files=obj['referenced_by_files']
        )


@dataclass
class ChunkSummary:
    """Lightweight chunk metadata for gossip protocol."""
    chunk_id: str
    checksum: str
    size: int

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'chunk_id': self.chunk_id,
            'checksum': self.checksum,
            'size': self.size
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'ChunkSummary':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            chunk_id=obj['chunk_id'],
            checksum=obj['checksum'],
            size=obj['size']
        )


@dataclass
class TombstoneEntry:
    """Represents a deleted chunk to prevent resurrection after partitions."""
    chunk_id: str
    deleted_at: str
    checksum: str

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'chunk_id': self.chunk_id,
            'deleted_at': self.deleted_at,
            'checksum': self.checksum
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'TombstoneEntry':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            chunk_id=obj['chunk_id'],
            deleted_at=obj['deleted_at'],
            checksum=obj['checksum']
        )


@dataclass
class ChunkGossipMessage:
    """Gossip message exchanged between chunkserver peers."""
    sender_address: str
    chunk_summaries: List[ChunkSummary]
    tombstones: List[TombstoneEntry]

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'sender_address': self.sender_address,
            'chunk_summaries': [
                {
                    'chunk_id': cs.chunk_id,
                    'checksum': cs.checksum,
                    'size': cs.size
                }
                for cs in self.chunk_summaries
            ],
            'tombstones': [
                {
                    'chunk_id': ts.chunk_id,
                    'deleted_at': ts.deleted_at,
                    'checksum': ts.checksum
                }
                for ts in self.tombstones
            ]
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'ChunkGossipMessage':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            sender_address=obj['sender_address'],
            chunk_summaries=[
                ChunkSummary(
                    chunk_id=cs['chunk_id'],
                    checksum=cs['checksum'],
                    size=cs['size']
                )
                for cs in obj['chunk_summaries']
            ],
            tombstones=[
                TombstoneEntry(
                    chunk_id=ts['chunk_id'],
                    deleted_at=ts['deleted_at'],
                    checksum=ts['checksum']
                )
                for ts in obj['tombstones']
            ]
        )


@dataclass
class ChunkGossipResponse:
    """Response to chunk gossip message indicating missing chunks."""
    peer_address: str
    missing_chunk_ids: List[str]

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'peer_address': self.peer_address,
            'missing_chunk_ids': self.missing_chunk_ids
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'ChunkGossipResponse':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            peer_address=obj['peer_address'],
            missing_chunk_ids=obj['missing_chunk_ids']
        )


@dataclass
class ChunkStateSummary:
    """Complete state summary for anti-entropy reconciliation."""
    peer_address: str
    chunk_ids: List[str]
    tombstone_ids: List[str]
    chunk_count: int
    total_size_bytes: int

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'peer_address': self.peer_address,
            'chunk_ids': self.chunk_ids,
            'tombstone_ids': self.tombstone_ids,
            'chunk_count': self.chunk_count,
            'total_size_bytes': self.total_size_bytes
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'ChunkStateSummary':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            peer_address=obj['peer_address'],
            chunk_ids=obj['chunk_ids'],
            tombstone_ids=obj['tombstone_ids'],
            chunk_count=obj['chunk_count'],
            total_size_bytes=obj['total_size_bytes']
        )


@dataclass
class FetchChunkRequest:
    """Request to fetch specific chunk data from peer for replication."""
    chunk_id: str

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({'chunk_id': self.chunk_id}).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'FetchChunkRequest':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(chunk_id=obj['chunk_id'])


@dataclass
class FetchChunkResponse:
    """Response containing chunk metadata for replication transfer."""
    chunk_id: str
    checksum: str
    size: int
    exists: bool
    error_message: Optional[str] = None

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'chunk_id': self.chunk_id,
            'checksum': self.checksum,
            'size': self.size,
            'exists': self.exists,
            'error_message': self.error_message
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'FetchChunkResponse':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            chunk_id=obj['chunk_id'],
            checksum=obj['checksum'],
            size=obj['size'],
            exists=obj['exists'],
            error_message=obj.get('error_message')
        )


@dataclass
class PushTombstonesRequest:
    """Request to push deletion tombstones to peer."""
    tombstones: List[TombstoneEntry]

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'tombstones': [
                {
                    'chunk_id': ts.chunk_id,
                    'deleted_at': ts.deleted_at,
                    'checksum': ts.checksum
                }
                for ts in self.tombstones
            ]
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'PushTombstonesRequest':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            tombstones=[
                TombstoneEntry(
                    chunk_id=ts['chunk_id'],
                    deleted_at=ts['deleted_at'],
                    checksum=ts['checksum']
                )
                for ts in obj['tombstones']
            ]
        )


@dataclass
class PushTombstonesResponse:
    """Response to tombstone push operation."""
    success: bool
    processed_count: int
    error_message: Optional[str] = None

    def to_json(self) -> bytes:
        """Serialize to JSON bytes."""
        return json.dumps({
            'success': self.success,
            'processed_count': self.processed_count,
            'error_message': self.error_message
        }).encode('utf-8')

    @classmethod
    def from_json(cls, data: bytes) -> 'PushTombstonesResponse':
        """Deserialize from JSON bytes."""
        obj = json.loads(data)
        return cls(
            success=obj['success'],
            processed_count=obj['processed_count'],
            error_message=obj.get('error_message')
        )
