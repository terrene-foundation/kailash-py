"""Unit tests for Nexus plugin system.

Tests the plugin architecture that allows progressive enhancement
of Nexus with additional features.
"""

import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestPluginSystem:
    """Test the plugin system functionality."""

    def test_plugin_base_class(self):
        """Test the Plugin base class interface."""
        from nexus.plugins import NexusPlugin

        # Test abstract base class
        with pytest.raises(TypeError):
            # Can't instantiate abstract class
            NexusPlugin()

        # Test concrete implementation
        class TestPlugin(NexusPlugin):
            @property
            def name(self):
                return "test"

            @property
            def description(self):
                return "Test plugin"

            def apply(self, nexus_instance):
                nexus_instance.test_applied = True

        plugin = TestPlugin()
        assert plugin.name == "test"
        assert plugin.description == "Test plugin"
        assert plugin.validate() is True

    def test_auth_plugin_initialization(self):
        """Test AuthPlugin initialization."""
        from nexus.plugins import AuthPlugin

        plugin = AuthPlugin()
        assert plugin.name == "auth"
        assert "authentication" in plugin.description.lower()

    def test_auth_plugin_apply(self):
        """Test applying auth plugin to nexus."""
        from nexus.plugins import AuthPlugin

        plugin = AuthPlugin()
        mock_nexus = Mock()
        mock_nexus._gateway = Mock()

        plugin.apply(mock_nexus)

        # Should set auth enabled flag
        assert mock_nexus._auth_enabled is True

    def test_monitoring_plugin_initialization(self):
        """Test MonitoringPlugin initialization."""
        from nexus.plugins import MonitoringPlugin

        plugin = MonitoringPlugin()
        assert plugin.name == "monitoring"
        assert "monitoring" in plugin.description.lower()

    def test_monitoring_plugin_apply(self):
        """Test applying monitoring plugin."""
        from nexus.plugins import MonitoringPlugin

        plugin = MonitoringPlugin()
        mock_nexus = Mock()

        plugin.apply(mock_nexus)

        # Should enable monitoring and initialize metrics
        assert mock_nexus._monitoring_enabled is True
        assert hasattr(mock_nexus, "_metrics")

    def test_rate_limit_plugin(self):
        """Test rate limiting plugin."""
        from nexus.plugins import RateLimitPlugin

        # Default rate limit
        plugin = RateLimitPlugin()
        assert plugin.requests_per_minute == 60

        # Custom rate limit
        plugin = RateLimitPlugin(requests_per_minute=100)
        assert plugin.requests_per_minute == 100

        # Apply to nexus
        mock_nexus = Mock()
        plugin.apply(mock_nexus)
        assert mock_nexus._rate_limit == 100

    def test_plugin_registry(self):
        """Test plugin registry."""
        from nexus.plugins import NexusPlugin, PluginRegistry

        registry = PluginRegistry()

        # Should have built-in plugins
        assert "auth" in registry.list()
        assert "monitoring" in registry.list()
        assert "rate_limit" in registry.list()

        # Test get plugin
        auth_plugin = registry.get("auth")
        assert auth_plugin is not None
        assert auth_plugin.name == "auth"

        # Test register custom plugin
        class CustomPlugin(NexusPlugin):
            @property
            def name(self):
                return "custom"

            @property
            def description(self):
                return "Custom plugin"

            def apply(self, nexus_instance):
                nexus_instance.custom_applied = True

        registry.register(CustomPlugin())
        assert "custom" in registry.list()

    def test_plugin_registry_validation(self):
        """Test plugin validation in registry."""
        from nexus.plugins import NexusPlugin, PluginRegistry

        registry = PluginRegistry()

        # Invalid plugin type
        with pytest.raises(ValueError, match="must inherit from NexusPlugin"):
            registry.register("not a plugin")

        # Plugin that fails validation
        class BadPlugin(NexusPlugin):
            @property
            def name(self):
                return "bad"

            @property
            def description(self):
                return "Bad plugin"

            def apply(self, nexus_instance):
                pass

            def validate(self):
                return False

        with pytest.raises(ValueError, match="validation failed"):
            registry.register(BadPlugin())

    def test_plugin_apply_through_registry(self):
        """Test applying plugins through registry."""
        from nexus.plugins import PluginRegistry

        registry = PluginRegistry()
        mock_nexus = Mock()
        mock_nexus._gateway = Mock()

        # Apply auth plugin
        registry.apply("auth", mock_nexus)
        assert mock_nexus._auth_enabled is True

        # Apply non-existent plugin
        with pytest.raises(ValueError, match="not found"):
            registry.apply("non_existent", mock_nexus)

    def test_plugin_loader(self):
        """Test loading external plugins."""
        import tempfile
        from pathlib import Path

        from nexus.plugins import PluginLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a plugin file
            plugin_file = Path(tmpdir) / "custom_plugin.py"
            plugin_file.write_text(
                """
from nexus.plugins import NexusPlugin

class CustomPlugin(NexusPlugin):
    @property
    def name(self):
        return "external"

    @property
    def description(self):
        return "External plugin"

    def apply(self, nexus_instance):
        nexus_instance.external_applied = True
"""
            )

            # Load plugins
            plugins = PluginLoader.load_from_directory(tmpdir)

            assert len(plugins) == 1
            assert "external" in plugins
            assert plugins["external"].name == "external"

    def test_nexus_use_plugin_method(self):
        """Test the use_plugin method on nexus."""
        from nexus.core import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gateway.return_value = Mock()

            nexus = Nexus()

            # Use auth plugin
            result = nexus.use_plugin("auth")

            # Should return self for chaining
            assert result is nexus

            # Should have applied auth
            assert hasattr(nexus, "_auth_enabled")
            assert nexus._auth_enabled is True

    def test_plugin_chaining(self):
        """Test chaining multiple plugins."""
        from nexus.core import Nexus

        with patch("nexus.core.create_gateway") as mock_gateway:
            mock_gateway.return_value = Mock()

            nexus = Nexus()

            # Chain multiple plugins
            result = nexus.enable_auth().enable_monitoring()

            # Should return nexus for chaining
            assert result is nexus

            # Should have applied both
            assert nexus._auth_enabled is True
            assert nexus._monitoring_enabled is True

    def test_global_plugin_registry(self):
        """Test global plugin registry singleton."""
        from nexus.plugins import get_plugin_registry

        registry1 = get_plugin_registry()
        registry2 = get_plugin_registry()

        # Should be the same instance
        assert registry1 is registry2

        # Should have built-in plugins
        assert "auth" in registry1.list()
        assert "monitoring" in registry1.list()
