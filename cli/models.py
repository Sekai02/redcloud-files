"""Command request and response data types for CLI."""

from dataclasses import dataclass
from typing import Callable, Literal


@dataclass(frozen=True)
class AddCommand:
    """Add files with tags."""

    file_list: tuple[str, ...]
    tag_list: tuple[str, ...]
    command: Literal["add"] = "add"


@dataclass(frozen=True)
class DeleteCommand:
    """Delete files matching tag query."""

    tag_query: tuple[str, ...]
    command: Literal["delete"] = "delete"


@dataclass(frozen=True)
class ListCommand:
    """List files matching tag query."""

    tag_query: tuple[str, ...]
    command: Literal["list"] = "list"


@dataclass(frozen=True)
class AddTagsCommand:
    """Add tags to files matching tag query."""

    tag_query: tuple[str, ...]
    tag_list: tuple[str, ...]
    command: Literal["add-tags"] = "add-tags"


@dataclass(frozen=True)
class DeleteTagsCommand:
    """Remove tags from files matching tag query."""

    tag_query: tuple[str, ...]
    tag_list: tuple[str, ...]
    command: Literal["delete-tags"] = "delete-tags"


@dataclass(frozen=True)
class RegisterCommand:
    """Register a new user account."""

    username: str
    password: str
    command: Literal["register"] = "register"


@dataclass(frozen=True)
class LoginCommand:
    """Login with username and password."""

    username: str
    password: str
    command: Literal["login"] = "login"


@dataclass(frozen=True)
class DownloadCommand:
    """Download file by filename."""

    filename: str
    output_path: str | None = None
    command: Literal["download"] = "download"


CommandRequest = (
    AddCommand
    | DeleteCommand
    | ListCommand
    | AddTagsCommand
    | DeleteTagsCommand
    | RegisterCommand
    | LoginCommand
    | DownloadCommand
)