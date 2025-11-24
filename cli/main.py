"""CLI entry point: REPL with prompt_toolkit."""

import os
import sys
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style

from cli.commands import (
    handle_add,
    handle_add_tags,
    handle_delete,
    handle_delete_tags,
    handle_list,
)
from cli.parser import ParseError, parse_command
from cli.models import (
    AddCommand,
    AddTagsCommand,
    DeleteCommand,
    DeleteTagsCommand,
    ListCommand,
)


COMMANDS = ["add", "delete", "list", "add-tags", "delete-tags", "clear", "exit", "help"]

STYLE = Style.from_dict(
    {
        "prompt": "#F45935 bold",
        "command": "#0088ff bold",
    }
)

HELP_TEXT = """Available commands:
  add file-list tag-list       Add files with tags
  delete tag-query             Delete files matching tag query
  list tag-query               List files matching tag query (empty = all)
  add-tags tag-query tag-list  Add tags to files matching tag query
  delete-tags tag-query tag-list  Remove tags from files matching tag query
  clear                        Clear screen and redisplay welcome message
  help                         Show this help
  exit                         Exit REPL

Tag queries use AND logic: 'list tag1 tag2' finds files with BOTH tags.
Use '--' to separate tag-query from tag-list in add-tags/delete-tags.
Examples:
  add file1.txt file2.txt important work
  list important
  add-tags important -- urgent
  delete-tags work urgent -- archived
  delete archived"""


def clear_screen() -> None:
    """Clear the terminal screen (cross-platform)."""
    if sys.platform == "win32":
        os.system("cls")
    else:
        os.system("clear")


def show_logo() -> None:
    """Display RedCloud logo with ANSI colors."""
    # ANSI color codes: \033[38;2;R;G;Bm for RGB colors
    # Git-like red-orange: RGB(244, 89, 53) or #F45935
    RED_ORANGE = "\033[38;2;244;89;53m"
    RESET = "\033[0m"

    logo = f"""{RED_ORANGE}
 ██████╗ ███████╗██████╗  ██████╗██╗      ██████╗ ██╗   ██╗██████╗      ██████╗██╗     ██╗
 ██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔═══██╗██║   ██║██╔══██╗    ██╔════╝██║     ██║
 ██████╔╝█████╗  ██║  ██║██║     ██║     ██║   ██║██║   ██║██║  ██║    ██║     ██║     ██║
 ██╔══██╗██╔══╝  ██║  ██║██║     ██║     ██║   ██║██║   ██║██║  ██║    ██║     ██║     ██║
 ██║  ██║███████╗██████╔╝╚██████╗███████╗╚██████╔╝╚██████╔╝██████╔╝    ╚██████╗███████╗██║
 ╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝      ╚═════╝╚══════╝╚═╝
{RESET}"""
    print(logo)


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
    print("RedCloud CLI - Tag-based File System")
    print("Type 'help' for commands or 'exit' to quit.\n")

    while True:
        try:
            user_input = session.prompt([("class:prompt", "redcloud> ")])

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
                print("RedCloud CLI - Tag-based File System")
                print("Type 'help' for commands or 'exit' to quit.\n")
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


def main() -> None:
    """Entry point for CLI."""
    repl_loop()


if __name__ == "__main__":
    main()
