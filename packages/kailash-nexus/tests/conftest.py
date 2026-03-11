"""Pytest configuration for Kailash Nexus tests.

Provides shared fixtures and test configuration.
"""

import os
import sys
from pathlib import Path

import pytest

# Add parent directories to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Add SDK test utilities
sdk_root = project_root.parent.parent
sys.path.insert(0, str(sdk_root / "tests"))

# Add kailash-dataflow src for dataflow imports
sys.path.insert(0, str(project_root.parent / "kailash-dataflow" / "src"))


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test (fast, isolated)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test (uses real services)"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as an end-to-end test (complete user flows)"
    )


@pytest.fixture
def clean_imports():
    """Clean imports to ensure test isolation."""
    # Store original modules
    original_modules = sys.modules.copy()

    yield

    # Restore original modules
    sys.modules.clear()
    sys.modules.update(original_modules)


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace for tests."""
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    yield tmp_path

    os.chdir(original_cwd)


@pytest.fixture
def mock_workflow():
    """Create a mock workflow for testing."""
    from kailash.workflow.builder import WorkflowBuilder

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "test", {"code": "result = {'test': True}"})
    return workflow.build()


# Test execution settings
def pytest_collection_modifyitems(config, items):
    """Modify test collection for better organization."""
    # Add markers based on test location
    for item in items:
        # Add marker based on directory
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
