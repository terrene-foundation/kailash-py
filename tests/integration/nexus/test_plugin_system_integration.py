"""Tier 2 Integration Tests for Plugin System (NO MOCKING).

Tests the plugin system with real plugin validation, loading, and lifecycle.
Validates the stub fixes in plugins.py.
"""

import pytest
from nexus import Nexus
from nexus.plugins import (
    AuthPlugin,
    MonitoringPlugin,
    NexusPlugin,
    PluginRegistry,
    RateLimitPlugin,
    get_plugin_registry,
)


@pytest.mark.integration
class TestPluginValidationIntegration:
    """Integration tests for plugin validation."""

    def test_valid_plugin_validation(self):
        """Test that valid plugins pass validation.

        CRITICAL: Tests the validate() method that was previously a stub.
        NO MOCKING - real plugin instances.
        """
        # Create real plugin instances
        auth_plugin = AuthPlugin()
        monitoring_plugin = MonitoringPlugin()
        rate_limit_plugin = RateLimitPlugin(requests_per_minute=100)

        # All should validate successfully
        assert auth_plugin.validate() is True
        assert monitoring_plugin.validate() is True
        assert rate_limit_plugin.validate() is True

    def test_invalid_plugin_validation(self):
        """Test that invalid plugins fail validation.

        Tests validation edge cases and error handling.
        """

        # Create a plugin with invalid name
        class InvalidNamePlugin(NexusPlugin):
            @property
            def name(self):
                return None  # Invalid: None name

            @property
            def description(self):
                return "Test"

            def apply(self, nexus_instance):
                pass

        invalid_plugin = InvalidNamePlugin()
        assert invalid_plugin.validate() is False

    def test_plugin_missing_apply_method(self):
        """Test validation fails for plugin without apply method."""

        # Create incomplete plugin class
        class IncompletePlugin(NexusPlugin):
            @property
            def name(self):
                return "incomplete"

            @property
            def description(self):
                return "Missing apply"

            # No apply method defined (shouldn't happen with ABC, but test anyway)

        # This should fail at instantiation due to ABC
        with pytest.raises(TypeError):
            IncompletePlugin()


@pytest.mark.integration
class TestPluginLifecycleIntegration:
    """Integration tests for plugin lifecycle management."""

    def test_auth_plugin_application(self):
        """Test applying authentication plugin to Nexus.

        Tests the full plugin apply() lifecycle with real Nexus instance.
        NO MOCKING - real plugin application.
        """
        nexus = Nexus(auto_discovery=False, enable_durability=False)
        auth_plugin = AuthPlugin()

        # Apply plugin
        auth_plugin.apply(nexus)

        # Verify authentication enabled
        assert hasattr(nexus, "_auth_enabled")
        assert nexus._auth_enabled is True

    def test_monitoring_plugin_application(self):
        """Test applying monitoring plugin to Nexus.

        Tests monitoring plugin lifecycle and state changes.
        """
        nexus = Nexus(auto_discovery=False, enable_durability=False)
        monitoring_plugin = MonitoringPlugin()

        # Capture initial state
        initial_monitoring = getattr(nexus, "_monitoring_enabled", False)

        # Apply plugin
        monitoring_plugin.apply(nexus)

        # Verify monitoring enabled
        assert hasattr(nexus, "_monitoring_enabled")
        assert nexus._monitoring_enabled is True
        assert hasattr(nexus, "_metrics")

    def test_rate_limit_plugin_application(self):
        """Test applying rate limit plugin with configuration.

        Tests plugin with constructor parameters.
        """
        nexus = Nexus(auto_discovery=False, enable_durability=False)

        # Create rate limit plugin with specific limit
        rate_limit = RateLimitPlugin(requests_per_minute=120)

        # Apply plugin
        rate_limit.apply(nexus)

        # Verify rate limit configured
        assert hasattr(nexus, "_rate_limit")
        assert nexus._rate_limit == 120

    def test_multiple_plugin_application(self):
        """Test applying multiple plugins to same Nexus instance.

        Validates plugins can coexist and don't interfere.
        """
        nexus = Nexus(auto_discovery=False, enable_durability=False)

        # Apply multiple plugins
        AuthPlugin().apply(nexus)
        MonitoringPlugin().apply(nexus)
        RateLimitPlugin(requests_per_minute=60).apply(nexus)

        # Verify all plugins applied
        assert nexus._auth_enabled is True
        assert nexus._monitoring_enabled is True
        assert nexus._rate_limit == 60


