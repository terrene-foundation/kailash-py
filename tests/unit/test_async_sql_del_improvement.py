"""Unit tests for AsyncSQLDatabaseNode.__del__ improvement (TODO-007).

Tests the Core SDK AsyncSQLDatabaseNode to verify:
1. __del__ emits ResourceWarning when not properly closed
2. __del__ does NOT attempt async cleanup (no asyncio calls)
3. __del__ is silent when already disconnected or adapter is None
4. Class-level defaults for _adapter and _connected are set
"""

import warnings

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode


class TestAsyncSQLDatabaseNodeDelWarning:
    """Test that __del__ emits ResourceWarning instead of attempting async cleanup."""

    def test_del_emits_resource_warning_when_not_closed(self):
        """Test that __del__ emits ResourceWarning when adapter exists and still connected."""
        node = AsyncSQLDatabaseNode.__new__(AsyncSQLDatabaseNode)
        # Simulate a node that was connected but not closed
        node._adapter = object()  # non-None adapter
        node._connected = True
        node._source_traceback = None

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            node.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert (
                len(resource_warnings) == 1
            ), f"Expected exactly 1 ResourceWarning, got {len(resource_warnings)}"
            assert "GC'd while still connected" in str(
                resource_warnings[0].message
            ), "Warning should mention GC'd while still connected"

    def test_del_silent_when_adapter_is_none(self):
        """Test that __del__ is silent when _adapter is None."""
        node = AsyncSQLDatabaseNode.__new__(AsyncSQLDatabaseNode)
        node._adapter = None
        node._connected = True

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            node.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert (
                len(resource_warnings) == 0
            ), "No warning should be emitted when _adapter is None"

    def test_del_silent_when_not_connected(self):
        """Test that __del__ is silent when _connected is False."""
        node = AsyncSQLDatabaseNode.__new__(AsyncSQLDatabaseNode)
        node._adapter = object()  # non-None adapter
        node._connected = False

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            node.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert (
                len(resource_warnings) == 0
            ), "No warning should be emitted when not connected"


class TestAsyncSQLDatabaseNodeDelNoAsyncio:
    """Test that __del__ does NOT use asyncio for cleanup."""

    def test_del_does_not_import_asyncio(self):
        """Test that __del__ does not import or use asyncio."""
        import inspect

        source = inspect.getsource(AsyncSQLDatabaseNode.__del__)

        assert (
            "asyncio" not in source
        ), "__del__ must not reference asyncio - async cleanup in __del__ is unreliable"
        assert "ensure_future" not in source, "__del__ must not use ensure_future"
        assert "create_task" not in source, "__del__ must not use create_task"
        assert "get_running_loop" not in source, "__del__ must not use get_running_loop"
        assert "get_event_loop" not in source, "__del__ must not use get_event_loop"


class TestAsyncSQLDatabaseNodeClassDefaults:
    """Test that class-level defaults are properly set."""

    def test_class_has_adapter_default(self):
        """Test that _adapter class-level default is None."""
        assert hasattr(AsyncSQLDatabaseNode, "_adapter")
        assert AsyncSQLDatabaseNode._adapter is None

    def test_class_has_connected_default(self):
        """Test that _connected class-level default is False."""
        assert hasattr(AsyncSQLDatabaseNode, "_connected")
        assert AsyncSQLDatabaseNode._connected is False

    def test_class_has_source_traceback_default(self):
        """Test that _source_traceback class-level default is None."""
        assert hasattr(AsyncSQLDatabaseNode, "_source_traceback")
        assert AsyncSQLDatabaseNode._source_traceback is None

    def test_del_safe_on_bare_instance(self):
        """Test that __del__ works safely on a bare instance without __init__."""
        node = AsyncSQLDatabaseNode.__new__(AsyncSQLDatabaseNode)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            node.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert (
                len(resource_warnings) == 0
            ), "__del__ should be safe on bare instance with only class defaults"
