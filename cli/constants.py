"""CLI constants and configuration."""

from prompt_toolkit.styles import Style

# Available commands for autocomplete
COMMANDS = ["add", "delete", "list", "add-tags", "delete-tags", "clear", "exit", "help"]

# Prompt toolkit style
STYLE = Style.from_dict(
    {
        "prompt": "#F45935 bold",
        "command": "#0088ff bold",
    }
)

# ANSI color codes
RED_ORANGE = "\033[38;2;244;89;53m"
RESET = "\033[0m"

# ASCII logo
LOGO = f"""{RED_ORANGE}
 ██████╗ ███████╗██████╗  ██████╗██╗      ██████╗ ██╗   ██╗██████╗      ██████╗██╗     ██╗
 ██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔═══██╗██║   ██║██╔══██╗    ██╔════╝██║     ██║
 ██████╔╝█████╗  ██║  ██║██║     ██║     ██║   ██║██║   ██║██║  ██║    ██║     ██║     ██║
 ██╔══██╗██╔══╝  ██║  ██║██║     ██║     ██║   ██║██║   ██║██║  ██║    ██║     ██║     ██║
 ██║  ██║███████╗██████╔╝╚██████╗███████╗╚██████╔╝╚██████╔╝██████╔╝    ╚██████╗███████╗██║
 ╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝      ╚═════╝╚══════╝╚═╝
{RESET}"""

# Welcome messages
WELCOME_TITLE = "RedCloud CLI - Tag-based File System"
WELCOME_HELP = "Type 'help' for commands or 'exit' to quit.\n"

# Prompt text
PROMPT_TEXT = "redcloud> "

# Help text
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

# Supported file extensions for add command parsing
SUPPORTED_FILE_EXTENSIONS = (".txt", ".pdf", ".jpg", ".png", ".doc", ".docx", ".csv", ".json", ".xml", ".chk")
