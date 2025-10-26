"""
Utility script to check method parity between LocalRuntime and AsyncLocalRuntime.

Usage:
    python tests/parity/utils/check_method_parity.py
"""

import inspect
import sys

from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime

# Document runtime-specific methods that are ALLOWED to differ
ALLOWED_ASYNC_ONLY_METHODS = {
    "execute_workflow_async",  # Async-specific execution method
    "_execute_node_async",  # Async node execution
    "_execute_fully_async_workflow",  # Async workflow optimization
    "_execute_mixed_workflow",  # Mixed sync/async handling
    "_execute_sync_node_async",  # Sync node in async context
    "_execute_sync_node_in_thread",  # Thread pool execution
    "_execute_sync_workflow",  # Sync workflow in async runtime
    "_execute_sync_workflow_internal",
    "_prepare_async_node_inputs",  # Async input preparation
    "_prepare_sync_node_inputs",  # Sync input preparation
}

ALLOWED_SYNC_ONLY_METHODS = set()  # Currently none - async inherits from sync


def get_public_methods(cls):
    """Get all public methods from a class."""
    return {
        name
        for name in dir(cls)
        if not name.startswith("__") and callable(getattr(cls, name))
    }


def main():
    """Check method parity and exit with appropriate status code."""
    local_methods = get_public_methods(LocalRuntime)
    async_methods = get_public_methods(AsyncLocalRuntime)

    print(f"LocalRuntime:      {len(local_methods)} methods")
    print(f"AsyncLocalRuntime: {len(async_methods)} methods")
    print()

    # Check for missing methods in AsyncLocalRuntime
    missing_in_async = local_methods - async_methods - ALLOWED_SYNC_ONLY_METHODS

    if missing_in_async:
        print(
            "❌ PARITY VIOLATION: AsyncLocalRuntime missing methods from LocalRuntime:"
        )
        for method in sorted(missing_in_async):
            print(f"   - {method}")
        print()
        print("These methods must be implemented in AsyncLocalRuntime.")
        print(
            "If they are intentionally sync-only, add them to ALLOWED_SYNC_ONLY_METHODS."
        )
        sys.exit(1)

    # Check for undocumented async-only methods
    extra_in_async = (async_methods - local_methods) - ALLOWED_ASYNC_ONLY_METHODS

    if extra_in_async:
        print("⚠️  WARNING: Undocumented async-only methods in AsyncLocalRuntime:")
        for method in sorted(extra_in_async):
            print(f"   - {method}")
        print()
        print(
            "Add these to ALLOWED_ASYNC_ONLY_METHODS with documentation if intentional."
        )
        sys.exit(1)

    # Success
    print("✅ Method parity check PASSED")
    print(f"   LocalRuntime:      {len(local_methods)} methods")
    print(f"   AsyncLocalRuntime: {len(async_methods)} methods")
    print(f"   Shared methods:    {len(local_methods & async_methods)}")
    print(f"   Async-only:        {len(ALLOWED_ASYNC_ONLY_METHODS)}")
    sys.exit(0)


if __name__ == "__main__":
    main()
