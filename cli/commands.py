"""Command handler functions for CLI operations."""

from pathlib import Path
from typing import Optional

from cli.models import (
    AddCommand,
    AddTagsCommand,
    DeleteCommand,
    DeleteTagsCommand,
    ListCommand,
    RegisterCommand,
    LoginCommand,
)
from cli.config import Config
from cli.controller_client import ControllerClient


_client: Optional[ControllerClient] = None


def get_client() -> ControllerClient:
    """
    Get or create global ControllerClient instance.

    Returns:
        ControllerClient instance
    """
    global _client
    if _client is None:
        config = Config(Path.home() / '.redcloud' / 'config.json')
        _client = ControllerClient(config)
    return _client


def handle_register(cmd: RegisterCommand, client: Optional[ControllerClient] = None) -> str:
    """
    Handle 'register' command.

    Args:
        cmd: RegisterCommand with username and password
        client: Optional ControllerClient for dependency injection (testing)

    Returns:
        Success or error message
    """
    if client is None:
        client = get_client()
    return client.register(cmd.username, cmd.password)


def handle_login(cmd: LoginCommand, client: Optional[ControllerClient] = None) -> str:
    """
    Handle 'login' command.

    Args:
        cmd: LoginCommand with username and password
        client: Optional ControllerClient for dependency injection (testing)

    Returns:
        Success or error message
    """
    if client is None:
        client = get_client()
    return client.login(cmd.username, cmd.password)


def handle_add(cmd: AddCommand, client: Optional[ControllerClient] = None) -> str:
    """
    Handle 'add' command.

    Args:
        cmd: AddCommand with file_list and tag_list
        client: Optional ControllerClient for dependency injection (testing)

    Returns:
        Success or error message with upload results
    """
    if client is None:
        client = get_client()
    return client.add_files(list(cmd.file_list), list(cmd.tag_list))


def handle_delete(cmd: DeleteCommand, client: Optional[ControllerClient] = None) -> str:
    """
    Handle 'delete' command.

    Args:
        cmd: DeleteCommand with tag_query
        client: Optional ControllerClient for dependency injection (testing)

    Returns:
        Success or error message with deletion results
    """
    if client is None:
        client = get_client()
    return client.delete_files(list(cmd.tag_query))


def handle_list(cmd: ListCommand, client: Optional[ControllerClient] = None) -> str:
    """
    Handle 'list' command.

    Args:
        cmd: ListCommand with tag_query
        client: Optional ControllerClient for dependency injection (testing)

    Returns:
        Formatted list of files
    """
    if client is None:
        client = get_client()
    return client.list_files(list(cmd.tag_query))


def handle_add_tags(cmd: AddTagsCommand, client: Optional[ControllerClient] = None) -> str:
    """
    Handle 'add-tags' command.

    Args:
        cmd: AddTagsCommand with tag_query and tag_list
        client: Optional ControllerClient for dependency injection (testing)

    Returns:
        Success or error message with update results
    """
    if client is None:
        client = get_client()
    return client.add_tags(list(cmd.tag_query), list(cmd.tag_list))


def handle_delete_tags(cmd: DeleteTagsCommand, client: Optional[ControllerClient] = None) -> str:
    """
    Handle 'delete-tags' command.

    Args:
        cmd: DeleteTagsCommand with tag_query and tag_list
        client: Optional ControllerClient for dependency injection (testing)

    Returns:
        Success or error message with update results
    """
    if client is None:
        client = get_client()
    return client.delete_tags(list(cmd.tag_query), list(cmd.tag_list))
