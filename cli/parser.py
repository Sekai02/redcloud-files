"""Command parser for CLI input."""

import shlex
from typing import Optional

from cli.constants import SUPPORTED_FILE_EXTENSIONS
from cli.models import (
    AddCommand,
    AddTagsCommand,
    CommandRequest,
    DeleteCommand,
    DeleteTagsCommand,
    ListCommand,
    RegisterCommand,
    LoginCommand,
    DownloadCommand,
)


class ParseError(Exception):
    """Raised when command parsing fails."""

    pass


def parse_command(input_line: str) -> CommandRequest:
    """Parse user input into a CommandRequest object.

    Args:
        input_line: Raw user input from REPL

    Returns:
        CommandRequest object (one of Add/Delete/List/AddTags/DeleteTags)

    Raises:
        ParseError: If command syntax is invalid
    """
    if not input_line.strip():
        raise ParseError("Empty command")

    try:
        tokens = shlex.split(input_line)
    except ValueError as e:
        raise ParseError(f"Invalid syntax: {e}")

    if not tokens:
        raise ParseError("Empty command")

    command_name = tokens[0]

    if command_name == "add":
        return _parse_add(tokens[1:])
    elif command_name == "delete":
        return _parse_delete(tokens[1:])
    elif command_name == "list":
        return _parse_list(tokens[1:])
    elif command_name == "add-tags":
        return _parse_add_tags(tokens[1:])
    elif command_name == "delete-tags":
        return _parse_delete_tags(tokens[1:])
    elif command_name == "register":
        return _parse_register(tokens[1:])
    elif command_name == "login":
        return _parse_login(tokens[1:])
    elif command_name == "download":
        return _parse_download(tokens[1:])
    else:
        raise ParseError(f"Unknown command: {command_name}")


def _parse_add(args: list[str]) -> AddCommand:
    """Parse 'add file-list tag-list' command."""
    if len(args) < 2:
        raise ParseError("add requires at least one file and one tag")

    file_list = []
    tag_list = []
    mode: Optional[str] = None

    for arg in args:
        if mode is None:
            file_list.append(arg)
            mode = "files"
        elif mode == "files":
            if arg.startswith("#") or not arg.endswith(SUPPORTED_FILE_EXTENSIONS):
                tag_list.append(arg)
                mode = "tags"
            else:
                file_list.append(arg)
        elif mode == "tags":
            tag_list.append(arg)

    if not file_list:
        raise ParseError("add requires at least one file")
    if not tag_list:
        raise ParseError("add requires at least one tag")

    return AddCommand(file_list=tuple(file_list), tag_list=tuple(tag_list))


def _parse_delete(args: list[str]) -> DeleteCommand:
    """Parse 'delete tag-query' command."""
    if not args:
        raise ParseError("delete requires at least one tag in query")

    return DeleteCommand(tag_query=tuple(args))


def _parse_list(args: list[str]) -> ListCommand:
    """Parse 'list tag-query' command."""
    return ListCommand(tag_query=tuple(args))


def _parse_add_tags(args: list[str]) -> AddTagsCommand:
    """Parse 'add-tags tag-query tag-list' command."""
    if len(args) < 2:
        raise ParseError("add-tags requires tag-query and at least one new tag")

    separator_index = _find_separator(args)

    if separator_index == -1:
        tag_query = tuple(args[:-1])
        tag_list = tuple([args[-1]])
    else:
        tag_query = tuple(args[:separator_index])
        tag_list = tuple(args[separator_index + 1 :])

    if not tag_query:
        raise ParseError("add-tags requires tag-query")
    if not tag_list:
        raise ParseError("add-tags requires at least one new tag")

    return AddTagsCommand(tag_query=tag_query, tag_list=tag_list)


def _parse_delete_tags(args: list[str]) -> DeleteTagsCommand:
    """Parse 'delete-tags tag-query tag-list' command."""
    if len(args) < 2:
        raise ParseError("delete-tags requires tag-query and at least one tag to remove")

    separator_index = _find_separator(args)

    if separator_index == -1:
        tag_query = tuple(args[:-1])
        tag_list = tuple([args[-1]])
    else:
        tag_query = tuple(args[:separator_index])
        tag_list = tuple(args[separator_index + 1 :])

    if not tag_query:
        raise ParseError("delete-tags requires tag-query")
    if not tag_list:
        raise ParseError("delete-tags requires at least one tag to remove")

    return DeleteTagsCommand(tag_query=tag_query, tag_list=tag_list)


def _find_separator(args: list[str]) -> int:
    """Find separator '--' in args, return index or -1."""
    try:
        return args.index("--")
    except ValueError:
        return -1


def _parse_register(args: list[str]) -> RegisterCommand:
    """Parse 'register <username> <password>' command."""
    if len(args) != 2:
        raise ParseError("register requires exactly 2 arguments: <username> <password>")

    username, password = args
    return RegisterCommand(username=username, password=password)


def _parse_login(args: list[str]) -> LoginCommand:
    """Parse 'login <username> <password>' command."""
    if len(args) != 2:
        raise ParseError("login requires exactly 2 arguments: <username> <password>")

    username, password = args
    return LoginCommand(username=username, password=password)


def _parse_download(args: list[str]) -> DownloadCommand:
    """Parse 'download <filename> [output_path]' command."""
    if len(args) < 1:
        raise ParseError("download requires at least 1 argument: <filename> [output_path]")
    
    filename = args[0]
    output_path = args[1] if len(args) > 1 else None
    
    return DownloadCommand(filename=filename, output_path=output_path)
