"""EATP test configuration and shared fixtures."""

import pytest


@pytest.fixture
def tmp_store_dir(tmp_path):
    """Temporary directory for filesystem store tests."""
    store_dir = tmp_path / ".eatp"
    store_dir.mkdir()
    return store_dir
