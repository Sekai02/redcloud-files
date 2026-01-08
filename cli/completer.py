"""Custom completer for RedCloud CLI with file autocompletion."""

from pathlib import Path
from typing import Iterable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from cli.constants import COMMANDS, SUPPORTED_FILE_EXTENSIONS, UPLOADS_DIR


class RedCloudCompleter(Completer):
    """
    Custom completer that provides:
    - Command name completion for the first token
    - File path completion for the 'add' command from uploads/ directory
    """

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        """
        Generate completions based on cursor position and context.

        For the first token, completes command names.
        For 'add' command arguments, completes files from uploads/ directory.
        """
        text = document.text_before_cursor
        tokens = text.split()

        is_typing_new_token = text.endswith(" ") or not tokens

        if not tokens or (len(tokens) == 1 and not is_typing_new_token):
            yield from self._complete_commands(tokens[0] if tokens else "")
            return

        command = tokens[0].lower()
        if command != "add":
            return

        current_word = "" if is_typing_new_token else tokens[-1]
        already_typed_files = set(
            t for t in tokens[1:] if t.startswith(f"{UPLOADS_DIR}/")
        )
        if not is_typing_new_token and current_word in already_typed_files:
            already_typed_files.discard(current_word)

        yield from self._complete_uploads_files(current_word, already_typed_files)

    def _complete_commands(self, partial: str) -> Iterable[Completion]:
        """Complete command names matching the partial input."""
        partial_lower = partial.lower()
        for cmd in COMMANDS:
            if cmd.startswith(partial_lower):
                yield Completion(cmd, start_position=-len(partial))

    def _complete_uploads_files(
        self, partial: str, exclude_files: set
    ) -> Iterable[Completion]:
        """
        Complete file paths from the uploads/ directory.

        Only includes files with supported extensions in the root of uploads/.
        Shows a message if no files are available.
        """
        uploads_path = Path.cwd() / UPLOADS_DIR

        if not uploads_path.exists() or not uploads_path.is_dir():
            if not partial or UPLOADS_DIR.startswith(partial):
                yield Completion(
                    "",
                    start_position=0,
                    display="(no files found - uploads/ directory missing)",
                )
            return

        available_files = []
        for item in uploads_path.iterdir():
            if not item.is_file():
                continue
            if not item.name.lower().endswith(SUPPORTED_FILE_EXTENSIONS):
                continue
            rel_path = f"{UPLOADS_DIR}/{item.name}"
            if rel_path in exclude_files:
                continue
            available_files.append(rel_path)

        if not available_files:
            if not partial or partial.startswith(UPLOADS_DIR) or UPLOADS_DIR.startswith(partial):
                yield Completion(
                    "",
                    start_position=0,
                    display="(no files found in uploads/)",
                )
            return

        partial_lower = partial.lower()
        for file_path in sorted(available_files):
            if file_path.lower().startswith(partial_lower):
                yield Completion(file_path, start_position=-len(partial))
