"""Centralized utilities for managing NodeRegistry in tests."""

import os

from kailash.nodes.base import NodeRegistry


def ensure_nodes_registered():
    """Ensure all SDK nodes are registered in the NodeRegistry.

    This function should be called after any operation that clears the registry
    to ensure all standard SDK nodes are available for tests.
    """
    import importlib
    import logging
    import sys

    # Debug: log the current state
    logging.debug(
        f"ensure_nodes_registered called. Current registry size: {len(NodeRegistry._nodes)}"
    )

    # First, check if nodes are already registered
    if NodeRegistry._nodes:
        # If we already have nodes, just ensure we have the common ones
        required_nodes = [
            "PythonCodeNode",
            "CSVReaderNode",
            "HTTPRequestNode",
            "SQLDatabaseNode",
        ]
        missing = [node for node in required_nodes if node not in NodeRegistry._nodes]
        if not missing:
            logging.debug("All required nodes already present")
            return  # All required nodes present

    # Don't clear module cache in non-forked mode to preserve class identities
    # Only clear in forked processes where we have no choice
    if os.environ.get("_PYTEST_FORKED"):
        modules_to_reload = []
        for module_name in list(sys.modules.keys()):
            if module_name.startswith("kailash.nodes."):
                modules_to_reload.append(module_name)

        # Remove modules from sys.modules to force fresh import
        for module_name in modules_to_reload:
            sys.modules.pop(module_name, None)

    try:
        # Import specific node modules directly to trigger decorators
        # These imports MUST happen after clearing sys.modules
        from kailash.nodes.api.http import HTTPRequestNode
        from kailash.nodes.code.python import PythonCodeNode
        from kailash.nodes.data.readers import CSVReaderNode, JSONReaderNode
        from kailash.nodes.data.sql import SQLDatabaseNode

        # Force registration if not already registered
        # Use try/except because after sys.modules clearing, class hierarchy checks may fail
        if "PythonCodeNode" not in NodeRegistry._nodes:
            try:
                NodeRegistry.register(PythonCodeNode, "PythonCodeNode")
            except Exception:
                pass  # Ignore if already registered via decorator
        if "CSVReaderNode" not in NodeRegistry._nodes:
            try:
                NodeRegistry.register(CSVReaderNode, "CSVReaderNode")
            except Exception:
                pass
        if "JSONReaderNode" not in NodeRegistry._nodes:
            try:
                NodeRegistry.register(JSONReaderNode, "JSONReaderNode")
            except Exception:
                pass
        if "HTTPRequestNode" not in NodeRegistry._nodes:
            try:
                NodeRegistry.register(HTTPRequestNode, "HTTPRequestNode")
            except Exception:
                pass
        if "SQLDatabaseNode" not in NodeRegistry._nodes:
            try:
                NodeRegistry.register(SQLDatabaseNode, "SQLDatabaseNode")
            except Exception:
                pass

    except ImportError as e:
        # If imports fail, try to at least import the main module
        try:
            import kailash.nodes

            # Force reload all submodules
            for attr_name in dir(kailash.nodes):
                attr = getattr(kailash.nodes, attr_name)
                if hasattr(attr, "__file__"):
                    importlib.reload(attr)
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
