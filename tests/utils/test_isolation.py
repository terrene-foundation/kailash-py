"""Test isolation utilities to prevent test interference and pollution.

This module provides utilities to isolate tests from each other, preventing
issues like shared state pollution, NodeRegistry contamination, and test
order dependencies.
"""

from typing import Any, Dict, Set
from unittest.mock import patch

import pytest
from kailash.nodes.base import NodeRegistry


class TestIsolation:
    """Test isolation utilities for clean test execution."""

    def __init__(self):
        self._original_registry: Dict[str, Any] = {}
        self._original_instance: Any = None

    def save_node_registry_state(self):
        """Save the current NodeRegistry state."""
        self._original_registry = NodeRegistry._nodes.copy()
        self._original_instance = NodeRegistry._instance

    def restore_node_registry_state(self):
        """Restore the NodeRegistry to its original state."""
        NodeRegistry._nodes.clear()
        NodeRegistry._nodes.update(self._original_registry)
        NodeRegistry._instance = self._original_instance

    def clear_node_registry(self):
        """Clear the NodeRegistry completely."""
        NodeRegistry._nodes.clear()
        NodeRegistry._instance = None

    def register_test_nodes(self, test_nodes: Dict[str, Any]):
        """Register test-specific nodes."""
        for name, node_class in test_nodes.items():
            NodeRegistry._nodes[name] = node_class


# Global test isolation instance
test_isolation = TestIsolation()


@pytest.fixture(autouse=True)
def isolate_node_registry():
    """Automatically isolate NodeRegistry for each test."""
    # Save original state
    test_isolation.save_node_registry_state()

    yield

    # Restore original state
    test_isolation.restore_node_registry_state()


@pytest.fixture
def clean_node_registry():
    """Provide a completely clean NodeRegistry for tests."""
    # Clear registry completely
    test_isolation.clear_node_registry()

    yield

    # Restore original state
    test_isolation.restore_node_registry_state()


@pytest.fixture
def isolated_test_environment():
    """Provide a completely isolated test environment."""
    # Save original state
    test_isolation.save_node_registry_state()

    # Clear registry for clean slate
    test_isolation.clear_node_registry()

    yield test_isolation

    # Restore original state
    test_isolation.restore_node_registry_state()


class MockNodeRegistry:
    """Mock NodeRegistry for testing without side effects."""

    def __init__(self):
        self._nodes: Dict[str, Any] = {}
        self._instance = None

    def register(self, node_class: Any, alias: str = None):
        """Register a node class in the mock registry."""
        name = alias or node_class.__name__
        self._nodes[name] = node_class

    def get_node(self, name: str):
        """Get a node class by name."""
        return self._nodes.get(name)

    def list_nodes(self):
        """List all registered nodes."""
        return list(self._nodes.keys())

    def clear(self):
        """Clear the mock registry."""
        self._nodes.clear()
        self._instance = None


@pytest.fixture
def mock_node_registry():
    """Provide a mock NodeRegistry for testing."""
    mock_registry = MockNodeRegistry()

    with patch("kailash.nodes.base.NodeRegistry", mock_registry):
        yield mock_registry


def ensure_test_isolation(test_func):
    """Decorator to ensure test isolation."""

    def wrapper(*args, **kwargs):
        # Save state
        test_isolation.save_node_registry_state()

        try:
            # Run test
            return test_func(*args, **kwargs)
        finally:
            # Restore state
            test_isolation.restore_node_registry_state()

    return wrapper


