"""
Unit tests for ModelRegistry runtime injection (M2-002).

Tests that ModelRegistry:
1. Accepts an optional runtime parameter in __init__
2. Uses self.runtime instead of creating LocalRuntime() in every method
3. Properly acquires/releases runtime references
4. Emits ResourceWarning on unclosed instances
5. Remains backward-compatible when no runtime is provided
"""

import warnings
from unittest.mock import MagicMock, patch

import pytest

from kailash.runtime.local import LocalRuntime


class TestModelRegistryRuntimeInjection:
    """Test that ModelRegistry accepts and uses an injected runtime."""

    def _make_mock_dataflow(self):
        """Create a minimal mock DataFlow instance for ModelRegistry construction."""
        mock_df = MagicMock()
        mock_df.config.database.get_connection_url.return_value = "sqlite:///test.db"
        mock_df.config.environment = "test"
        return mock_df

    def test_constructor_accepts_runtime_parameter(self):
        """ModelRegistry.__init__ must accept runtime=None as a keyword argument."""
        from dataflow.core.model_registry import ModelRegistry

        mock_df = self._make_mock_dataflow()
        runtime = LocalRuntime()
        try:
            # Must not raise TypeError for unexpected keyword argument
            registry = ModelRegistry(mock_df, runtime=runtime)
            assert registry.runtime is runtime
        finally:
            registry.close()
            runtime.close()

    def test_constructor_acquires_injected_runtime(self):
        """When runtime is provided, constructor must call runtime.acquire()."""
        from dataflow.core.model_registry import ModelRegistry

        mock_df = self._make_mock_dataflow()
        runtime = LocalRuntime()
        initial_ref_count = runtime.ref_count  # Should be 1

        registry = ModelRegistry(mock_df, runtime=runtime)
        try:
            # acquire() increments ref count
            assert runtime.ref_count == initial_ref_count + 1
            assert registry._owns_runtime is False
        finally:
            registry.close()
            runtime.close()

    def test_constructor_creates_runtime_when_none_provided(self):
        """When no runtime provided, constructor must create its own (backward compat)."""
        from dataflow.core.model_registry import ModelRegistry

        mock_df = self._make_mock_dataflow()
        registry = ModelRegistry(mock_df)
        try:
            assert registry.runtime is not None
            assert registry._owns_runtime is True
        finally:
            registry.close()

    def test_close_releases_runtime(self):
        """close() must call runtime.release() and set runtime to None."""
        from dataflow.core.model_registry import ModelRegistry

        mock_df = self._make_mock_dataflow()
        runtime = LocalRuntime()
        registry = ModelRegistry(mock_df, runtime=runtime)

        # Before close: ref_count should be 2 (creator + acquire)
        assert runtime.ref_count == 2

        registry.close()

        # After close: ref_count should be back to 1 (only creator reference)
        assert runtime.ref_count == 1
        assert registry.runtime is None

        runtime.close()

    def test_close_idempotent(self):
        """Calling close() multiple times must not raise."""
        from dataflow.core.model_registry import ModelRegistry

        mock_df = self._make_mock_dataflow()
        runtime = LocalRuntime()
        registry = ModelRegistry(mock_df, runtime=runtime)

        registry.close()
        registry.close()  # Second call should be a no-op
        assert registry.runtime is None

        runtime.close()

    def test_del_emits_resource_warning(self):
        """__del__ must emit ResourceWarning if close() was not called."""
        from dataflow.core.model_registry import ModelRegistry

        mock_df = self._make_mock_dataflow()
        runtime = LocalRuntime()
        registry = ModelRegistry(mock_df, runtime=runtime)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            registry.__del__()

            resource_warnings = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(resource_warnings) == 1
            assert "Unclosed" in str(resource_warnings[0].message)
            assert "ModelRegistry" in str(resource_warnings[0].message)

        # Clean up: close was called by __del__, but runtime ref still held by creator
        runtime.close()

    def test_no_resource_warning_after_close(self):
        """__del__ must NOT emit ResourceWarning if close() was already called."""
        from dataflow.core.model_registry import ModelRegistry

        mock_df = self._make_mock_dataflow()
        runtime = LocalRuntime()
        registry = ModelRegistry(mock_df, runtime=runtime)
        registry.close()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            registry.__del__()

            resource_warnings = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(resource_warnings) == 0

        runtime.close()


