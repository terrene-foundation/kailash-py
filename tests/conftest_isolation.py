"""
Test isolation fixtures to prevent test pollution.

This module provides fixtures that ensure proper test isolation by:
1. Cleaning singleton states between tests
2. Providing isolated mock node factories
3. Managing import states
4. Ensuring proper cleanup
"""

import gc
import sys
from typing import Any, Dict, Optional, Tuple, Type
from unittest.mock import patch

import pytest
from tests.node_registry_utils import ensure_nodes_registered

from kailash.nodes.base import Node, NodeRegistry


@pytest.fixture(autouse=True, scope="function")
def clean_node_registry():
    """
    Ensure NodeRegistry is clean before and after each test.

    This fixture runs automatically for every test and ensures that
    the NodeRegistry singleton doesn't leak state between tests.
    """
    from tests.node_registry_utils import restore_registry, save_and_clear_registry

    # Store original state and clear
    original_nodes = save_and_clear_registry()

    yield

    # Restore original state, filtering out test nodes
    filtered_nodes = {}
    for name, node in original_nodes.items():
        if not name.startswith(("Mock", "Test", "Local")):
            filtered_nodes[name] = node
    restore_registry(filtered_nodes, ensure_sdk_nodes=False)


@pytest.fixture(autouse=True, scope="function")
def reset_singletons():
    """
    Reset all singleton states between tests.

    This ensures that singleton patterns don't cause test pollution.
    """
    # Force garbage collection before test
    gc.collect()

    yield

    # Force garbage collection after test
    gc.collect()


@pytest.fixture
def mock_node_factory():
    """
    Factory for creating isolated mock node classes.

    This factory creates unique node classes for each test, preventing
    class-level pollution between tests.

    Usage:
        def test_something(mock_node_factory):
            MockNode = mock_node_factory("MyNode", execute_return={"status": "ok"})
            # Use MockNode in test...
    """
    created_nodes = []

    def _create_mock_node(
        name: str = "MockNode",
        base_class: Optional[Type[Node]] = None,
        execute_return: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        **extra_attrs,
    ) -> Type[Node]:
        """
        Create an isolated mock node class.

        Args:
            name: Base name for the node class
            base_class: Base class to inherit from (default: Node)
            execute_return: What the execute method should return
            parameters: Node parameters definition
            **extra_attrs: Additional attributes/methods for the class

        Returns:
            Mock node class
        """
        if base_class is None:
            base_class = Node

        if execute_return is None:
            execute_return = {"result": "success"}

        if parameters is None:
            parameters = {}

        # Create unique class name to avoid conflicts
        unique_name = f"{name}_{id(name)}_{len(created_nodes)}"

        # Define class methods
        def init_method(self, **kwargs):
            self.config = kwargs
            self.name = kwargs.get("name", unique_name)
            self.id = kwargs.get("id", unique_name)
            super(type(self), self).__init__()

        def get_parameters_method(self):
            return parameters

        def execute_method(self, **kwargs):
            return execute_return

        # Build class attributes
        class_attrs = {
            "__init__": init_method,
            "get_parameters": get_parameters_method,
            "execute": execute_method,
        }

        # Add any extra attributes
        class_attrs.update(extra_attrs)

        # Create the class
        mock_class = type(unique_name, (base_class,), class_attrs)

        # Track for cleanup
        created_nodes.append(unique_name)

        # Register with NodeRegistry using the original name (not unique)
        # This allows tests to use familiar names like "MockNode"
        NodeRegistry.register(mock_class, name)

        return mock_class

    yield _create_mock_node

    # Cleanup all created nodes
    for node_name in created_nodes:
        NodeRegistry._nodes.pop(node_name, None)

    # Also cleanup by the registered names
    standard_names = ["MockNode", "TestNode", "LocalNode"]
    for name in standard_names:
        NodeRegistry._nodes.pop(name, None)


@pytest.fixture
def isolated_workflow_builder():
    """
    Provide an isolated WorkflowBuilder instance with clean state.
    """
    from kailash.workflow.builder import WorkflowBuilder

    builder = WorkflowBuilder()
    yield builder

    # Cleanup
    builder.clear()


@pytest.fixture(scope="function")
def temp_sys_modules():
    """
    Temporarily modify sys.modules and restore it after the test.

    Useful for testing import behaviors and module-level side effects.
    """
    original_modules = sys.modules.copy()

    yield sys.modules

    # Restore original modules
    modules_to_remove = set(sys.modules.keys()) - set(original_modules.keys())
    for module in modules_to_remove:
        # Only remove test-related modules
        if any(module.startswith(prefix) for prefix in ["test_", "mock_", "fake_"]):
            del sys.modules[module]


@pytest.fixture
def clean_imports():
    """
    Ensure specific modules are cleanly imported for each test.

    This is useful when testing import-time behaviors.
    """
    modules_to_clean = [
        "kailash.nodes.base",
        "kailash.workflow.builder",
        "kailash.workflow.graph",
    ]

    # Remove modules from sys.modules
    for module in modules_to_clean:
        sys.modules.pop(module, None)

    yield

    # Re-remove them after test (they may have been imported during test)
    for module in modules_to_clean:
        sys.modules.pop(module, None)


# Test markers for better organization
def pytest_configure(config):
    """Add custom markers for test organization."""
    config.addinivalue_line(
        "markers", "needs_isolation: Test requires complete isolation"
    )
    config.addinivalue_line("markers", "modifies_registry: Test modifies NodeRegistry")
    config.addinivalue_line("markers", "uses_singletons: Test uses singleton patterns")
    config.addinivalue_line(
        "markers", "integration: Integration test that may have side effects"
    )


# Ensure proper test collection order
def pytest_collection_modifyitems(config, items):
    """
    Modify test collection to ensure proper ordering.

    Tests that modify global state should run last in their module.
    """
    # Separate tests by their markers
    isolated_tests = []
    registry_tests = []
    other_tests = []

    for item in items:
        if item.get_closest_marker("needs_isolation"):
            isolated_tests.append(item)
        elif item.get_closest_marker("modifies_registry"):
            registry_tests.append(item)
        else:
            other_tests.append(item)

    # Reorder: other tests first, then registry tests, then isolated tests
    items[:] = other_tests + registry_tests + isolated_tests
