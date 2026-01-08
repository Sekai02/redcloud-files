"""Tests for RedCloudCompleter."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from prompt_toolkit.document import Document

from cli.completer import RedCloudCompleter
from cli.constants import COMMANDS, UPLOADS_DIR


@pytest.fixture
def completer():
    """Create a RedCloudCompleter instance."""
    return RedCloudCompleter()


@pytest.fixture
def uploads_dir(tmp_path):
    """
    Create a temporary uploads directory with test files.

    Returns:
        Path to the temporary uploads directory
    """
    uploads = tmp_path / UPLOADS_DIR
    uploads.mkdir()
    (uploads / "document.txt").write_text("content")
    (uploads / "image.png").write_text("content")
    (uploads / "data.csv").write_text("content")
    (uploads / "unsupported.xyz").write_text("content")
    return uploads


def get_completions_list(completer, text):
    """Helper to get list of completion texts from completer."""
    doc = Document(text, len(text))
    return [c.text for c in completer.get_completions(doc, None)]


def get_completions_display(completer, text):
    """Helper to get list of completion display texts from completer."""
    doc = Document(text, len(text))
    return [c.display for c in completer.get_completions(doc, None)]


class TestCommandCompletion:
    """Tests for command name completion."""

    def test_empty_input_shows_all_commands(self, completer):
        """Empty input should suggest all commands."""
        completions = get_completions_list(completer, "")
        for cmd in COMMANDS:
            assert cmd in completions

    def test_partial_command_filters(self, completer):
        """Partial command should filter to matching commands."""
        completions = get_completions_list(completer, "add")
        assert "add" in completions
        assert "add-tags" in completions
        assert "delete" not in completions

    def test_command_completion_case_insensitive(self, completer):
        """Command completion should be case insensitive."""
        completions = get_completions_list(completer, "ADD")
        assert "add" in completions
        assert "add-tags" in completions


class TestFileCompletion:
    """Tests for file path completion in add command."""

    def test_add_command_shows_uploads_files(self, completer, uploads_dir):
        """After 'add ', should show files from uploads/ directory."""
        with patch.object(Path, "cwd", return_value=uploads_dir.parent):
            completions = get_completions_list(completer, "add ")
            assert "uploads/document.txt" in completions
            assert "uploads/image.png" in completions
            assert "uploads/data.csv" in completions

    def test_filters_unsupported_extensions(self, completer, uploads_dir):
        """Should not show files with unsupported extensions."""
        with patch.object(Path, "cwd", return_value=uploads_dir.parent):
            completions = get_completions_list(completer, "add ")
            assert "uploads/unsupported.xyz" not in completions

    def test_partial_path_filters_files(self, completer, uploads_dir):
        """Partial path should filter matching files."""
        with patch.object(Path, "cwd", return_value=uploads_dir.parent):
            completions = get_completions_list(completer, "add uploads/d")
            assert "uploads/document.txt" in completions
            assert "uploads/data.csv" in completions
            assert "uploads/image.png" not in completions

    def test_excludes_already_typed_files(self, completer, uploads_dir):
        """Files already in command should not be suggested again."""
        with patch.object(Path, "cwd", return_value=uploads_dir.parent):
            completions = get_completions_list(
                completer, "add uploads/document.txt "
            )
            assert "uploads/document.txt" not in completions
            assert "uploads/image.png" in completions

    def test_non_add_command_no_file_completion(self, completer, uploads_dir):
        """Non-add commands should not trigger file completion."""
        with patch.object(Path, "cwd", return_value=uploads_dir.parent):
            completions = get_completions_list(completer, "delete ")
            assert not any("uploads/" in c for c in completions)


class TestEmptyUploadsHandling:
    """Tests for empty or missing uploads directory."""

    def test_missing_uploads_shows_message(self, completer, tmp_path):
        """Missing uploads/ directory should show helpful message."""
        with patch.object(Path, "cwd", return_value=tmp_path):
            displays = get_completions_display(completer, "add ")
            assert any("no files found" in str(d) for d in displays)

    def test_empty_uploads_shows_message(self, completer, tmp_path):
        """Empty uploads/ directory should show helpful message."""
        empty_uploads = tmp_path / UPLOADS_DIR
        empty_uploads.mkdir()
        with patch.object(Path, "cwd", return_value=tmp_path):
            displays = get_completions_display(completer, "add ")
            assert any("no files found" in str(d) for d in displays)

    def test_only_unsupported_files_shows_message(self, completer, tmp_path):
        """Directory with only unsupported files should show message."""
        uploads = tmp_path / UPLOADS_DIR
        uploads.mkdir()
        (uploads / "file.xyz").write_text("content")
        (uploads / "file.abc").write_text("content")
        with patch.object(Path, "cwd", return_value=tmp_path):
            displays = get_completions_display(completer, "add ")
            assert any("no files found" in str(d) for d in displays)


class TestCaseInsensitiveExtensions:
    """Tests for case-insensitive file extension matching."""

    def test_uppercase_extension_matches(self, completer, tmp_path):
        """Files with uppercase extensions should be included."""
        uploads = tmp_path / UPLOADS_DIR
        uploads.mkdir()
        (uploads / "FILE.TXT").write_text("content")
        (uploads / "IMAGE.PNG").write_text("content")
        with patch.object(Path, "cwd", return_value=tmp_path):
            completions = get_completions_list(completer, "add ")
            assert "uploads/FILE.TXT" in completions
            assert "uploads/IMAGE.PNG" in completions
