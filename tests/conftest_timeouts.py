"""
Timeout configuration for different test tiers.

This module enforces strict timeout limits based on test location:
- Unit tests: 1 second
- Integration tests: 5 seconds
- E2E tests: 10 seconds
"""

import pytest


def pytest_collection_modifyitems(config, items):
    """Apply timeout markers based on test location."""
    for item in items:
        # Get the test file path
        test_path = str(item.fspath)

        # Apply timeouts based on directory
        if "/tests/unit/" in test_path:
            # Unit tests: 1 second max (5 seconds for tests with heavy imports)
            # Tests that import heavy modules need more time in worker processes
            needs_extended_timeout = any(
                [
                    "pythoncode" in test_path.lower(),
                    "python_code" in test_path.lower(),
                    "embedding" in test_path.lower(),  # sklearn imports
                    "test_access_controlled" in test_path,  # imports many nodes
                    "test_parameter_injection" in test_path,  # complex node setups
                    "test_workflow_builder_api"
                    in test_path,  # node registry operations
                    "test_node_constructor_mapping"
                    in test_path,  # multiple node imports
                ]
            )

            if needs_extended_timeout:
                item.add_marker(pytest.mark.timeout(5))
            else:
                item.add_marker(pytest.mark.timeout(1))
        elif "/tests/integration/" in test_path:
            # Integration tests: 5 seconds max
            item.add_marker(pytest.mark.timeout(5))
        elif "/tests/e2e/" in test_path:
            # E2E tests: 10 seconds max
            item.add_marker(pytest.mark.timeout(10))
        else:
            # Default: 5 seconds
            item.add_marker(pytest.mark.timeout(5))
