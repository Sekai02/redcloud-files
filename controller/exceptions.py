"""Custom exception classes for the Controller."""


class DFSException(Exception):
    """
    Base exception class for all DFS-related errors.
    """
    pass


class UserAlreadyExistsError(DFSException):
    """
    Raised when attempting to register a username that already exists.
    """
    pass


class InvalidCredentialsError(DFSException):
    """
    Raised when login credentials are invalid.
    """
    pass


class InvalidAPIKeyError(DFSException):
    """
    Raised when an API Key is invalid or expired.
    """
    pass


class FileNotFoundError(DFSException):
    """
    Raised when a requested file does not exist.
    """
    pass


class UnauthorizedAccessError(DFSException):
    """
    Raised when a user attempts to access a file they don't own.
    """
    pass


class ChunkserverUnavailableError(DFSException):
    """
    Raised when the Chunkserver is unreachable or unavailable.
    """
    pass


class EmptyTagListError(DFSException):
    """
    Raised when attempting to create or update a file with an empty tag list.
    """
    pass


class InvalidTagQueryError(DFSException):
    """
    Raised when a tag query is malformed or invalid.
    """
    pass


class StorageFullError(DFSException):
    """
    Raised when the Chunkserver reports insufficient storage space.
    """
    pass


class ChecksumMismatchError(DFSException):
    """
    Raised when chunk checksum verification fails.
    """
    pass
