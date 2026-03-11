"""Plugin system for progressive enhancement of Nexus.

This module implements a plugin architecture that allows users to
progressively enhance their Nexus instance with additional features
like authentication, monitoring, and enterprise capabilities.
"""

import importlib
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


class NexusPlugin(ABC):
    """Base class for Nexus plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Plugin description."""
        pass

    @abstractmethod
    def apply(self, nexus_instance: Any) -> None:
        """Apply plugin to the Nexus instance.

        Args:
            nexus_instance: The Nexus instance to enhance
        """
        pass

    def validate(self) -> bool:
        """Validate plugin can be applied.

        Performs basic validation checks:
        - Plugin has valid name
        - Plugin has callable apply method
        - Subclasses can override for additional validation

        Returns:
            True if plugin can be applied, False otherwise
        """
        # Validate plugin has a name
        try:
            name = self.name
            if not name or not isinstance(name, str):
                logger.error(f"Plugin validation failed: invalid name '{name}'")
                return False
        except Exception as e:
            logger.error(f"Plugin validation failed: unable to get name - {e}")
            return False

        # Validate plugin has apply method
        if not hasattr(self, "apply") or not callable(getattr(self, "apply", None)):
            logger.error(
                f"Plugin '{name}' validation failed: missing or invalid apply method"
            )
            return False

        # Validation passed
        logger.debug(f"Plugin '{name}' validation passed")
        return True


class AuthPlugin(NexusPlugin):
    """Authentication plugin using SDK's MiddlewareAuthManager."""

    @property
    def name(self) -> str:
        return "auth"

    @property
    def description(self) -> str:
        return "Enables authentication using SDK enterprise auth components"

    def apply(self, nexus_instance: Any) -> None:
        """Apply authentication using SDK components."""
        logger.info("Applying authentication plugin with SDK components")

        # Use SDK's enterprise authentication
        if hasattr(nexus_instance, "_gateway") and nexus_instance._gateway:
            try:
                from kailash.middleware.auth.auth_manager import MiddlewareAuthManager

                # Initialize SDK auth manager
                auth_manager = MiddlewareAuthManager(
                    enable_api_keys=True, enable_audit=True
                )

                # Integrate with gateway (if supported)
                if hasattr(nexus_instance._gateway, "set_auth_manager"):
                    nexus_instance._gateway.set_auth_manager(auth_manager)

                nexus_instance._auth_enabled = True
                nexus_instance._auth_manager = auth_manager

                logger.info("SDK-based authentication enabled")

            except ImportError as e:
                logger.warning(f"SDK auth components not available: {e}")
                # Fallback to simple flag
                nexus_instance._auth_enabled = True


class MonitoringPlugin(NexusPlugin):
    """Built-in monitoring plugin."""

    @property
    def name(self) -> str:
        return "monitoring"

    @property
    def description(self) -> str:
        return "Adds performance monitoring and metrics collection"

    def apply(self, nexus_instance: Any) -> None:
        """Apply monitoring to Nexus."""
        logger.info("Applying monitoring plugin")

        # Add monitoring configuration
        nexus_instance._monitoring_enabled = True
        nexus_instance._metrics = {}

        # Hook into workflow execution for metrics
        logger.info("Monitoring enabled")


class RateLimitPlugin(NexusPlugin):
    """Rate limiting plugin."""

    def __init__(self, requests_per_minute: int = 60):
        """Initialize rate limit plugin.

        Args:
            requests_per_minute: Maximum requests per minute
        """
        self.requests_per_minute = requests_per_minute

    @property
    def name(self) -> str:
        return "rate_limit"

    @property
    def description(self) -> str:
        return f"Adds rate limiting ({self.requests_per_minute} req/min)"

    def apply(self, nexus_instance: Any) -> None:
        """Apply rate limiting."""
        logger.info(f"Applying rate limit plugin: {self.requests_per_minute} req/min")
        nexus_instance._rate_limit = self.requests_per_minute


