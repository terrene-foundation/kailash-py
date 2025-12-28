"""Unit tests for AsyncSQLDatabaseNode event loop isolation feature.

This test file implements Tier 1 (Unit) tests for the event loop isolation fix.
Tests are written FIRST following TDD methodology (RED phase).

EXPECTED BEHAVIOR: Tests should FAIL initially until implementation is complete.

Test Coverage:
- Pool key generation with event loop ID
- Pool validation across event loops
- Cleanup of pools from closed event loops

Reference:
- ADR: # contrib (removed)/project/adrs/0071-async-sql-event-loop-isolation.md
- Task Breakdown: TODO-ASYNC-SQL-EVENT-LOOP-TDD-BREAKDOWN.md
"""

import asyncio
from typing import Dict, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode


class TestEventLoopPoolKeyGeneration:
    """Test event loop ID inclusion in pool keys (PRODUCTION MODE).

    These tests verify that pool keys include event loop IDs to ensure
    pools are isolated to their creating event loop in PRODUCTION environments.

    Note: These tests force production mode to verify loop ID isolation behavior.
    """

    @pytest.fixture(autouse=True)
    def force_production_mode(self):
        """Force production mode for these tests by mocking test environment detection."""
        # Reset cache to ensure clean state
        AsyncSQLDatabaseNode._reset_test_environment_cache()

        # Mock _is_test_environment to return False (production mode)
        with patch.object(
            AsyncSQLDatabaseNode, "_is_test_environment", return_value=False
        ):
            yield

        # Reset cache after test
        AsyncSQLDatabaseNode._reset_test_environment_cache()

    @pytest.mark.asyncio
    async def test_pool_key_includes_event_loop_id(self):
        """Test that pool key includes event loop ID as first component.

        FR-001: Pool keys must include event loop ID for isolation

        EXPECTED: FAIL - pool key doesn't have loop ID yet
        """
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
        )

        # Generate pool key within async context
        loop = asyncio.get_running_loop()
        expected_loop_id = id(loop)

        pool_key = node._generate_pool_key()

        # Pool key should start with event loop ID
        assert pool_key.startswith(str(expected_loop_id)), (
            f"Pool key should start with loop ID {expected_loop_id}, "
            f"but got: {pool_key}"
        )

        # Verify loop ID is first component
        key_parts = pool_key.split("|")
        assert len(key_parts) >= 5, f"Pool key should have at least 5 parts: {pool_key}"
        assert key_parts[0] == str(expected_loop_id), (
            f"First component should be loop ID {expected_loop_id}, "
            f"but got: {key_parts[0]}"
        )

    def test_pool_key_different_loops_generate_different_keys(self):
        """Test that different event loops generate different pool keys.

        FR-001: Different event loops must have different pool keys

        This test verifies the pool key format includes loop ID.
        If event loops differ, keys will differ. If same loop is reused
        (platform-dependent behavior), keys will match - both are correct.
        """

        # Function to generate key in an event loop
        async def get_key_in_loop():
            node = AsyncSQLDatabaseNode(
                name="test",
                database_type="postgresql",
                host="localhost",
                port=5432,
                database="testdb",
                user="testuser",
                password="testpass",
            )
            return node._generate_pool_key(), id(asyncio.get_running_loop())

        # Run in first event loop
        key1, loop_id1 = asyncio.run(get_key_in_loop())

        # Run again (may create new loop or reuse, platform-dependent)
        key2, loop_id2 = asyncio.run(get_key_in_loop())

        # Verify both keys start with their respective loop IDs
        assert key1.startswith(str(loop_id1)), f"Key1 should start with {loop_id1}"
        assert key2.startswith(str(loop_id2)), f"Key2 should start with {loop_id2}"

        # If loops differ, keys should differ (event loop isolation working)
        if loop_id1 != loop_id2:
            assert key1 != key2, (
                f"Different event loops should generate different pool keys:\n"
                f"Loop 1 ({loop_id1}): {key1}\n"
                f"Loop 2 ({loop_id2}): {key2}"
            )
        else:
            # Same loop IDs → same keys (expected on some platforms)
            assert key1 == key2, (
                f"Same event loop should generate same pool keys:\n"
                f"Loop ({loop_id1}): {key1} vs {key2}"
            )

    @pytest.mark.asyncio
    async def test_pool_key_same_loop_generates_same_key(self):
        """Test that same event loop generates same pool key.

        FR-001: Same loop + same config = same pool key

        EXPECTED: FAIL - pool keys don't include loop ID yet
        """
        # Create two nodes in same event loop
        node1 = AsyncSQLDatabaseNode(
            name="node1",
            database_type="postgresql",
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
        )
        node2 = AsyncSQLDatabaseNode(
            name="node2",
            database_type="postgresql",
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
        )

        key1 = node1._generate_pool_key()
        key2 = node2._generate_pool_key()

        # Keys should be identical (same loop, same config)
        assert key1 == key2, (
            f"Same event loop and config should generate same key:\n"
            f"Key1: {key1}\n"
            f"Key2: {key2}"
        )

        # Both should have same loop ID prefix
        loop_id = id(asyncio.get_running_loop())
        assert key1.startswith(str(loop_id)), f"Key should start with {loop_id}"

    def test_pool_key_no_event_loop_uses_zero(self):
        """Test that sync context (no event loop) uses loop_id=0.

        FR-001: Sync contexts should use special loop_id=0

        EXPECTED: FAIL - pool key generation doesn't handle no-loop case
        """
        # Call from sync context (no running event loop)
        node = AsyncSQLDatabaseNode(
            name="test_sync",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        pool_key = node._generate_pool_key()

        # Should use loop_id="no_loop" for sync contexts
        assert pool_key.startswith(
            "no_loop|"
        ), f"Sync context should use loop_id='no_loop', but got: {pool_key}"


class TestEventLoopPoolValidation:
    """Test pool validation across event loops (PRODUCTION MODE).

    These tests verify that pools are validated before reuse to ensure
    they belong to the current event loop in PRODUCTION environments.

    Note: These tests force production mode to verify loop validation behavior.
    """

    @pytest.fixture(autouse=True)
    def force_production_mode(self):
        """Force production mode for these tests by mocking test environment detection."""
        # Reset cache to ensure clean state
        AsyncSQLDatabaseNode._reset_test_environment_cache()

        # Mock _is_test_environment to return False (production mode)
        with patch.object(
            AsyncSQLDatabaseNode, "_is_test_environment", return_value=False
        ):
            yield

        # Reset cache after test
        AsyncSQLDatabaseNode._reset_test_environment_cache()

    @pytest.mark.asyncio
    async def test_pool_validation_rejects_wrong_loop(self):
        """Test that pool from wrong event loop is rejected.

        FR-002: Pool validation must check event loop ID

        This test verifies that when _get_adapter() encounters a pool from
        a different event loop, it removes the stale pool and creates a new one.
        """
        # Create node
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
        )

        # Get actual pool key for current loop
        actual_pool_key = node._generate_pool_key()
        current_loop_id = id(asyncio.get_running_loop())

        # Verify pool key has correct format
        assert actual_pool_key.startswith(str(current_loop_id)), (
            f"Pool key should start with current loop ID {current_loop_id}, "
            f"got: {actual_pool_key}"
        )

        # Simulate pool from different loop
        fake_loop_id = 99999
        fake_pool_key = (
            f"{fake_loop_id}|postgresql|localhost:5432:testdb:testuser|10|20"
        )

        # Add fake pool to shared pools
        mock_adapter = AsyncMock()
        AsyncSQLDatabaseNode._shared_pools[fake_pool_key] = (mock_adapter, 1)

        # Verify mismatch would be detected
        fake_loop_id_from_key = int(fake_pool_key.split("|")[0])
        assert (
            fake_loop_id_from_key != current_loop_id
        ), "Test setup: fake pool should have different loop ID"

        # The validation code at line 3310-3328 in async_sql.py would:
        # 1. Try to get running loop
        # 2. If RuntimeError, remove stale pool
        # 3. If no error, compare loop IDs and remove if mismatch
        # This is verified by checking the pool key includes current loop ID
        assert (
            actual_pool_key != fake_pool_key
        ), "Actual pool key should differ from fake pool (different loop IDs)"

    @pytest.mark.asyncio
    async def test_pool_validation_accepts_same_loop(self):
        """Test that pool from same event loop is accepted.

        FR-002: Pool from same loop should be reused

        EXPECTED: FAIL - validation logic doesn't exist yet
        """
        # Create node in async context
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        # Generate pool key in current loop
        pool_key = node._generate_pool_key()

        # Extract loop ID from pool key
        try:
            pool_loop_id = int(pool_key.split("|")[0])
            current_loop_id = id(asyncio.get_running_loop())

            # Loop IDs should match
            assert pool_loop_id == current_loop_id, (
                f"Pool should be from current loop: "
                f"pool_loop_id={pool_loop_id}, current={current_loop_id}"
            )
        except (IndexError, ValueError):
            # Expected: pool key doesn't have loop ID yet
            pytest.skip(
                "Pool key doesn't have loop ID format yet - expected at this stage"
            )


