"""Pytest plugin for handling tests that require isolation.

This plugin runs tests marked with @pytest.mark.requires_isolation using pytest-forked
to ensure they run in a clean process without state pollution.
"""

import pytest


def pytest_configure(config):
    """Register the isolation handling hooks."""
    config.addinivalue_line(
        "markers",
        "requires_isolation: mark test to run in isolated process (uses forked)",
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle isolation requirements."""
    # Check if we're already running with --forked
    try:
        if config.getoption("--forked"):
            # Already using forked, no need to modify
            return
    except ValueError:
        # --forked option not available, continue
        pass

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

    # Add forked marker to tests that require isolation (only if forked plugin is available)
    # Check if forked plugin is loaded by checking if the plugin is in the plugin manager
    if config.pluginmanager.has_plugin("pytest_forked"):
        for item in items:
            if item.get_closest_marker("requires_isolation"):
                # Add the forked marker to run this test in isolation
                item.add_marker(pytest.mark.forked)


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
