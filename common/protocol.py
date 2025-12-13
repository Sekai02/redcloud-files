"""Shared RPC/protocol message definitions (serialization formats)."""

from dataclasses import dataclass
from typing import Optional
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
