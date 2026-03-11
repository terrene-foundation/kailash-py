"""Unit tests for Nexus plugin API (TODO-300C).

Tests for NexusPluginProtocol and add_plugin() method on Nexus class.
Tier 1 tests - mocking allowed for isolated unit testing.
"""

import asyncio
import logging
from datetime import UTC, datetime

import pytest
from nexus import Nexus
from nexus.core import NexusPluginProtocol

# =============================================================================
# Test Fixtures
# =============================================================================


class DummyPlugin:
    """Dummy plugin for testing."""

    def __init__(self, name="dummy"):
        self._name = name
        self.install_called = False
        self.install_app_ref = None
        self.startup_called = False
        self.shutdown_called = False

    @property
    def name(self) -> str:
        return self._name

    def install(self, app):
        self.install_called = True
        self.install_app_ref = app

    def on_startup(self):
        self.startup_called = True

    def on_shutdown(self):
        self.shutdown_called = True


class MiddlewarePlugin:
    """Plugin that registers middleware during install."""

    def __init__(self):
        self._name = "middleware-plugin"

    @property
    def name(self) -> str:
        return self._name

    def install(self, app):
        # Plugin registers middleware via the public API
        class PluginMiddleware:
            def __init__(self, inner_app, plugin_id=None):
                self.app = inner_app
                self.plugin_id = plugin_id

            async def __call__(self, scope, receive, send):
                await self.app(scope, receive, send)

        app.add_middleware(PluginMiddleware, plugin_id="test")

    def on_startup(self):
        pass

    def on_shutdown(self):
        pass


class MinimalPlugin:
    """Plugin with only required methods (no lifecycle hooks)."""

    @property
    def name(self) -> str:
        return "minimal"

    def install(self, app):
        pass


# =============================================================================
# Tests: NexusPluginProtocol
# =============================================================================


class TestNexusPluginProtocol:
    """Tests for the NexusPluginProtocol definition."""

    def test_dummy_plugin_is_protocol_compliant(self):
        """DummyPlugin satisfies NexusPluginProtocol."""
        plugin = DummyPlugin()
        assert isinstance(plugin, NexusPluginProtocol)

    def test_plain_object_not_protocol_compliant(self):
        """Plain object does not satisfy NexusPluginProtocol."""
        assert not isinstance(object(), NexusPluginProtocol)

    def test_protocol_is_runtime_checkable(self):
        """NexusPluginProtocol can be checked at runtime."""
        # This verifies the @runtime_checkable decorator is applied
        assert isinstance(DummyPlugin(), NexusPluginProtocol)


# =============================================================================
# Tests: add_plugin() - Validation
# =============================================================================


class TestAddPluginValidation:
    """Tests for add_plugin() input validation."""

    def test_rejects_object_without_install(self):
        """TypeError when plugin has no install method."""
        app = Nexus(enable_durability=False)

        class NoInstall:
            name = "bad"

        with pytest.raises(TypeError, match="NexusPluginProtocol"):
            app.add_plugin(NoInstall())

    def test_rejects_object_without_name(self):
        """TypeError when plugin has no name."""
        app = Nexus(enable_durability=False)

        class NoName:
            def install(self, app):
                pass

        with pytest.raises(TypeError, match="NexusPluginProtocol"):
            app.add_plugin(NoName())

    def test_rejects_string(self):
        """TypeError when passing a string."""
        app = Nexus(enable_durability=False)

        with pytest.raises(TypeError, match="NexusPluginProtocol"):
            app.add_plugin("not a plugin")

    def test_accepts_valid_plugin(self):
        """No error when passing a valid plugin."""
        app = Nexus(enable_durability=False)
        plugin = DummyPlugin()

        app.add_plugin(plugin)

        assert "dummy" in app._plugins


# =============================================================================
# Tests: add_plugin() - Installation
# =============================================================================


