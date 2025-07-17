"""Centralized utilities for managing NodeRegistry in tests."""

from kailash.nodes.base import NodeRegistry


def ensure_nodes_registered():
    """Ensure all SDK nodes are registered in the NodeRegistry.

    This function should be called after any operation that clears the registry
    to ensure all standard SDK nodes are available for tests.
    """
    try:
        # Import the main nodes module which triggers all @register_node decorators
        # The __init__.py imports all submodules, triggering registration
        # Force reimport to ensure decorators fire even if already imported
        import importlib

        import kailash.nodes

        importlib.reload(kailash.nodes)
    except ImportError:
        # If main import fails, try individual imports
        try:
            from kailash.nodes.ai import embeddings, llm
            from kailash.nodes.api import graphql, http
            from kailash.nodes.code import python
            from kailash.nodes.data import cache, readers, sql, writers
            from kailash.nodes.logic import conditions, operations
            from kailash.nodes.security import auth, behavior_analysis
            from kailash.nodes.transform import data_transform
        except ImportError:
            pass  # Some modules may not be available in all environments


def save_and_clear_registry():
    """Save current registry state and clear it.

    Returns:
        dict: The original node registry state
    """
    original_nodes = NodeRegistry._nodes.copy()
    NodeRegistry._nodes.clear()
    return original_nodes


def restore_registry(original_nodes, ensure_sdk_nodes=True):
    """Restore registry to a previous state.

    Args:
        original_nodes: The saved registry state
        ensure_sdk_nodes: If True, ensure SDK nodes are registered after restore
    """
    NodeRegistry._nodes.clear()
    NodeRegistry._nodes.update(original_nodes)

    if ensure_sdk_nodes and not NodeRegistry._nodes:
        # If registry is empty after restore, ensure SDK nodes are available
        ensure_nodes_registered()
