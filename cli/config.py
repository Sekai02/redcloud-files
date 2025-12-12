"""Configuration management for RedCloud CLI."""

import json
import os
import shutil
from pathlib import Path
from typing import Optional


class Config:
    """Manages CLI configuration stored in JSON file."""

    DEFAULT_CONFIG = {
        "controller_host": os.environ.get("DFS_CONTROLLER_HOST", "controller"),
        "controller_port": int(os.environ.get("DFS_CONTROLLER_PORT", "8000")),
        "timeout": 30,
        "max_retries": 3,
        "retry_backoff_multiplier": 2,
    }

    def __init__(self, config_path: Path):
        """
        Initialize configuration manager.

        Args:
            config_path: Path to config JSON file (typically ~/.redcloud/config.json)
        """
        self.config_path = config_path
        self.data = self._load()

    def _load(self) -> dict:
        """
        Load configuration from file, creating defaults if necessary.

        Returns:
            Configuration dictionary
        """
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            import tempfile
            self.config_path = Path(tempfile.gettempdir()) / '.redcloud' / 'config.json'
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                config = self.DEFAULT_CONFIG.copy()
                config.update(data)
                return config
            except (json.JSONDecodeError, IOError) as e:
                backup_path = self.config_path.with_suffix('.json.bak')
                try:
                    shutil.copy(self.config_path, backup_path)
                except:
                    pass
                return self.DEFAULT_CONFIG.copy()
        else:
            config = self.DEFAULT_CONFIG.copy()
            try:
                with open(self.config_path, 'w') as f:
                    json.dump(config, f, indent=2)
            except IOError:
                pass
            return config

    def save(self) -> None:
        """Save current configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.data, f, indent=2)
        except IOError as e:
            pass

    def get_api_key(self) -> Optional[str]:
        """
        Get stored API key.

        Returns:
            API key string or None if not set
        """
        return self.data.get('api_key')

    def set_api_key(self, key: str) -> None:
        """
        Set API key and save to file.

        Args:
            key: API key string (format: "dfs_<uuid>")
        """
        self.data['api_key'] = key
        self.save()

    def get_base_url(self) -> str:
        """
        Get controller base URL.

        Returns:
            Base URL string (e.g., "http://localhost:8000")
        """
        host = self.data.get('controller_host', 'localhost')
        port = self.data.get('controller_port', 8000)
        return f"http://{host}:{port}"

    def get_timeout(self) -> int:
        """
        Get request timeout in seconds.

        Returns:
            Timeout value in seconds
        """
        return self.data.get('timeout', 30)

    def get_retry_config(self) -> dict:
        """
        Get retry configuration.

        Returns:
            Dictionary with 'max_retries' and 'retry_backoff_multiplier'
        """
        return {
            'max_retries': self.data.get('max_retries', 3),
            'retry_backoff_multiplier': self.data.get('retry_backoff_multiplier', 2),
        }
