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
