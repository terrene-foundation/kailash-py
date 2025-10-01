"""
Kailash SDK Nodes Module - Safe Lazy Loading Implementation

This implementation provides lazy loading with circular dependency protection
and maintains full backward compatibility.
"""

import importlib
import sys
import warnings
from typing import Any, Dict, Optional, Set

# Core imports that are always needed
from .base import Node, NodeParameter, NodeRegistry

# Track loading state to detect circular dependencies
_LOADING_STACK: Set[str] = set()
_LOADED_MODULES: Dict[str, Optional[Any]] = {}

# Define available node categories for lazy loading
_NODE_CATEGORIES = [
    "ai",
    "alerts",
    "api",
    "auth",
    "cache",
    "code",
    "compliance",
    "data",
    "edge",
    "enterprise",
    "logic",
    "mixins",
    "monitoring",
    "rag",
    "security",
    "testing",
    "transaction",
    "transform",
    "validation",
]

# Initialize lazy module cache
_LAZY_MODULES: Dict[str, Optional[Any]] = {
    category: None for category in _NODE_CATEGORIES
}


def _safe_lazy_import(name: str) -> Any:
    """
    Safely import a module with circular dependency detection.

    Args:
        name: The module name to import

    Returns:
        The imported module

    Raises:
        ImportError: If a circular dependency is detected
    """
    full_module_name = f"kailash.nodes.{name}"

    # Check if already loaded
    if name in _LOADED_MODULES:
        return _LOADED_MODULES[name]

    # Check for circular dependency
    if full_module_name in _LOADING_STACK:
        cycle_modules = list(_LOADING_STACK) + [full_module_name]
        warnings.warn(
            f"Circular dependency detected: {' -> '.join(cycle_modules)}. "
            f"Using partial import to break the cycle.",
            ImportWarning,
            stacklevel=3,
        )
        # Return a placeholder that will be populated after loading
        module = sys.modules.get(full_module_name)
        if module:
            return module
        # Create empty module as placeholder
        module = type(sys)("placeholder")
        sys.modules[full_module_name] = module
        return module

    # Add to loading stack
    _LOADING_STACK.add(full_module_name)

    try:
        # Perform the actual import
        module = importlib.import_module(f".{name}", package="kailash.nodes")
        _LOADED_MODULES[name] = module
        return module
    finally:
        # Remove from loading stack
        _LOADING_STACK.discard(full_module_name)


def __getattr__(name: str) -> Any:
    """
    Lazy loading of node category modules with circular dependency protection.

    This function is called when accessing an attribute that doesn't exist
    in the module's namespace. It enables lazy loading of node categories
    while detecting and handling circular dependencies.

    Args:
        name: The attribute name being accessed

    Returns:
        The requested module or attribute

    Raises:
        AttributeError: If the attribute doesn't exist
    """
    # Check if it's a known node category
    if name in _LAZY_MODULES:
        if _LAZY_MODULES[name] is None:
            try:
                # Use safe import with circular dependency detection
                _LAZY_MODULES[name] = _safe_lazy_import(name)
            except ImportError as e:
                # Log the error and re-raise
                import logging

                logging.error(f"Failed to import kailash.nodes.{name}: {e}")
                raise
        return _LAZY_MODULES[name]

    # Handle special attributes
    if name == "__all__":
        return ["Node", "NodeParameter", "NodeRegistry"] + _NODE_CATEGORIES

    # Attribute not found
    raise AttributeError(f"module 'kailash.nodes' has no attribute '{name}'")


def __dir__():
    """Return the list of available attributes for tab completion."""
    return ["Node", "NodeParameter", "NodeRegistry"] + _NODE_CATEGORIES


def check_circular_dependencies() -> Dict[str, Any]:
    """
    Check for circular dependencies in the nodes module.

    Returns:
        A dictionary containing:
        - has_circular_deps: Boolean indicating if circular deps exist
        - circular_chains: List of circular dependency chains found
        - warnings: List of warning messages
    """
    from pathlib import Path

    from ..utils.circular_dependency_detector import CircularDependencyDetector

    # Get the SDK root directory
    sdk_root = Path(__file__).parent.parent.parent

    detector = CircularDependencyDetector(sdk_root)
    detector.build_import_graph("src/kailash/nodes")
    cycles = detector.detect_cycles()

    result = {
        "has_circular_deps": bool(cycles),
        "circular_chains": cycles,
        "warnings": [],
    }

    if cycles:
        for cycle in cycles:
            result["warnings"].append(
                f"Circular dependency detected: {' -> '.join(cycle)} -> {cycle[0]}"
            )

    return result


def preload_all_categories():
    """
    Preload all node categories (useful for testing or warming up).

    This function loads all node categories immediately rather than lazily.
    It's useful for:
    - Testing that all imports work correctly
    - Warming up the import cache
    - Detecting circular dependencies early
    """
    failed_imports = []

    for category in _NODE_CATEGORIES:
        try:
            _safe_lazy_import(category)
        except ImportError as e:
            failed_imports.append((category, str(e)))

    if failed_imports:
        warnings.warn(
            f"Failed to import some categories: {failed_imports}", ImportWarning
        )

    return {
        "loaded": [cat for cat in _NODE_CATEGORIES if cat in _LOADED_MODULES],
        "failed": failed_imports,
    }


# Performance monitoring
def get_import_stats() -> Dict[str, Any]:
    """
    Get statistics about module imports.

    Returns:
        Dictionary containing import statistics
    """
    return {
        "loaded_modules": list(_LOADED_MODULES.keys()),
        "pending_modules": [
            cat for cat in _NODE_CATEGORIES if cat not in _LOADED_MODULES
        ],
        "total_categories": len(_NODE_CATEGORIES),
        "loaded_count": len(_LOADED_MODULES),
        "currently_loading": list(_LOADING_STACK),
    }


# Backward compatibility - ensure all existing imports work
__all__ = ["Node", "NodeParameter", "NodeRegistry"] + _NODE_CATEGORIES

# Export core components directly
