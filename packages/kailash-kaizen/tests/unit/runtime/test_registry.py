"""
Unit Tests for Runtime Registry Functions (Tier 1)

Tests the global registry functions in kaizen.runtime.

Coverage:
- register_runtime()
- unregister_runtime()
- get_runtime()
- get_all_runtimes()
- list_runtimes()
- set_default_runtime()
- get_default_runtime()
- create_selector()
"""

from typing import Any, AsyncIterator, Dict, List

import pytest

from kaizen.runtime import (
    ExecutionContext,
    ExecutionResult,
    RuntimeAdapter,
    RuntimeCapabilities,
    RuntimeSelector,
    create_selector,
    get_all_runtimes,
    get_default_runtime,
    get_runtime,
    list_runtimes,
    register_runtime,
    set_default_runtime,
    unregister_runtime,
)


class MockRuntimeAdapter(RuntimeAdapter):
    """Mock adapter for testing registry functions."""

    def __init__(self, name: str):
        self._capabilities = RuntimeCapabilities(
            runtime_name=name,
            provider="test",
        )

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return self._capabilities

    async def execute(self, context, on_progress=None) -> ExecutionResult:
        return ExecutionResult.from_success("done", self._capabilities.runtime_name)

    async def stream(self, context) -> AsyncIterator[str]:
        yield "chunk"

    async def interrupt(self, session_id: str, mode: str = "graceful") -> bool:
        return True

    def map_tools(self, kaizen_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return kaizen_tools

    def normalize_result(self, raw_result: Any) -> ExecutionResult:
        return ExecutionResult.from_success(
            str(raw_result), self._capabilities.runtime_name
        )


@pytest.fixture(autouse=True)
def clean_registry():
    """Clean registry before and after each test."""
    # Import the private registry to clean it
    from kaizen import runtime as runtime_module

    # Store original state
    original_registry = dict(runtime_module._runtime_registry)
    original_default = runtime_module._default_runtime

    # Clear for test
    runtime_module._runtime_registry.clear()
    runtime_module._default_runtime = "kaizen_local"

    yield

    # Restore original state
    runtime_module._runtime_registry.clear()
    runtime_module._runtime_registry.update(original_registry)
    runtime_module._default_runtime = original_default


class TestRegisterRuntime:
    """Test register_runtime function."""

    def test_register_runtime_success(self):
        """Test registering a runtime adapter."""
        adapter = MockRuntimeAdapter("test_runtime")

        register_runtime("test_runtime", adapter)

        assert get_runtime("test_runtime") is adapter

    def test_register_multiple_runtimes(self):
        """Test registering multiple runtimes."""
        adapter1 = MockRuntimeAdapter("runtime1")
        adapter2 = MockRuntimeAdapter("runtime2")

        register_runtime("runtime1", adapter1)
        register_runtime("runtime2", adapter2)

        assert get_runtime("runtime1") is adapter1
        assert get_runtime("runtime2") is adapter2
        assert len(list_runtimes()) == 2

    def test_register_overwrites_existing(self):
        """Test that registering with same name overwrites."""
        adapter1 = MockRuntimeAdapter("same_name")
        adapter2 = MockRuntimeAdapter("same_name")

        register_runtime("my_runtime", adapter1)
        register_runtime("my_runtime", adapter2)

        assert get_runtime("my_runtime") is adapter2

    def test_register_invalid_type(self):
        """Test registering non-adapter raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            register_runtime("invalid", "not an adapter")

        assert "RuntimeAdapter" in str(exc_info.value)

    def test_register_invalid_type_dict(self):
        """Test registering dict raises TypeError."""
        with pytest.raises(TypeError):
            register_runtime("invalid", {"name": "test"})


class TestUnregisterRuntime:
    """Test unregister_runtime function."""

    def test_unregister_existing(self):
        """Test unregistering an existing runtime."""
        adapter = MockRuntimeAdapter("to_remove")
        register_runtime("to_remove", adapter)

        result = unregister_runtime("to_remove")

        assert result is True
        assert get_runtime("to_remove") is None

    def test_unregister_nonexistent(self):
        """Test unregistering a non-existent runtime."""
        result = unregister_runtime("nonexistent")

        assert result is False


class TestGetRuntime:
    """Test get_runtime function."""

    def test_get_existing_runtime(self):
        """Test getting an existing runtime."""
        adapter = MockRuntimeAdapter("my_runtime")
        register_runtime("my_runtime", adapter)

        result = get_runtime("my_runtime")

        assert result is adapter

    def test_get_nonexistent_runtime(self):
        """Test getting a non-existent runtime returns None."""
        result = get_runtime("nonexistent")

        assert result is None


class TestGetAllRuntimes:
    """Test get_all_runtimes function."""

    def test_get_all_empty(self):
        """Test getting all runtimes when empty."""
        result = get_all_runtimes()

        assert result == {}

    def test_get_all_with_runtimes(self):
        """Test getting all registered runtimes."""
        adapter1 = MockRuntimeAdapter("runtime1")
        adapter2 = MockRuntimeAdapter("runtime2")
        register_runtime("runtime1", adapter1)
        register_runtime("runtime2", adapter2)

        result = get_all_runtimes()

        assert len(result) == 2
        assert "runtime1" in result
        assert "runtime2" in result

    def test_get_all_returns_copy(self):
        """Test get_all_runtimes returns a copy."""
        adapter = MockRuntimeAdapter("test")
        register_runtime("test", adapter)

        result1 = get_all_runtimes()
        result2 = get_all_runtimes()

        # Should be different dict objects
        assert result1 is not result2
        # But contain same values
        assert result1 == result2


class TestListRuntimes:
    """Test list_runtimes function."""

    def test_list_empty(self):
        """Test listing when no runtimes registered."""
        result = list_runtimes()

        assert result == []

    def test_list_with_runtimes(self):
        """Test listing registered runtimes."""
        register_runtime("a", MockRuntimeAdapter("a"))
        register_runtime("b", MockRuntimeAdapter("b"))
        register_runtime("c", MockRuntimeAdapter("c"))

        result = list_runtimes()

        assert len(result) == 3
        assert "a" in result
        assert "b" in result
        assert "c" in result


class TestSetDefaultRuntime:
    """Test set_default_runtime function."""

    def test_set_default_registered(self):
        """Test setting default to a registered runtime."""
        adapter = MockRuntimeAdapter("my_default")
        register_runtime("my_default", adapter)

        set_default_runtime("my_default")

        assert get_default_runtime() is adapter

    def test_set_default_unregistered(self):
        """Test setting default to unregistered runtime raises."""
        with pytest.raises(ValueError) as exc_info:
            set_default_runtime("not_registered")

        assert "not registered" in str(exc_info.value)


class TestGetDefaultRuntime:
    """Test get_default_runtime function."""

    def test_get_default_when_not_set(self):
        """Test getting default when it doesn't exist."""
        # Default is "kaizen_local" but it's not registered
        result = get_default_runtime()

        assert result is None

    def test_get_default_when_set(self):
        """Test getting default when properly set."""
        adapter = MockRuntimeAdapter("kaizen_local")
        register_runtime("kaizen_local", adapter)

        result = get_default_runtime()

        assert result is adapter


class TestCreateSelector:
    """Test create_selector function."""

    def test_create_selector_empty(self):
        """Test creating selector with no runtimes."""
        selector = create_selector()

        assert isinstance(selector, RuntimeSelector)
        assert len(selector.runtimes) == 0

    def test_create_selector_with_runtimes(self):
        """Test creating selector with registered runtimes."""
        register_runtime("runtime1", MockRuntimeAdapter("runtime1"))
        register_runtime("runtime2", MockRuntimeAdapter("runtime2"))

        selector = create_selector()

        assert isinstance(selector, RuntimeSelector)
        assert len(selector.runtimes) == 2
        assert "runtime1" in selector.runtimes
        assert "runtime2" in selector.runtimes

    def test_create_selector_uses_default(self):
        """Test created selector uses the default runtime."""
        adapter = MockRuntimeAdapter("my_default")
        register_runtime("my_default", adapter)
        set_default_runtime("my_default")

        selector = create_selector()

        assert selector.default_runtime == "my_default"


class TestIntegration:
    """Integration tests for registry functions."""

    def test_full_lifecycle(self):
        """Test complete runtime lifecycle."""
        # Register
        adapter = MockRuntimeAdapter("lifecycle_test")
        register_runtime("lifecycle_test", adapter)
        assert "lifecycle_test" in list_runtimes()

        # Set as default
        set_default_runtime("lifecycle_test")
        assert get_default_runtime() is adapter

        # Create selector
        selector = create_selector()
        assert selector.default_runtime == "lifecycle_test"

        # Unregister
        assert unregister_runtime("lifecycle_test") is True
        assert get_runtime("lifecycle_test") is None

    def test_multiple_operations(self):
        """Test multiple registry operations."""
        # Add several runtimes
        for i in range(5):
            register_runtime(f"runtime_{i}", MockRuntimeAdapter(f"runtime_{i}"))

        assert len(list_runtimes()) == 5

        # Remove some
        unregister_runtime("runtime_1")
        unregister_runtime("runtime_3")

        assert len(list_runtimes()) == 3
        assert "runtime_0" in list_runtimes()
        assert "runtime_1" not in list_runtimes()
        assert "runtime_2" in list_runtimes()
        assert "runtime_3" not in list_runtimes()
        assert "runtime_4" in list_runtimes()
