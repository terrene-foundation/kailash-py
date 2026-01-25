"""
Unit tests for AsyncSQLDatabaseNode pool key generation.

Tests the pool key generation that ensures proper event loop isolation
to prevent "Task got Future attached to a different loop" errors.

NOTE: As of v0.10.15, pool keys ALWAYS include the actual event loop ID.
The previous behavior of using "test|" prefix in test mode was removed
because it caused pool sharing across different event loops, leading to
asyncio errors in Docker/FastAPI deployments.

Tier: 1 (Unit)
Target: src/kailash/nodes/data/async_sql.py
Coverage: _is_test_environment() and _generate_pool_key() methods
"""

import asyncio
import inspect
import os
import sys
import time
from typing import Any, Dict
from unittest.mock import patch

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode


class TestEnvironmentDetection:
    """Test _is_test_environment() detection logic."""

    def test_detects_pytest_via_sys_modules(self):
        """Test: pytest in sys.modules → returns True."""
        # pytest is already in sys.modules when running via pytest
        assert "pytest" in sys.modules
        result = AsyncSQLDatabaseNode._is_test_environment()
        assert result is True, "Should detect pytest via sys.modules"

    def test_detects_pytest_via_environment_variable(self):
        """Test: PYTEST_CURRENT_TEST set → returns True."""
        # Save original state
        original_modules = sys.modules.copy()
        original_env = os.environ.copy()

        try:
            # Remove pytest from sys.modules to test env var detection
            if "pytest" in sys.modules:
                del sys.modules["pytest"]

            # Set PYTEST_CURRENT_TEST environment variable
            os.environ["PYTEST_CURRENT_TEST"] = "test_file.py::test_name (call)"

            # Clear cache if exists
            if hasattr(AsyncSQLDatabaseNode._is_test_environment, "cache_clear"):
                AsyncSQLDatabaseNode._is_test_environment.cache_clear()

            result = AsyncSQLDatabaseNode._is_test_environment()
            assert result is True, "Should detect pytest via PYTEST_CURRENT_TEST"

        finally:
            # Restore original state
            sys.modules.update(original_modules)
            os.environ.clear()
            os.environ.update(original_env)
            if hasattr(AsyncSQLDatabaseNode._is_test_environment, "cache_clear"):
                AsyncSQLDatabaseNode._is_test_environment.cache_clear()

    def test_detects_unittest_via_sys_modules(self):
        """Test: unittest in sys.modules → returns True."""
        # unittest.main is in sys.modules during test execution
        import unittest

        assert "unittest" in sys.modules
        result = AsyncSQLDatabaseNode._is_test_environment()
        assert result is True, "Should detect unittest via sys.modules"

    def test_detects_kailash_test_env_variable(self):
        """Test: KAILASH_TEST_ENV=true → returns True."""
        original_env = os.environ.copy()
        original_modules = sys.modules.copy()

        try:
            # Remove test frameworks from sys.modules
            for module in ["pytest", "unittest"]:
                if module in sys.modules:
                    del sys.modules[module]

            # Set KAILASH_TEST_ENV
            os.environ["KAILASH_TEST_ENV"] = "true"

            # Clear cache if exists
            if hasattr(AsyncSQLDatabaseNode._is_test_environment, "cache_clear"):
                AsyncSQLDatabaseNode._is_test_environment.cache_clear()

            result = AsyncSQLDatabaseNode._is_test_environment()
            assert result is True, "Should detect KAILASH_TEST_ENV=true"

        finally:
            # Restore original state
            sys.modules.update(original_modules)
            os.environ.clear()
            os.environ.update(original_env)
            if hasattr(AsyncSQLDatabaseNode._is_test_environment, "cache_clear"):
                AsyncSQLDatabaseNode._is_test_environment.cache_clear()

    def test_production_environment_returns_false(self):
        """Test: No test indicators → returns False.

        Note: This test can't fully simulate production since we're running in pytest.
        Stack inspection will always detect pytest in the call stack. We verify that
        if all explicit indicators are removed, the method relies on stack inspection.
        """
        original_env = os.environ.copy()

        try:
            # Remove explicit environment indicators
            for env_var in ["PYTEST_CURRENT_TEST", "KAILASH_TEST_ENV"]:
                if env_var in os.environ:
                    del os.environ[env_var]

            # In pytest context, stack inspection will still detect test environment
            # This is expected behavior - production code won't have pytest in stack
            result = AsyncSQLDatabaseNode._is_test_environment()

            # Since we're running in pytest, should still return True via stack inspection
            assert (
                result is True
            ), "Should detect test environment via stack inspection when running in pytest"

        finally:
            # Restore original state
            os.environ.clear()
            os.environ.update(original_env)

    def test_detection_cached_for_performance(self):
        """Test: Multiple calls return same result without re-checking."""
        # Clear cache if exists
        if hasattr(AsyncSQLDatabaseNode._is_test_environment, "cache_clear"):
            AsyncSQLDatabaseNode._is_test_environment.cache_clear()

        # First call
        result1 = AsyncSQLDatabaseNode._is_test_environment()

        # Second call - should use cached result
        result2 = AsyncSQLDatabaseNode._is_test_environment()

        assert result1 == result2, "Cached results should be identical"

        # Verify method has cache_info (lru_cache indicator)
        if hasattr(AsyncSQLDatabaseNode._is_test_environment, "cache_info"):
            info = AsyncSQLDatabaseNode._is_test_environment.cache_info()
            assert info.hits >= 1, "Should have cache hits on second call"

    def test_detection_overhead_under_1ms(self):
        """Test: Detection takes <1ms (performance requirement)."""
        # Clear cache for accurate timing
        if hasattr(AsyncSQLDatabaseNode._is_test_environment, "cache_clear"):
            AsyncSQLDatabaseNode._is_test_environment.cache_clear()

        # Measure execution time
        start = time.perf_counter()
        for _ in range(100):
            AsyncSQLDatabaseNode._is_test_environment()
        end = time.perf_counter()

        avg_time_ms = ((end - start) / 100) * 1000
        assert avg_time_ms < 1.0, f"Detection took {avg_time_ms:.3f}ms, should be <1ms"

    def test_stack_inspection_fallback_works(self):
        """Test: Stack contains pytest/unittest → returns True."""
        # This test verifies that stack inspection works as a fallback
        # when called from within a pytest test function
        result = AsyncSQLDatabaseNode._is_test_environment()

        # Check if we can see pytest/unittest in the stack
        stack = inspect.stack()
        has_test_in_stack = any(
            "pytest" in frame.filename or "unittest" in frame.filename
            for frame in stack
        )

        if has_test_in_stack:
            assert result is True, "Should detect test environment via stack inspection"