@pytest.mark.integration
class TestPluginRegistryIntegration:
    """Integration tests for plugin registry."""

    def test_builtin_plugins_loaded(self):
        """Test that built-in plugins are loaded in registry.

        NO MOCKING - tests real plugin registry initialization.
        """
        registry = PluginRegistry()

        # Verify built-in plugins loaded
        assert "auth" in registry.list()
        assert "monitoring" in registry.list()
        assert "rate_limit" in registry.list()

    def test_plugin_registration(self):
        """Test registering custom plugins.

        Tests the register() method with validation.
        """
        registry = PluginRegistry()

        # Create custom plugin
        class CustomPlugin(NexusPlugin):
            @property
            def name(self):
                return "custom"

            @property
            def description(self):
                return "Custom test plugin"

            def apply(self, nexus_instance):
                nexus_instance._custom_applied = True

        custom_plugin = CustomPlugin()

        # Register plugin
        registry.register(custom_plugin)

        # Verify plugin registered
        assert "custom" in registry.list()
        assert registry.get("custom") == custom_plugin

    def test_invalid_plugin_registration_rejected(self):
        """Test that invalid plugins are rejected during registration.

        Tests validation enforcement in registry.
        """
        registry = PluginRegistry()

        # Try to register non-plugin object
        with pytest.raises(ValueError, match="must inherit from NexusPlugin"):
            registry.register("not_a_plugin")

    def test_plugin_retrieval(self):
        """Test retrieving registered plugins by name."""
        registry = PluginRegistry()

        # Get built-in plugin
        auth_plugin = registry.get("auth")
        assert auth_plugin is not None
        assert isinstance(auth_plugin, AuthPlugin)

        # Get non-existent plugin
        missing = registry.get("nonexistent")
        assert missing is None

    def test_plugin_application_via_registry(self):
        """Test applying plugins through registry.

        Tests the apply() method of registry.
        """
        registry = PluginRegistry()
        nexus = Nexus(auto_discovery=False, enable_durability=False)

        # Apply plugin via registry
        registry.apply("auth", nexus)

        # Verify plugin applied
        assert nexus._auth_enabled is True

    def test_plugin_application_error_handling(self):
        """Test error handling when applying non-existent plugin."""
        registry = PluginRegistry()
        nexus = Nexus(auto_discovery=False, enable_durability=False)

        # Try to apply non-existent plugin
        with pytest.raises(ValueError, match="not found"):
            registry.apply("nonexistent", nexus)


@pytest.mark.integration
class TestPluginRegistryGlobalSingleton:
    """Integration tests for global plugin registry."""

    def test_global_registry_singleton(self):
        """Test that get_plugin_registry() returns singleton.

        Validates global registry pattern.
        """
        # Get registry twice
        registry1 = get_plugin_registry()
        registry2 = get_plugin_registry()

        # Should be same instance
        assert registry1 is registry2

        # Should have built-in plugins
        assert "auth" in registry1.list()
        assert "monitoring" in registry1.list()

    def test_global_registry_persistence(self):
        """Test that global registry persists plugin registrations.

        Validates state persistence across calls.
        """
        registry = get_plugin_registry()

        # Register custom plugin
        class PersistentPlugin(NexusPlugin):
            @property
            def name(self):
                return "persistent_test"

            @property
            def description(self):
                return "Test persistence"

            def apply(self, nexus_instance):
                pass

        registry.register(PersistentPlugin())

        # Get registry again
        registry2 = get_plugin_registry()

        # Custom plugin should still be registered
        assert "persistent_test" in registry2.list()


@pytest.mark.integration
class TestPluginErrorHandling:
    """Integration tests for plugin error handling and diagnostics."""

    def test_plugin_validation_error_logging(self):
        """Test that validation errors are properly logged.

        Validates diagnostic error messages.
        """
        import logging
        from io import StringIO

        # Capture log output
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.ERROR)
        logger = logging.getLogger("nexus.plugins")
        logger.addHandler(handler)

        try:
            # Create plugin with error-triggering name
            class ErrorPlugin(NexusPlugin):
                @property
                def name(self):
                    raise RuntimeError("Name error")

                @property
                def description(self):
                    return "Test"

                def apply(self, nexus_instance):
                    pass

            plugin = ErrorPlugin()
            result = plugin.validate()

            # Should fail validation
            assert result is False

            # Should have logged error
            log_output = log_stream.getvalue()
            assert "unable to get name" in log_output.lower()

        finally:
            logger.removeHandler(handler)

    def test_plugin_apply_exception_propagation(self):
        """Test that exceptions during apply() are properly propagated.

        Validates error handling doesn't silently fail.
        """

        class FailingPlugin(NexusPlugin):
            @property
            def name(self):
                return "failing"

            @property
            def description(self):
                return "Fails on apply"

            def apply(self, nexus_instance):
                raise RuntimeError("Apply failed intentionally")

        nexus = Nexus(auto_discovery=False, enable_durability=False)
        plugin = FailingPlugin()

        # Exception should propagate
        with pytest.raises(RuntimeError, match="Apply failed intentionally"):
            plugin.apply(nexus)