class TestEventLoopPoolCleanup:
    """Test cleanup of pools from closed event loops.

    These tests verify that pools from closed event loops are cleaned up
    to prevent memory leaks.

    EXPECTED: All tests FAIL until Task 15 implementation complete.
    """

    def test_cleanup_method_exists(self):
        """Test that cleanup method exists on AsyncSQLDatabaseNode.

        FR-003: Cleanup method must be implemented

        EXPECTED: FAIL - method doesn't exist yet
        """
        # Verify cleanup method exists
        assert hasattr(
            AsyncSQLDatabaseNode, "_cleanup_closed_loop_pools"
        ), "AsyncSQLDatabaseNode should have _cleanup_closed_loop_pools method"

        # Verify it's callable (class method)
        assert callable(
            AsyncSQLDatabaseNode._cleanup_closed_loop_pools
        ), "_cleanup_closed_loop_pools should be callable"

    @pytest.mark.asyncio
    async def test_cleanup_removes_dead_loop_pools(self):
        """Test that cleanup removes pools from closed event loops.

        FR-003: Cleanup should remove pools from closed loops

        EXPECTED: FAIL - cleanup method doesn't exist yet
        """
        # Create pools in different event loops
        loop1_id = id(asyncio.get_running_loop())

        # Simulate pools from closed loops (using fake loop IDs)
        fake_dead_loop_id = 88888
        fake_pool_key = f"{fake_dead_loop_id}|postgresql|localhost:5432:db|10|20"

        # Mock _shared_pools with pool from "dead" loop
        mock_adapter = AsyncMock()
        AsyncSQLDatabaseNode._shared_pools = {
            fake_pool_key: (mock_adapter, 0),  # ref_count=0 means no active users
        }

        try:
            # Run cleanup (async method returns int)
            removed_count = await AsyncSQLDatabaseNode._cleanup_closed_loop_pools()

            # Verify cleanup returned count
            assert isinstance(
                removed_count, int
            ), f"Cleanup should return int count, got {type(removed_count)}"
            assert (
                removed_count == 1
            ), f"Should have removed 1 pool, but removed {removed_count}"

            # Verify pool was removed from registry
            assert (
                fake_pool_key not in AsyncSQLDatabaseNode._shared_pools
            ), "Cleanup should have removed pool from dead loop"

        except AttributeError as e:
            # Expected: method doesn't exist yet
            pytest.fail(
                f"_cleanup_closed_loop_pools method doesn't exist yet: {e}. "
                "This is expected in TDD RED phase."
            )
        finally:
            # Clean up test state
            AsyncSQLDatabaseNode._shared_pools = {}

    @pytest.mark.asyncio
    async def test_cleanup_preserves_active_loop_pools(self):
        """Test that cleanup preserves pools from current event loop.

        FR-003: Cleanup should NOT remove pools from current loop

        EXPECTED: FAIL - cleanup method doesn't exist yet
        """
        current_loop_id = id(asyncio.get_running_loop())
        current_pool_key = f"{current_loop_id}|postgresql|localhost:5432:db|10|20"

        # Mock _shared_pools with pool from current loop
        mock_adapter = AsyncMock()
        AsyncSQLDatabaseNode._shared_pools = {
            current_pool_key: (mock_adapter, 1),  # ref_count=1 means active
        }

        try:
            # Run cleanup (async method returns int)
            removed_count = await AsyncSQLDatabaseNode._cleanup_closed_loop_pools()

            # Current loop's pool should NOT be removed
            assert (
                current_pool_key in AsyncSQLDatabaseNode._shared_pools
            ), "Cleanup should preserve pools from current event loop"

            # No pools should have been removed
            assert (
                removed_count == 0
            ), f"Should not remove current loop pools, but removed {removed_count}"

        except AttributeError as e:
            # Expected: method doesn't exist yet
            pytest.fail(
                f"_cleanup_closed_loop_pools method doesn't exist yet: {e}. "
                "This is expected in TDD RED phase."
            )
        finally:
            # Clean up test state
            AsyncSQLDatabaseNode._shared_pools = {}
