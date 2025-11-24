"""Command handler functions for CLI operations."""

from cli.models import (
    AddCommand,
    AddTagsCommand,
    DeleteCommand,
    DeleteTagsCommand,
    ListCommand,
)


def handle_add(cmd: AddCommand) -> str:
    """Handle 'add' command."""
    files_str = ", ".join(cmd.file_list)
    tags_str = ", ".join(cmd.tag_list)
    return f"[MOCK] Adding files [{files_str}] with tags [{tags_str}]"


def handle_delete(cmd: DeleteCommand) -> str:
    """Handle 'delete' command."""
    query_str = " AND ".join(cmd.tag_query) if cmd.tag_query else "ALL"
    return f"[MOCK] Deleting files matching: {query_str}"


def handle_list(cmd: ListCommand) -> str:
    """Handle 'list' command."""
    query_str = " AND ".join(cmd.tag_query) if cmd.tag_query else "ALL"
    return f"[MOCK] Listing files matching: {query_str}"


def handle_add_tags(cmd: AddTagsCommand) -> str:
    """Handle 'add-tags' command."""
    query_str = " AND ".join(cmd.tag_query)
    tags_str = ", ".join(cmd.tag_list)
    return f"[MOCK] Adding tags [{tags_str}] to files matching: {query_str}"


def handle_delete_tags(cmd: DeleteTagsCommand) -> str:
    """Handle 'delete-tags' command."""
    query_str = " AND ".join(cmd.tag_query)
    tags_str = ", ".join(cmd.tag_list)
    return f"[MOCK] Removing tags [{tags_str}] from files matching: {query_str}"
