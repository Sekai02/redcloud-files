"""REPL with prompt_toolkit for user interaction."""

import os
import sys
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory

from cli.commands import (
    handle_add,
    handle_add_tags,
    handle_delete,
    handle_delete_tags,
    handle_list,
)
from cli.constants import (
    COMMANDS,
    HELP_TEXT,
    LOGO,
    PROMPT_TEXT,
    STYLE,
    WELCOME_HELP,
    WELCOME_TITLE,
)
from cli.models import (
    AddCommand,
    AddTagsCommand,
    DeleteCommand,
    DeleteTagsCommand,
    ListCommand,
)
from cli.parser import ParseError, parse_command


def clear_screen() -> None:
    """Clear the terminal screen (cross-platform)."""
    if sys.platform == "win32":
        os.system("cls")
    else:
        os.system("clear")


def show_logo() -> None:
    """Display RedCloud logo with ANSI colors."""
    print(LOGO)


def dispatch_command(cmd_obj) -> str:
    """Dispatch parsed command to appropriate handler."""
    if isinstance(cmd_obj, AddCommand):
        return handle_add(cmd_obj)
    elif isinstance(cmd_obj, DeleteCommand):
        return handle_delete(cmd_obj)
    elif isinstance(cmd_obj, ListCommand):
        return handle_list(cmd_obj)
    elif isinstance(cmd_obj, AddTagsCommand):
        return handle_add_tags(cmd_obj)
    elif isinstance(cmd_obj, DeleteTagsCommand):
        return handle_delete_tags(cmd_obj)
    else:
        return f"Unknown command type: {type(cmd_obj)}"


def repl_loop() -> None:
    """Start interactive REPL with prompt_toolkit."""
    completer = WordCompleter(COMMANDS, ignore_case=True)
    history = InMemoryHistory()
    session: PromptSession = PromptSession(
        completer=completer, history=history, style=STYLE
    )

    clear_screen()
    show_logo()
    print(WELCOME_TITLE)
    print(WELCOME_HELP)

    while True:
        try:
            user_input = session.prompt([("class:prompt", PROMPT_TEXT)])

            if not user_input.strip():
                continue

            if user_input.strip() == "exit":
                print("Goodbye!")
                break

            if user_input.strip() == "help":
                print(HELP_TEXT)
                continue

            if user_input.strip() == "clear":
                clear_screen()
                show_logo()
                print(WELCOME_TITLE)
                print(WELCOME_HELP)
                continue

            cmd_obj = parse_command(user_input)
            result = dispatch_command(cmd_obj)
            print(result)

        except ParseError as e:
            print(f"Error: {e}")
        except KeyboardInterrupt:
            continue
        except EOFError:
            print("\nGoodbye!")
            break