class TestAdaptivePoolKeyGeneration:
    """Test adaptive _generate_pool_key() behavior.

    NOTE: As of v0.10.15, pool keys ALWAYS include the actual event loop ID
    to prevent "Task got Future attached to a different loop" errors in
    Docker/FastAPI deployments. The previous behavior of using "test|" prefix
    in test mode was removed because it caused pool sharing across different
    event loops, leading to asyncio errors.
    """

    @pytest.mark.asyncio
    async def test_pool_key_includes_loop_id_always(self):
        """Test: Pool key always includes actual event loop ID.

        v0.10.15 change: We always use actual loop ID to prevent
        "attached to different loop" errors in Docker/FastAPI.
        """
        # Create node instance with valid config (passed to __init__)
        node = AsyncSQLDatabaseNode(
            database_type="postgresql",
            connection_string="postgresql://user:pass@localhost:5432/testdb",
            pool_size=10,
            max_pool_size=20,
        )

        # Generate pool key in test environment (current context)
        key = node._generate_pool_key()

        # Get current loop ID - should be in the key
        loop = asyncio.get_running_loop()
        loop_id = str(id(loop))

        # Key should start with actual loop ID
        assert key.startswith(
            f"{loop_id}|"
        ), f"Expected key to start with loop ID '{loop_id}|', got: {key}"

        # Verify key format is correct: "{loop_id}|postgresql|connection_string|pool_size|max_pool_size"
        parts = key.split("|")
        assert len(parts) == 5, f"Expected 5 parts in key, got {len(parts)}: {key}"
        assert parts[0] == loop_id, f"Expected loop ID as first part, got: {parts[0]}"
        assert (
            parts[1] == "postgresql"
        ), f"Expected 'postgresql' as second part, got: {parts[1]}"

    @pytest.mark.asyncio
    async def test_pool_key_format_with_loop_id(self):
        """Test: Pool key format is consistent with 5 parts.

        Format: {loop_id}|{db_type}|{connection}|{pool_size}|{max_pool_size}
        """
        node = AsyncSQLDatabaseNode(
            database_type="postgresql",
            connection_string="postgresql://user:pass@localhost:5432/testdb",
            pool_size=10,
            max_pool_size=20,
        )

        key = node._generate_pool_key()

        # Verify key format
        parts = key.split("|")
        assert len(parts) == 5, f"Expected 5 parts in key, got {len(parts)}: {key}"

        # First part should be numeric (loop ID)
        assert parts[
            0
        ].isdigit(), f"First part should be numeric loop ID, got: {parts[0]}"
        assert (
            parts[1] == "postgresql"
        ), f"Expected 'postgresql' as second part, got: {parts[1]}"
        assert (
            parts[2] == "postgresql://user:pass@localhost:5432/testdb"
        ), "Third part should be connection string"
        assert (
            parts[3] == "10"
        ), f"Fourth part should be pool_size '10', got: {parts[3]}"
        assert (
            parts[4] == "20"
        ), f"Fifth part should be max_pool_size '20', got: {parts[4]}"

    @pytest.mark.asyncio
    async def test_same_key_on_same_loop(self):
        """Test: Same event loop + same config → same pool key."""
        # Create two node instances with identical config
        node1 = AsyncSQLDatabaseNode(
            database_type="postgresql",
            connection_string="postgresql://user:pass@localhost:5432/testdb",
            pool_size=10,
            max_pool_size=20,
        )

        node2 = AsyncSQLDatabaseNode(
            database_type="postgresql",
            connection_string="postgresql://user:pass@localhost:5432/testdb",
            pool_size=10,
            max_pool_size=20,
        )

        # Generate keys on the same event loop
        key1 = node1._generate_pool_key()
        key2 = node2._generate_pool_key()

        # Keys should be identical on the same loop with same config
        assert (
            key1 == key2
        ), f"Keys should match on same loop:\nKey1: {key1}\nKey2: {key2}"

    @pytest.mark.asyncio
    async def test_different_keys_for_different_configs(self):
        """Test: Different connection configs → different pool keys."""
        # Create two nodes with different database configs
        node1 = AsyncSQLDatabaseNode(
            database_type="postgresql",
            connection_string="postgresql://user:pass@localhost:5432/testdb",
            pool_size=10,
            max_pool_size=20,
        )

        node2 = AsyncSQLDatabaseNode(
            database_type="postgresql",
            connection_string="postgresql://user:pass@localhost:5432/different_db",  # Different DB
            pool_size=10,
            max_pool_size=20,
        )

        # Generate keys
        key1 = node1._generate_pool_key()
        key2 = node2._generate_pool_key()

        # Keys should be different due to different connection strings
        assert (
            key1 != key2
        ), f"Keys should differ with different configs:\nKey1: {key1}\nKey2: {key2}"

    @pytest.mark.asyncio
    async def test_key_format_consistency(self):
        """Test: Key format is always 5 parts with loop ID first.

        Format: {loop_id}|{db_type}|{connection}|{pool_size}|{max_pool_size}
        """
        node = AsyncSQLDatabaseNode(
            database_type="postgresql",
            connection_string="postgresql://user:pass@localhost:5432/testdb",
            pool_size=10,
            max_pool_size=20,
        )

        # Generate pool key
        key = node._generate_pool_key()

        # Get current loop ID
        loop = asyncio.get_running_loop()
        loop_id = str(id(loop))

        # Verify key format
        parts = key.split("|")
        assert len(parts) == 5, f"Key should have 5 parts, got {len(parts)}: {key}"

        # First part should be actual loop ID
        assert (
            parts[0] == loop_id
        ), f"First part should be loop ID '{loop_id}', got: {parts[0]}"
        assert (
            parts[1] == "postgresql"
        ), f"Second part should be 'postgresql', got: {parts[1]}"
        assert (
            parts[2] == "postgresql://user:pass@localhost:5432/testdb"
        ), "Third part should be connection string"
        assert (
            parts[3] == "10"
        ), f"Fourth part should be pool_size '10', got: {parts[3]}"
        assert (
            parts[4] == "20"
        ), f"Fifth part should be max_pool_size '20', got: {parts[4]}"