class TestAddPluginInstallation:
    """Tests for plugin installation behavior."""

    def test_install_called_immediately(self):
        """Plugin.install() is called during add_plugin()."""
        app = Nexus(enable_durability=False)
        plugin = DummyPlugin()

        app.add_plugin(plugin)

        assert plugin.install_called

    def test_install_receives_nexus_instance(self):
        """Plugin.install() receives the Nexus app instance."""
        app = Nexus(enable_durability=False)
        plugin = DummyPlugin()

        app.add_plugin(plugin)

        assert plugin.install_app_ref is app

    def test_plugin_can_register_middleware(self):
        """Plugin can call add_middleware() during install()."""
        app = Nexus(enable_durability=False)
        plugin = MiddlewarePlugin()

        app.add_plugin(plugin)

        assert len(app._middleware_stack) == 1


# =============================================================================
# Tests: add_plugin() - Duplicate Detection
# =============================================================================


class TestAddPluginDuplicate:
    """Tests for duplicate plugin detection."""

    def test_rejects_duplicate_name(self):
        """ValueError when installing plugin with same name."""
        app = Nexus(enable_durability=False)
        plugin1 = DummyPlugin(name="my-plugin")
        plugin2 = DummyPlugin(name="my-plugin")

        app.add_plugin(plugin1)

        with pytest.raises(ValueError, match="already installed"):
            app.add_plugin(plugin2)

    def test_accepts_different_names(self):
        """No error when plugins have different names."""
        app = Nexus(enable_durability=False)
        plugin1 = DummyPlugin(name="plugin-a")
        plugin2 = DummyPlugin(name="plugin-b")

        app.add_plugin(plugin1)
        app.add_plugin(plugin2)

        assert len(app._plugins) == 2


# =============================================================================
# Tests: add_plugin() - Method Chaining
# =============================================================================


class TestAddPluginChaining:
    """Tests for method chaining support."""

    def test_returns_self(self):
        """add_plugin() returns self for method chaining."""
        app = Nexus(enable_durability=False)
        plugin = DummyPlugin()

        result = app.add_plugin(plugin)

        assert result is app

    def test_chain_multiple(self):
        """Multiple plugins can be chained."""
        app = Nexus(enable_durability=False)
        plugin1 = DummyPlugin(name="a")
        plugin2 = DummyPlugin(name="b")

        result = app.add_plugin(plugin1).add_plugin(plugin2)

        assert result is app
        assert len(app._plugins) == 2


# =============================================================================
# Tests: Lifecycle Hooks
# =============================================================================


