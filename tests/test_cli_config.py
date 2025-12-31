"""Tests for CLI configuration module."""

import json
import pytest
from pathlib import Path
from cli.config import Config


def test_config_creates_default_file(tmp_path):
    """Test that config file is created with defaults if missing."""
    config_path = tmp_path / '.redcloud' / 'config.json'
    config = Config(config_path)

    assert config_path.exists()

    assert config.data['controller_host'] == 'localhost'
    assert config.data['controller_port'] == 8000
    assert config.data['timeout'] == 30
    assert config.data['max_retries'] == 3
    assert config.data['retry_backoff_multiplier'] == 2
    assert 'api_key' not in config.data


def test_config_loads_existing_file(tmp_path):
    """Test loading existing config file."""
    config_path = tmp_path / '.redcloud' / 'config.json'
    config_path.parent.mkdir(parents=True)

    existing_data = {
        'api_key': 'dfs_test123',
        'controller_host': 'example.com',
        'controller_port': 9000,
    }
    with open(config_path, 'w') as f:
        json.dump(existing_data, f)

    config = Config(config_path)

    assert config.data['api_key'] == 'dfs_test123'
    assert config.data['controller_host'] == 'example.com'
    assert config.data['controller_port'] == 9000

    assert config.data['timeout'] == 30
    assert config.data['max_retries'] == 3


def test_config_save_and_get_api_key(temp_config):
    """Test saving and retrieving API key."""
    assert temp_config.get_api_key() is None

    test_key = 'dfs_abc123'
    temp_config.set_api_key(test_key)

    assert temp_config.get_api_key() == test_key

    with open(temp_config.config_path, 'r') as f:
        data = json.load(f)
    assert data['api_key'] == test_key


def test_config_handles_corrupted_file(tmp_path):
    """Test recovery from corrupted config file."""
    config_path = tmp_path / '.redcloud' / 'config.json'
    config_path.parent.mkdir(parents=True)

    with open(config_path, 'w') as f:
        f.write('{ invalid json content')

    config = Config(config_path)
    assert config.data['controller_host'] == 'localhost'
    assert config.data['controller_port'] == 8000

    backup_path = config_path.with_suffix('.json.bak')
    assert backup_path.exists()


def test_config_get_base_url(temp_config):
    """Test base URL construction."""
    assert temp_config.get_base_url() == 'http://localhost:8000'

    temp_config.data['controller_host'] = 'example.com'
    temp_config.data['controller_port'] = 9000
    assert temp_config.get_base_url() == 'http://example.com:9000'


def test_config_get_timeout(temp_config):
    """Test timeout retrieval."""
    assert temp_config.get_timeout() == 30

    temp_config.data['timeout'] = 60
    assert temp_config.get_timeout() == 60


def test_config_get_retry_config(temp_config):
    """Test retry configuration retrieval."""
    retry_config = temp_config.get_retry_config()

    assert retry_config['max_retries'] == 3
    assert retry_config['retry_backoff_multiplier'] == 2

    temp_config.data['max_retries'] = 5
    temp_config.data['retry_backoff_multiplier'] = 3

    retry_config = temp_config.get_retry_config()
    assert retry_config['max_retries'] == 5
    assert retry_config['retry_backoff_multiplier'] == 3


def test_config_directory_created_if_missing(tmp_path):
    """Test that config directory is created if it doesn't exist."""
    config_path = tmp_path / 'nested' / 'deep' / '.redcloud' / 'config.json'

    assert not config_path.parent.exists()

    config = Config(config_path)
    assert config_path.parent.exists()
    assert config_path.exists()