class PluginRegistry:
    """Registry for managing Nexus plugins."""

    def __init__(self):
        """Initialize plugin registry."""
        self._plugins: Dict[str, NexusPlugin] = {}
        self._load_builtin_plugins()

    def _load_builtin_plugins(self):
        """Load built-in plugins."""
        self.register(AuthPlugin())
        self.register(MonitoringPlugin())
        self.register(RateLimitPlugin())

    def register(self, plugin: NexusPlugin) -> None:
        """Register a plugin.

        Args:
            plugin: Plugin instance to register
        """
        if not isinstance(plugin, NexusPlugin):
            raise ValueError("Plugin must inherit from NexusPlugin")

        if not plugin.validate():
            raise ValueError(f"Plugin {plugin.name} validation failed")

        self._plugins[plugin.name] = plugin
        logger.info(f"Registered plugin: {plugin.name}")

    def get(self, name: str) -> Optional[NexusPlugin]:
        """Get a plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None if not found
        """
        return self._plugins.get(name)

    def list(self) -> List[str]:
        """List all available plugins.

        Returns:
            List of plugin names
        """
        return list(self._plugins.keys())

    def apply(self, name: str, nexus_instance: Any) -> None:
        """Apply a plugin to Nexus instance.

        Args:
            name: Plugin name
            nexus_instance: Nexus instance
        """
        plugin = self.get(name)
        if not plugin:
            raise ValueError(f"Plugin '{name}' not found")

        plugin.apply(nexus_instance)
        logger.info(f"Applied plugin: {name}")


class PluginLoader:
    """Loads external plugins from filesystem."""

    PLUGIN_PATTERNS = [
        "nexus_plugins/*.py",
        "plugins/*.py",
        "*_plugin.py",
    ]

    @staticmethod
    def load_from_directory(directory: str = None) -> Dict[str, NexusPlugin]:
        """Load plugins from directory.

        Args:
            directory: Directory to search (defaults to current)

        Returns:
            Dictionary of loaded plugins
        """
        directory = Path(directory or os.getcwd())
        plugins = {}

        for pattern in PluginLoader.PLUGIN_PATTERNS:
            for file_path in directory.glob(pattern):
                if file_path.name.startswith("_"):
                    continue

                try:
                    plugin = PluginLoader._load_plugin_from_file(file_path)
                    if plugin:
                        plugins[plugin.name] = plugin
                except Exception as e:
                    logger.warning(f"Failed to load plugin from {file_path}: {e}")

        return plugins

    @staticmethod
    def _load_plugin_from_file(file_path: Path) -> Optional[NexusPlugin]:
        """Load a plugin from a Python file.

        Args:
            file_path: Path to plugin file

        Returns:
            Plugin instance or None
        """
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        if not spec or not spec.loader:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Look for NexusPlugin subclasses
        for name, obj in vars(module).items():
            if (
                isinstance(obj, type)
                and issubclass(obj, NexusPlugin)
                and obj is not NexusPlugin
            ):
                try:
                    return obj()
                except TypeError as e:
                    # Plugin constructor requires arguments
                    logger.warning(
                        f"Cannot instantiate plugin {name} from {file_path}: "
                        f"constructor requires arguments ({e})"
                    )
                except Exception as e:
                    # Plugin initialization failed
                    logger.error(
                        f"Failed to instantiate plugin {name} from {file_path}: "
                        f"{type(e).__name__}: {e}"
                    )

        return None


# Global plugin registry
_registry = None


def get_plugin_registry() -> PluginRegistry:
    """Get or create the global plugin registry.

    Returns:
        Global PluginRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = PluginRegistry()

        # Load external plugins
        external = PluginLoader.load_from_directory()
        for plugin in external.values():
            try:
                _registry.register(plugin)
            except Exception as e:
                logger.warning(f"Failed to register external plugin {plugin.name}: {e}")

    return _registry
