"""Shared pytest fixtures for all tests."""

import pytest
from pathlib import Path
from cli.config import Config


@pytest.fixture
def temp_config_dir(tmp_path):
    """
    Create temporary config directory.

    Args:
        tmp_path: pytest tmp_path fixture

    Returns:
        Path to temporary .redcloud directory
    """
    config_dir = tmp_path / '.redcloud'
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def temp_config(temp_config_dir):
    """
    Create temporary config instance.

    Args:
        temp_config_dir: Temporary config directory fixture

    Returns:
        Config instance with temp config file
    """
    return Config(temp_config_dir / 'config.json')


@pytest.fixture
def sample_file(tmp_path):
    """
    Create a sample file for testing file uploads.

    Args:
        tmp_path: pytest tmp_path fixture

    Returns:
        Path to sample text file
    """
    file_path = tmp_path / 'test.txt'
    file_path.write_text('Sample content for testing')
    return file_path


@pytest.fixture
def multiple_sample_files(tmp_path):
    """
    Create multiple sample files for testing bulk operations.

    Args:
        tmp_path: pytest tmp_path fixture

    Returns:
        List of Paths to sample files
    """
    files = []
    for i in range(3):
        file_path = tmp_path / f'test{i}.txt'
        file_path.write_text(f'Sample content {i}')
        files.append(file_path)
    return files