class TestModelRegistryNoLocalRuntimeLocals:
    """Verify that no method creates a local LocalRuntime() instance."""

    def test_no_local_runtime_in_source(self):
        """The model_registry.py source must contain zero 'init_runtime = LocalRuntime()' patterns."""
        import inspect

        from dataflow.core.model_registry import ModelRegistry

        source = inspect.getsource(ModelRegistry)

        # There should be NO method-local LocalRuntime() creation
        assert "init_runtime = LocalRuntime()" not in source, (
            "Found 'init_runtime = LocalRuntime()' in ModelRegistry source. "
            "All methods must use self.runtime instead of creating local runtimes."
        )

    def test_no_local_runtime_import_usage_in_methods(self):
        """No method body should instantiate LocalRuntime() or AsyncLocalRuntime()."""
        import inspect

        from dataflow.core.model_registry import ModelRegistry

        source = inspect.getsource(ModelRegistry)

        # Count occurrences of LocalRuntime() instantiation (not in imports/comments)
        # The constructor may reference LocalRuntime for self-creation, but method bodies
        # should not create new instances.
        lines = source.split("\n")
        violation_lines = []
        in_init = False

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Track if we're inside __init__
            if "def __init__" in stripped:
                in_init = True
            elif stripped.startswith("def ") and in_init:
                in_init = False

            # Skip __init__ — it legitimately creates a runtime when none provided
            if in_init:
                continue

            # Skip comments
            if stripped.startswith("#"):
                continue

            # Check for LocalRuntime() or AsyncLocalRuntime() instantiation
            if "LocalRuntime()" in stripped or "AsyncLocalRuntime()" in stripped:
                violation_lines.append((i, stripped))

        assert len(violation_lines) == 0, (
            f"Found {len(violation_lines)} LocalRuntime()/AsyncLocalRuntime() instantiation(s) "
            f"outside __init__:\n"
            + "\n".join(f"  Line {num}: {text}" for num, text in violation_lines)
        )


class TestModelRegistryBackwardCompatibility:
    """Ensure ModelRegistry works identically with and without runtime injection."""

    def _make_mock_dataflow(self):
        mock_df = MagicMock()
        mock_df.config.database.get_connection_url.return_value = "sqlite:///test.db"
        mock_df.config.environment = "test"
        return mock_df

    def test_positional_arg_still_works(self):
        """ModelRegistry(dataflow_instance) must still work as before."""
        from dataflow.core.model_registry import ModelRegistry

        mock_df = self._make_mock_dataflow()
        registry = ModelRegistry(mock_df)
        try:
            assert registry.dataflow is mock_df
            assert registry.runtime is not None
        finally:
            registry.close()

    def test_migration_system_param_still_works(self):
        """ModelRegistry(dataflow, migration_system=ms) must still work."""
        from dataflow.core.model_registry import ModelRegistry

        mock_df = self._make_mock_dataflow()
        mock_ms = MagicMock()
        registry = ModelRegistry(mock_df, migration_system=mock_ms)
        try:
            assert registry.migration_system is mock_ms
        finally:
            registry.close()

    def test_all_three_params(self):
        """ModelRegistry(dataflow, runtime=rt, migration_system=ms) must work."""
        from dataflow.core.model_registry import ModelRegistry

        mock_df = self._make_mock_dataflow()
        mock_ms = MagicMock()
        runtime = LocalRuntime()
        registry = ModelRegistry(mock_df, runtime=runtime, migration_system=mock_ms)
        try:
            assert registry.dataflow is mock_df
            assert registry.runtime is runtime
            assert registry.migration_system is mock_ms
            assert registry._owns_runtime is False
        finally:
            registry.close()
            runtime.close()
