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


CommandRequest = AddCommand | DeleteCommand | ListCommand | AddTagsCommand | DeleteTagsCommand