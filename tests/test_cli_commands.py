"""Tests for CLI command handlers."""

import pytest
from unittest.mock import Mock
from cli.commands import (
    handle_register,
    handle_login,
    handle_add,
    handle_delete,
    handle_list,
    handle_add_tags,
    handle_delete_tags,
)
from cli.models import (
    RegisterCommand,
    LoginCommand,
    AddCommand,
    DeleteCommand,
    ListCommand,
    AddTagsCommand,
    DeleteTagsCommand,
)
from cli.controller_client import ControllerClient


def test_handle_register():
    """Test register command handler with mocked client."""
    mock_client = Mock(spec=ControllerClient)
    mock_client.register.return_value = "Registration successful!"

    cmd = RegisterCommand(username='testuser', password='password123')
    result = handle_register(cmd, client=mock_client)

    assert 'Registration successful' in result
    mock_client.register.assert_called_once_with('testuser', 'password123')


def test_handle_login():
    """Test login command handler with mocked client."""
    mock_client = Mock(spec=ControllerClient)
    mock_client.login.return_value = "Login successful!"

    cmd = LoginCommand(username='testuser', password='password123')
    result = handle_login(cmd, client=mock_client)

    assert 'Login successful' in result
    mock_client.login.assert_called_once_with('testuser', 'password123')


def test_handle_add():
    """Test add command handler with mocked client."""
    mock_client = Mock(spec=ControllerClient)
    mock_client.add_files.return_value = "Added: test.txt (ID: file123..., Size: 100 bytes, Tags: tag1, tag2)"

    cmd = AddCommand(file_list=('test.txt', 'test2.txt'), tag_list=('tag1', 'tag2'))
    result = handle_add(cmd, client=mock_client)

    assert 'Added' in result
    mock_client.add_files.assert_called_once_with(['test.txt', 'test2.txt'], ['tag1', 'tag2'])


def test_handle_list():
    """Test list command handler with mocked client."""
    mock_client = Mock(spec=ControllerClient)
    mock_client.list_files.return_value = "Found 1 file(s)"

    cmd = ListCommand(tag_query=('tag1', 'tag2'))
    result = handle_list(cmd, client=mock_client)

    assert 'Found' in result
    mock_client.list_files.assert_called_once_with(['tag1', 'tag2'])


def test_handle_list_empty_query():
    """Test list command handler with empty query."""
    mock_client = Mock(spec=ControllerClient)
    mock_client.list_files.return_value = "Found 5 file(s)"

    cmd = ListCommand(tag_query=())
    result = handle_list(cmd, client=mock_client)

    assert 'Found' in result
    mock_client.list_files.assert_called_once_with([])


def test_handle_delete():
    """Test delete command handler with mocked client."""
    mock_client = Mock(spec=ControllerClient)
    mock_client.delete_files.return_value = "Deleted 2 file(s)"

    cmd = DeleteCommand(tag_query=('tag1', 'tag2'))
    result = handle_delete(cmd, client=mock_client)

    assert 'Deleted' in result
    mock_client.delete_files.assert_called_once_with(['tag1', 'tag2'])


def test_handle_add_tags():
    """Test add-tags command handler with mocked client."""
    mock_client = Mock(spec=ControllerClient)
    mock_client.add_tags.return_value = "Added tags [newtag] to 3 file(s)"

    cmd = AddTagsCommand(tag_query=('tag1', 'tag2'), tag_list=('newtag',))
    result = handle_add_tags(cmd, client=mock_client)

    assert 'Added tags' in result
    mock_client.add_tags.assert_called_once_with(['tag1', 'tag2'], ['newtag'])


def test_handle_delete_tags():
    """Test delete-tags command handler with mocked client."""
    mock_client = Mock(spec=ControllerClient)
    mock_client.delete_tags.return_value = "Removed tags [oldtag] from 2 file(s)"

    cmd = DeleteTagsCommand(tag_query=('tag1',), tag_list=('oldtag',))
    result = handle_delete_tags(cmd, client=mock_client)

    assert 'Removed tags' in result
    mock_client.delete_tags.assert_called_once_with(['tag1'], ['oldtag'])
