"""
Configuration management for MCP servers.

Provides hierarchical configuration with support for:
- Default values
- YAML/JSON configuration files
- Environment variable overrides
- Runtime parameter overrides
- Dot notation access
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    logger.warning("PyYAML not available. YAML configuration files not supported.")


class ConfigManager:
    """
    Hierarchical configuration manager for MCP servers.

    Configuration precedence (highest to lowest):
    1. Runtime overrides (set via set() method)
    2. Environment variables
    3. Configuration file (YAML/JSON)
    4. Default values
    """

    def __init__(
        self,
        config_file: Optional[Union[str, Path]] = None,
        defaults: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize configuration manager.

        Args:
            config_file: Path to configuration file (YAML or JSON)
            defaults: Default configuration values
        """
        self._defaults = defaults or {}
        self._file_config = {}
        self._env_config = {}
        self._runtime_config = {}

        # Load configuration file if provided
        if config_file:
            self.load_file(config_file)

        # Load environment variables
        self._load_env_vars()

    def load_file(self, config_file: Union[str, Path]) -> None:
        """Load configuration from file."""
        config_path = Path(config_file)

        if not config_path.exists():
            logger.warning(f"Configuration file not found: {config_path}")
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                if config_path.suffix.lower() in [".yaml", ".yml"]:
                    if not HAS_YAML:
                        raise ValueError("PyYAML not available for YAML configuration")
                    self._file_config = yaml.safe_load(f) or {}
                elif config_path.suffix.lower() == ".json":
                    self._file_config = json.load(f) or {}
                else:
                    raise ValueError(
                        f"Unsupported configuration file format: {config_path.suffix}"
                    )

            logger.info(f"Loaded configuration from {config_path}")

        except Exception as e:
            logger.error(f"Failed to load configuration file {config_path}: {e}")
            self._file_config = {}

    def _load_env_vars(self) -> None:
        """Load configuration from environment variables."""
        # Look for environment variables with MCP_ prefix
        env_config = {}

        for key, value in os.environ.items():
            if key.startswith("MCP_"):
                # Convert MCP_SERVER_NAME to server.name
                config_key = key[4:].lower().replace("_", ".")

                # Try to parse as JSON, fall back to string
                try:
                    parsed_value = json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    parsed_value = value

                self._set_nested_value(env_config, config_key, parsed_value)

        self._env_config = env_config

    def _set_nested_value(self, config: Dict[str, Any], key: str, value: Any) -> None:
        """Set a nested configuration value using dot notation."""
        keys = key.split(".")
        current = config

        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.

        Args:
            key: Configuration key (e.g., "server.cache.ttl")
            default: Default value if key not found

        Returns:
            Configuration value
        """
        # Check in order of precedence
        for config in [
            self._runtime_config,
            self._env_config,
            self._file_config,
            self._defaults,
        ]:
            value = self._get_nested_value(config, key)
            if value is not None:
                return value

        return default

    def _get_nested_value(self, config: Dict[str, Any], key: str) -> Any:
        """Get nested value using dot notation."""
        keys = key.split(".")
        current = config

        try:
            for k in keys:
                current = current[k]
            return current
        except (KeyError, TypeError):
            return None

    def set(self, key: str, value: Any) -> None:
        """Set runtime configuration value using dot notation."""
        self._set_nested_value(self._runtime_config, key, value)

    def update(self, config: Dict[str, Any]) -> None:
        """Update runtime configuration with dictionary."""
        for key, value in config.items():
            self.set(key, value)

    def to_dict(self) -> Dict[str, Any]:
        """Get complete configuration as dictionary."""
        result = {}

        # Merge all configurations in reverse precedence order
        for config in [
            self._defaults,
            self._file_config,
            self._env_config,
            self._runtime_config,
        ]:
            result = self._deep_merge(result, config)

        return result

    def _deep_merge(
        self, base: Dict[str, Any], update: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deep merge two dictionaries."""
        result = base.copy()

        for key, value in update.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def save(self, config_file: Union[str, Path], format: str = "yaml") -> None:
        """
        Save current configuration to file.

        Args:
            config_file: Path to save configuration
            format: File format ('yaml' or 'json')
        """
        config_path = Path(config_file)
        config_data = self.to_dict()

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                if format.lower() == "yaml":
                    if not HAS_YAML:
                        raise ValueError("PyYAML not available for YAML export")
                    yaml.dump(config_data, f, default_flow_style=False, indent=2)
                elif format.lower() == "json":
                    json.dump(config_data, f, indent=2)
                else:
                    raise ValueError(f"Unsupported format: {format}")

            logger.info(f"Configuration saved to {config_path}")

        except Exception as e:
            logger.error(f"Failed to save configuration to {config_path}: {e}")
            raise


def create_default_config() -> Dict[str, Any]:
    """Create default MCP server configuration."""
    return {
        "server": {
            "name": "mcp-server",
            "version": "1.0.0",
            "description": "MCP Server",
            "transport": "stdio",
        },
        "cache": {"enabled": True, "default_ttl": 300, "max_size": 128},
        "metrics": {
            "enabled": True,
            "collect_performance": True,
            "collect_usage": True,
        },
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    }


def load_config_file(config_file: Union[str, Path]) -> ConfigManager:
    """
    Convenience function to load configuration from file.

    Args:
        config_file: Path to configuration file

    Returns:
        ConfigManager instance with loaded configuration
    """
    defaults = create_default_config()
    return ConfigManager(config_file=config_file, defaults=defaults)
