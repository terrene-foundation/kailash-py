"""Pytest plugin for handling tests that require isolation.

This plugin manages tests marked with @pytest.mark.requires_isolation.
When running with pytest-xdist (-n workers), tests naturally run in isolated
worker processes. For single-process runs, isolation is handled via fixtures.

Note: pytest-forked has been removed due to CVE-2022-42969 in its transitive
dependency (py library). Process isolation is now provided by pytest-xdist.
"""

import os

import pytest


def pytest_configure(config):
    """Register the isolation handling hooks."""
    config.addinivalue_line(
        "markers",
        "requires_isolation: mark test to run in isolated process (uses xdist workers)",
    )


def _is_xdist_worker():
    """Check if we're running as a pytest-xdist worker."""
    return os.environ.get("PYTEST_XDIST_WORKER") is not None


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle isolation requirements."""
    # Check if we should skip isolation tests
    try:
        if config.getoption("--no-isolation"):
            # Skip tests that require isolation
            skip_isolation = pytest.mark.skip(
                reason="Test requires isolation (use --run-isolation to run)"
            )
            for item in items:
                if item.get_closest_marker("requires_isolation"):
                    item.add_marker(skip_isolation)
            return
    except ValueError:
        # Option not registered yet
        pass

    # When running with xdist workers, tests are already isolated
    # No need to add special markers - each worker is a separate process


def pytest_addoption(parser):
    """Add command-line options for isolation handling."""
    parser.addoption(
        "--no-isolation",
        action="store_true",
        default=False,
        help="Skip tests that require isolation",
    )
    parser.addoption(
        "--run-isolation",
        action="store_true",
        default=False,
        help="Run only tests that require isolation",
    )


def pytest_runtest_setup(item):
    """Setup hook to handle isolation tests."""
    # If --run-isolation is specified, skip tests without requires_isolation
    try:
        if item.config.getoption("--run-isolation"):
            if not item.get_closest_marker("requires_isolation"):
                pytest.skip("Running only isolation tests")
    except ValueError:
        # Option not available
        pass