class TestOrderValidator:
    """Utility to validate test order independence."""

    def __init__(self):
        self._test_states: Dict[str, Dict[str, Any]] = {}

    def capture_state(self, test_name: str):
        """Capture the current state for a test."""
        self._test_states[test_name] = {
            "node_registry_size": len(NodeRegistry._nodes),
            "node_registry_keys": set(NodeRegistry._nodes.keys()),
            "node_registry_instance": NodeRegistry._instance is not None,
        }

    def validate_state_isolation(
        self, test_name: str, expected_initial_state: Dict[str, Any]
    ):
        """Validate that test state matches expected initial state."""
        if test_name not in self._test_states:
            return True

        actual_state = self._test_states[test_name]

        # Check if state matches expected initial state
        for key, expected_value in expected_initial_state.items():
            if key in actual_state:
                if actual_state[key] != expected_value:
                    return False

        return True

    def detect_test_pollution(self) -> Dict[str, Any]:
        """Detect potential test pollution between tests."""
        pollution_report = {
            "registry_size_changes": [],
            "registry_key_changes": [],
            "instance_changes": [],
        }

        test_names = list(self._test_states.keys())
        for i in range(len(test_names) - 1):
            current_test = test_names[i]
            next_test = test_names[i + 1]

            current_state = self._test_states[current_test]
            next_state = self._test_states[next_test]

            # Check for registry size changes
            if current_state["node_registry_size"] != next_state["node_registry_size"]:
                pollution_report["registry_size_changes"].append(
                    {
                        "from_test": current_test,
                        "to_test": next_test,
                        "size_change": next_state["node_registry_size"]
                        - current_state["node_registry_size"],
                    }
                )

            # Check for registry key changes
            current_keys = current_state["node_registry_keys"]
            next_keys = next_state["node_registry_keys"]
            if current_keys != next_keys:
                pollution_report["registry_key_changes"].append(
                    {
                        "from_test": current_test,
                        "to_test": next_test,
                        "added_keys": next_keys - current_keys,
                        "removed_keys": current_keys - next_keys,
                    }
                )

            # Check for instance changes
            if (
                current_state["node_registry_instance"]
                != next_state["node_registry_instance"]
            ):
                pollution_report["instance_changes"].append(
                    {
                        "from_test": current_test,
                        "to_test": next_test,
                        "instance_created": next_state["node_registry_instance"],
                    }
                )

        return pollution_report


# Global test order validator
test_order_validator = TestOrderValidator()


@pytest.fixture
def test_order_validation():
    """Provide test order validation for detecting test pollution."""
    yield test_order_validator


def reset_global_state():
    """Reset all global state for testing."""
    # Reset NodeRegistry
    NodeRegistry._nodes.clear()
    NodeRegistry._instance = None

    # Reset any other global state here
    # Add more global state resets as needed


@pytest.fixture(scope="function")
def reset_all_global_state():
    """Reset all global state before and after each test."""
    reset_global_state()
    yield
    reset_global_state()


class TestStateSnapshot:
    """Utility to capture and restore test state snapshots."""

    def __init__(self):
        self.snapshots: Dict[str, Dict[str, Any]] = {}

    def capture_snapshot(self, name: str):
        """Capture a snapshot of the current state."""
        self.snapshots[name] = {
            "node_registry_nodes": NodeRegistry._nodes.copy(),
            "node_registry_instance": NodeRegistry._instance,
            # Add more state as needed
        }

    def restore_snapshot(self, name: str):
        """Restore a previously captured snapshot."""
        if name not in self.snapshots:
            raise ValueError(f"Snapshot '{name}' not found")

        snapshot = self.snapshots[name]

        # Restore NodeRegistry
        NodeRegistry._nodes.clear()
        NodeRegistry._nodes.update(snapshot["node_registry_nodes"])
        NodeRegistry._instance = snapshot["node_registry_instance"]

        # Restore other state as needed

    def clear_snapshots(self):
        """Clear all snapshots."""
        self.snapshots.clear()


@pytest.fixture
def test_state_snapshot():
    """Provide test state snapshot functionality."""
    snapshot = TestStateSnapshot()
    yield snapshot
    snapshot.clear_snapshots()


# Utility functions for common test isolation patterns
def with_clean_registry(test_func):
    """Decorator to run a test with a clean NodeRegistry."""

    def wrapper(*args, **kwargs):
        # Save original state
        original_nodes = NodeRegistry._nodes.copy()
        original_instance = NodeRegistry._instance

        # Clear registry
        NodeRegistry._nodes.clear()
        NodeRegistry._instance = None

        try:
            return test_func(*args, **kwargs)
        finally:
            # Restore original state
            NodeRegistry._nodes.clear()
            NodeRegistry._nodes.update(original_nodes)
            NodeRegistry._instance = original_instance

    return wrapper


def with_isolated_registry(test_func):
    """Decorator to run a test with an isolated NodeRegistry."""

    def wrapper(*args, **kwargs):
        # Save original state
        original_nodes = NodeRegistry._nodes.copy()
        original_instance = NodeRegistry._instance

        try:
            return test_func(*args, **kwargs)
        finally:
            # Restore original state
            NodeRegistry._nodes.clear()
            NodeRegistry._nodes.update(original_nodes)
            NodeRegistry._instance = original_instance

    return wrapper
