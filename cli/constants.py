"""CLI constants and configuration."""

from prompt_toolkit.styles import Style

COMMANDS = ["register", "login", "add", "delete", "list", "add-tags", "delete-tags", "download", "clear", "exit", "help"]

STYLE = Style.from_dict(
    {
        "prompt": "#F45935 bold",
        "command": "#0088ff bold",
    }
)

RED_ORANGE = "\033[38;2;244;89;53m"
RESET = "\033[0m"

LOGO = f"""{RED_ORANGE}
 ██████╗ ███████╗██████╗  ██████╗██╗      ██████╗ ██╗   ██╗██████╗      ██████╗██╗     ██╗
 ██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔═══██╗██║   ██║██╔══██╗    ██╔════╝██║     ██║
 ██████╔╝█████╗  ██║  ██║██║     ██║     ██║   ██║██║   ██║██║  ██║    ██║     ██║     ██║
 ██╔══██╗██╔══╝  ██║  ██║██║     ██║     ██║   ██║██║   ██║██║  ██║    ██║     ██║     ██║
 ██║  ██║███████╗██████╔╝╚██████╗███████╗╚██████╔╝╚██████╔╝██████╔╝    ╚██████╗███████╗██║
 ╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝      ╚═════╝╚══════╝╚═╝
{RESET}"""

WELCOME_TITLE = "RedCloud CLI - Tag-based File System"
WELCOME_HELP = "Type 'help' for commands or 'exit' to quit.\n"

PROMPT_TEXT = "redcloud> "

HELP_TEXT = """Available commands:
  register <username> <password>      Register new user account
  login <username> <password>         Login and get API key
  add file-list tag-list              Add files with tags (files must use uploads/ prefix)
  delete tag-query                    Delete files matching tag query
  list tag-query                      List files matching tag query (empty = all)
  add-tags tag-query tag-list         Add tags to files matching tag query
  delete-tags tag-query tag-list      Remove tags from files matching tag query
  download <filename> [output_path]   Download file (output uses downloads/ prefix or defaults to downloads/)
  clear                               Clear screen and redisplay welcome message
  help                                Show this help
  exit                                Exit REPL

Tag queries use AND logic: 'list tag1 tag2' finds files with BOTH tags.
Use '--' to separate tag-query from tag-list in add-tags/delete-tags.
Examples:
  register alice mypassword123
  login alice mypassword123
  add uploads/file1.txt uploads/file2.txt important work
  list important
  add-tags important -- urgent
  download document.pdf
  download report.txt downloads/renamed.txt
  delete-tags work urgent -- archived
  delete archived"""

SUPPORTED_FILE_EXTENSIONS = (".txt", ".pdf", ".jpg", ".png", ".doc", ".docx", ".csv", ".json", ".xml", ".chk")