class TestPluginLifecycleHooks:
    """Tests for plugin startup/shutdown hooks."""

    def test_startup_hook_registered(self):
        """on_startup hook is registered in _startup_hooks."""
        app = Nexus(enable_durability=False)
        plugin = DummyPlugin()

        app.add_plugin(plugin)

        assert plugin.on_startup in app._startup_hooks

    def test_shutdown_hook_registered(self):
        """on_shutdown hook is registered in _shutdown_hooks."""
        app = Nexus(enable_durability=False)
        plugin = DummyPlugin()

        app.add_plugin(plugin)

        assert plugin.on_shutdown in app._shutdown_hooks

    def test_minimal_plugin_no_hooks(self):
        """Plugin without lifecycle methods has no hooks registered."""
        app = Nexus(enable_durability=False)

        # MinimalPlugin has install but its on_startup/on_shutdown are
        # not defined, so hooks should remain empty
        plugin = MinimalPlugin()
        app.add_plugin(plugin)

        # MinimalPlugin doesn't define on_startup/on_shutdown
        assert len(app._startup_hooks) == 0
        assert len(app._shutdown_hooks) == 0

    def test_startup_hook_failure_logged(self, caplog):
        """Startup hook errors are logged but don't crash."""

        class FailingStartupPlugin:
            @property
            def name(self):
                return "failing-startup"

            def install(self, app):
                pass

            def on_startup(self):
                raise RuntimeError("Startup kaboom")

            def on_shutdown(self):
                pass

        app = Nexus(enable_durability=False)
        app.add_plugin(FailingStartupPlugin())

        with caplog.at_level(logging.ERROR):
            # Call startup hooks directly (start() blocks)
            app._call_startup_hooks()

        assert "Startup hook failed" in caplog.text

    def test_shutdown_hook_failure_logged(self, caplog):
        """Shutdown hook errors are logged but don't crash."""

        class FailingShutdownPlugin:
            @property
            def name(self):
                return "failing-shutdown"

            def install(self, app):
                pass

            def on_startup(self):
                pass

            def on_shutdown(self):
                raise RuntimeError("Shutdown kaboom")

        app = Nexus(enable_durability=False)
        app.add_plugin(FailingShutdownPlugin())

        with caplog.at_level(logging.ERROR):
            app._call_shutdown_hooks()

        assert "Shutdown hook failed" in caplog.text

    def test_shutdown_hooks_called_in_reverse_order(self):
        """Shutdown hooks are called in reverse order of registration."""
        call_order = []

        class OrderTracker:
            def __init__(self, plugin_name):
                self._name = plugin_name

            @property
            def name(self):
                return self._name

            def install(self, app):
                pass

            def on_startup(self):
                pass

            def on_shutdown(self):
                call_order.append(self._name)

        app = Nexus(enable_durability=False)
        app.add_plugin(OrderTracker("first"))
        app.add_plugin(OrderTracker("second"))
        app.add_plugin(OrderTracker("third"))

        app._call_shutdown_hooks()

        assert call_order == ["third", "second", "first"]

    def test_async_startup_hook_no_running_loop(self):
        """Async startup hook works when no event loop is running."""

        async_hook_called = []

        class AsyncStartupPlugin:
            @property
            def name(self):
                return "async-startup"

            def install(self, app):
                pass

            async def on_startup(self):
                async_hook_called.append(True)

            def on_shutdown(self):
                pass

        app = Nexus(enable_durability=False)
        app.add_plugin(AsyncStartupPlugin())

        # Should not raise - runs via asyncio.run() since no loop is running
        app._call_startup_hooks()
        assert len(async_hook_called) == 1

    def test_async_shutdown_hook_no_running_loop(self):
        """Async shutdown hook works when no event loop is running."""

        async_hook_called = []

        class AsyncShutdownPlugin:
            @property
            def name(self):
                return "async-shutdown"

            def install(self, app):
                pass

            def on_startup(self):
                pass

            async def on_shutdown(self):
                async_hook_called.append(True)

        app = Nexus(enable_durability=False)
        app.add_plugin(AsyncShutdownPlugin())

        app._call_shutdown_hooks()
        assert len(async_hook_called) == 1


# =============================================================================
# Tests: Introspection
# =============================================================================


class TestPluginIntrospection:
    """Tests for plugin introspection property."""

    def test_plugins_property_returns_dict(self):
        """plugins property returns dict of installed plugins."""
        app = Nexus(enable_durability=False)
        plugin = DummyPlugin()
        app.add_plugin(plugin)

        plugins_dict = app.plugins

        assert isinstance(plugins_dict, dict)
        assert len(plugins_dict) == 1
        assert "dummy" in plugins_dict

    def test_plugins_property_returns_copy(self):
        """plugins property returns a copy, not the internal dict."""
        app = Nexus(enable_durability=False)
        plugin = DummyPlugin()
        app.add_plugin(plugin)

        dict1 = app.plugins
        dict2 = app.plugins

        assert dict1 is not dict2
        assert dict1 is not app._plugins

    def test_plugins_multiple(self):
        """Multiple plugins tracked correctly."""
        app = Nexus(enable_durability=False)
        app.add_plugin(DummyPlugin(name="a"))
        app.add_plugin(DummyPlugin(name="b"))
        app.add_plugin(DummyPlugin(name="c"))

        assert len(app.plugins) == 3
        assert set(app.plugins.keys()) == {"a", "b", "c"}


# =============================================================================
# Tests: Logging
# =============================================================================


class TestAddPluginLogging:
    """Tests for logging behavior."""

    def test_logs_install(self, caplog):
        """Info log when plugin is installed."""
        with caplog.at_level(logging.INFO):
            app = Nexus(enable_durability=False)

            caplog.clear()
            app.add_plugin(DummyPlugin())

        assert "Installing plugin: dummy" in caplog.text
        assert "Plugin installed: dummy" in caplog.text
