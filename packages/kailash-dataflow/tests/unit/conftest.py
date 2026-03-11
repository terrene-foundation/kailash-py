#!/usr/bin/env python3
"""
Unit Test Configuration (Tier 1)

Provides standardized fixtures and configuration for DataFlow unit tests.
Follows the three-tier testing strategy with proper isolation and mocking.

This file provides fixtures specifically for Tier 1 (unit) tests:
- ✅ SQLite databases (both :memory: and file-based)
- ✅ Mocks and stubs for external services
- ❌ NO PostgreSQL connections (use integration tests instead)
"""

from typing import AsyncGenerator

import pytest

from tests.fixtures.unit_test_harness import (
    MockingUtilities,
    StandardUnitFixtures,
    UnitTestDatabaseConfig,
    UnitTestSuite,
)

# Standard unit test suite fixtures


@pytest.fixture
async def unit_test_suite():
    """Create standard memory-based unit test suite."""
    suite = StandardUnitFixtures.memory_test_suite()
    async with suite.session():
        yield suite


@pytest.fixture
async def memory_test_suite():
    """Create memory-based SQLite unit test suite for fast tests."""
    config = UnitTestDatabaseConfig.memory_database()
    suite = UnitTestSuite(config)
    async with suite.session():
        yield suite


@pytest.fixture
async def file_test_suite():
    """Create file-based SQLite unit test suite for persistent tests."""
    config = UnitTestDatabaseConfig.file_database()
    suite = UnitTestSuite(config)
    async with suite.session():
        yield suite


# Database connection fixtures


@pytest.fixture
async def sqlite_memory_connection(memory_test_suite):
    """Provide SQLite memory connection for unit tests."""
    async with memory_test_suite.get_connection() as conn:
        yield conn


@pytest.fixture
async def sqlite_file_connection(file_test_suite):
    """Provide SQLite file connection for unit tests."""
    async with file_test_suite.get_connection() as conn:
        yield conn


# DataFlow fixtures


@pytest.fixture
async def memory_dataflow(memory_test_suite):
    """Create DataFlow instance with memory database for unit tests."""
    dataflow = memory_test_suite.dataflow_harness.create_dataflow()
    yield dataflow


@pytest.fixture
async def file_dataflow(file_test_suite):
    """Create DataFlow instance with file database for unit tests."""
    dataflow = file_test_suite.dataflow_harness.create_dataflow()
    yield dataflow


@pytest.fixture
async def auto_migrate_dataflow(memory_test_suite):
    """Create DataFlow instance with auto-migration enabled."""
    dataflow = memory_test_suite.dataflow_harness.create_dataflow(auto_migrate=True)
    yield dataflow


# Table factory fixtures


@pytest.fixture
async def basic_test_table(memory_test_suite):
    """Create basic test table with standard schema."""
    table_name = (
        await memory_test_suite.dataflow_harness.table_factory.create_basic_table()
    )
    yield table_name


@pytest.fixture
async def constrained_test_tables(memory_test_suite):
    """Create test tables with constraints and foreign keys."""
    tables = (
        await memory_test_suite.dataflow_harness.table_factory.create_constrained_table()
    )
    yield tables


# Mocking utilities fixtures


@pytest.fixture
def mock_connection_manager():
    """Create mock connection manager for unit tests."""
    return MockingUtilities.mock_connection_manager()


@pytest.fixture
def mock_migration_executor():
    """Create mock migration executor for unit tests."""
    return MockingUtilities.mock_migration_executor()


@pytest.fixture
def mock_dataflow_engine():
    """Create mock DataFlow engine for unit tests."""
    return MockingUtilities.mock_dataflow_engine()


@pytest.fixture
def mock_postgresql_config():
    """Create mock PostgreSQL config for unit tests."""
    return StandardUnitFixtures.mock_postgresql_config()


# Test isolation markers


def pytest_configure(config):
    """Configure custom pytest markers for unit tests."""
    config.addinivalue_line("markers", "unit: mark test as a unit test (Tier 1)")
    config.addinivalue_line(
        "markers", "sqlite_memory: mark test as using SQLite memory database"
    )
    config.addinivalue_line(
        "markers", "sqlite_file: mark test as using SQLite file database"
    )
    config.addinivalue_line("markers", "mocking: mark test as using mocks/stubs")


# Test collection configuration


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location and patterns."""
    for item in items:
        # Auto-mark all tests in unit/ directory as unit tests
        if "tests/unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Mark tests that use specific fixtures
        if hasattr(item, "fixturenames"):
            if any(fixture.startswith("memory_") for fixture in item.fixturenames):
                item.add_marker(pytest.mark.sqlite_memory)
            if any(fixture.startswith("file_") for fixture in item.fixturenames):
                item.add_marker(pytest.mark.sqlite_file)
            if any(fixture.startswith("mock_") for fixture in item.fixturenames):
                item.add_marker(pytest.mark.mocking)


# Performance and timeout settings for unit tests


@pytest.fixture(autouse=True)
def unit_test_timeout():
    """Apply default timeout to unit tests (should be fast)."""
    # Unit tests should complete quickly - no timeout fixture needed
    # as pytest-timeout handles this via pytest.ini or command line
    pass
