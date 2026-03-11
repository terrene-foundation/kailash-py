"""
Unit Tests for DataFlow TDD Infrastructure

This module tests the core TDD support infrastructure including:
- Test context manager and isolation
- Transaction-based test isolation using PostgreSQL savepoints
- Performance optimization for test execution
- Feature flag integration
"""

import asyncio
import os
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

# Test the TDD infrastructure we're about to build
from dataflow.testing.tdd_support import (
    TDDDatabaseManager,
    TDDTestContext,
    TDDTransactionManager,
    get_test_context,
    is_tdd_mode,
)


class TestTDDModeDetection:
    """Test TDD mode detection and feature flag functionality."""

    def test_tdd_mode_detection_enabled(self):
        """Test detection when DATAFLOW_TDD_MODE is enabled."""
        with patch.dict(os.environ, {"DATAFLOW_TDD_MODE": "true"}):
            assert is_tdd_mode() is True

    def test_tdd_mode_detection_disabled(self):
        """Test detection when DATAFLOW_TDD_MODE is disabled."""
        with patch.dict(os.environ, {"DATAFLOW_TDD_MODE": "false"}, clear=True):
            assert is_tdd_mode() is False

    def test_tdd_mode_detection_not_set(self):
        """Test detection when DATAFLOW_TDD_MODE is not set."""
        with patch.dict(os.environ, {}, clear=True):
            assert is_tdd_mode() is False

    def test_tdd_mode_detection_case_insensitive(self):
        """Test that TDD mode detection is case insensitive."""
        test_cases = ["TRUE", "True", "YES", "1", "on"]
        for value in test_cases:
            with patch.dict(os.environ, {"DATAFLOW_TDD_MODE": value}):
                assert is_tdd_mode() is True, f"Failed for value: {value}"


class TestTDDTestContext:
    """Test TDD test context management."""

    def test_test_context_initialization(self):
        """Test that test context initializes with correct default values."""
        context = TDDTestContext()

        assert context.test_id is not None
        assert context.isolation_level == "READ COMMITTED"
        assert context.timeout == 30
        assert context.savepoint_name is not None
        assert context.rollback_on_error is True
        assert context.connection is None
        assert context.savepoint_created is False

    def test_test_context_custom_values(self):
        """Test test context initialization with custom values."""
        context = TDDTestContext(
            test_id="custom_test",
            isolation_level="SERIALIZABLE",
            timeout=60,
            savepoint_name="custom_savepoint",
            rollback_on_error=False,
        )

        assert context.test_id == "custom_test"
        assert context.isolation_level == "SERIALIZABLE"
        assert context.timeout == 60
        assert context.savepoint_name == "sp_custom_savepoint"
        assert context.rollback_on_error is False

    def test_test_context_auto_generated_names(self):
        """Test that test context auto-generates unique names."""
        context1 = TDDTestContext()
        context2 = TDDTestContext()

        assert context1.test_id != context2.test_id
        assert context1.savepoint_name != context2.savepoint_name

    def test_test_context_metadata_storage(self):
        """Test that test context can store custom metadata."""
        context = TDDTestContext()
        context.metadata = {"test_case": "user_registration", "database": "postgres"}

        assert context.metadata["test_case"] == "user_registration"
        assert context.metadata["database"] == "postgres"


class TestTDDDatabaseManager:
    """Test TDD database connection management."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock database connection."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetch = AsyncMock()
        mock_conn.close = AsyncMock()
        return mock_conn

    @pytest.fixture
    def db_manager(self):
        """Create a TDD database manager instance."""
        return TDDDatabaseManager()

    def test_database_manager_initialization(self, db_manager):
        """Test database manager initializes correctly."""
        assert db_manager.connection_pool is None
        assert db_manager.active_connections == {}
        assert db_manager.test_isolation_enabled is True

    @pytest.mark.asyncio
    async def test_get_test_connection_creates_new(self, db_manager, mock_connection):
        """Test that get_test_connection creates a new connection for tests."""
        with patch("asyncpg.connect", return_value=mock_connection):
            context = TDDTestContext(test_id="test_123")

            conn = await db_manager.get_test_connection(context)

            assert conn == mock_connection
            assert db_manager.active_connections["test_123"] == mock_connection

    @pytest.mark.asyncio
    async def test_get_test_connection_reuses_existing(
        self, db_manager, mock_connection
    ):
        """Test that get_test_connection reuses existing connection."""
        context = TDDTestContext(test_id="test_123")
        db_manager.active_connections["test_123"] = mock_connection

        conn = await db_manager.get_test_connection(context)

        assert conn == mock_connection

    @pytest.mark.asyncio
    async def test_cleanup_test_connection(self, db_manager, mock_connection):
        """Test that test connections are properly cleaned up."""
        context = TDDTestContext(test_id="test_123")
        db_manager.active_connections["test_123"] = mock_connection

        await db_manager.cleanup_test_connection(context)

        mock_connection.close.assert_called_once()
        assert "test_123" not in db_manager.active_connections

    @pytest.mark.asyncio
    async def test_cleanup_all_test_connections(self, db_manager):
        """Test that all test connections are cleaned up."""
        mock_conn1 = AsyncMock()
        mock_conn2 = AsyncMock()

        db_manager.active_connections = {"test_1": mock_conn1, "test_2": mock_conn2}

        await db_manager.cleanup_all_test_connections()

        mock_conn1.close.assert_called_once()
        mock_conn2.close.assert_called_once()
        assert len(db_manager.active_connections) == 0


class TestTDDTransactionManager:
    """Test TDD transaction and savepoint management."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock database connection with transaction support."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetch = AsyncMock()
        mock_conn.transaction = MagicMock()
        return mock_conn

    @pytest.fixture
    def transaction_manager(self):
        """Create a TDD transaction manager instance."""
        return TDDTransactionManager()

    @pytest.mark.asyncio
    async def test_create_savepoint(self, transaction_manager, mock_connection):
        """Test creating a savepoint for test isolation."""
        context = TDDTestContext(savepoint_name="sp_test_123")

        await transaction_manager.create_savepoint(mock_connection, context)

        mock_connection.execute.assert_called_with("SAVEPOINT sp_test_123")
        assert context.savepoint_created is True

    @pytest.mark.asyncio
    async def test_rollback_to_savepoint(self, transaction_manager, mock_connection):
        """Test rolling back to a savepoint."""
        context = TDDTestContext(savepoint_name="sp_test_123", savepoint_created=True)

        await transaction_manager.rollback_to_savepoint(mock_connection, context)

        mock_connection.execute.assert_called_with("ROLLBACK TO SAVEPOINT sp_test_123")

    @pytest.mark.asyncio
    async def test_rollback_to_savepoint_not_created(
        self, transaction_manager, mock_connection
    ):
        """Test rollback when savepoint was not created."""
        context = TDDTestContext(savepoint_name="sp_test_123", savepoint_created=False)

        # Should not execute rollback if savepoint was not created
        await transaction_manager.rollback_to_savepoint(mock_connection, context)

        mock_connection.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_savepoint(self, transaction_manager, mock_connection):
        """Test releasing a savepoint."""
        context = TDDTestContext(savepoint_name="sp_test_123", savepoint_created=True)

        await transaction_manager.release_savepoint(mock_connection, context)

        mock_connection.execute.assert_called_with("RELEASE SAVEPOINT sp_test_123")
        assert context.savepoint_created is False

    @pytest.mark.asyncio
    async def test_begin_test_transaction(self, transaction_manager, mock_connection):
        """Test beginning a test transaction with proper isolation."""
        context = TDDTestContext(isolation_level="SERIALIZABLE")

        await transaction_manager.begin_test_transaction(mock_connection, context)

        # Should begin transaction with isolation level and create savepoint
        mock_connection.execute.assert_any_call("BEGIN")
        mock_connection.execute.assert_any_call(
            "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
        )
        mock_connection.execute.assert_any_call(f"SAVEPOINT {context.savepoint_name}")

    @pytest.mark.asyncio
    async def test_end_test_transaction_rollback(
        self, transaction_manager, mock_connection
    ):
        """Test ending test transaction with rollback."""
        context = TDDTestContext(
            savepoint_name="sp_test_123", savepoint_created=True, rollback_on_error=True
        )

        await transaction_manager.end_test_transaction(
            mock_connection, context, rollback=True
        )

        mock_connection.execute.assert_called_with("ROLLBACK TO SAVEPOINT sp_test_123")

    @pytest.mark.asyncio
    async def test_end_test_transaction_commit(
        self, transaction_manager, mock_connection
    ):
        """Test ending test transaction with commit (release savepoint)."""
        context = TDDTestContext(
            savepoint_name="sp_test_123",
            savepoint_created=True,
            rollback_on_error=False,
        )

        await transaction_manager.end_test_transaction(
            mock_connection, context, rollback=False
        )

        mock_connection.execute.assert_called_with("RELEASE SAVEPOINT sp_test_123")


class TestTDDContextManager:
    """Test the global TDD context management."""

    def test_get_test_context_none_by_default(self):
        """Test that get_test_context returns None when not set."""
        # Ensure no context is set
        with patch("dataflow.testing.tdd_support._current_test_context", None):
            assert get_test_context() is None

    def test_get_test_context_returns_current(self):
        """Test that get_test_context returns the current context."""
        mock_context = TDDTestContext(test_id="test_current")

        with patch("dataflow.testing.tdd_support._current_test_context", mock_context):
            assert get_test_context() == mock_context

    def test_context_isolation_between_tests(self):
        """Test that test contexts are properly isolated."""
        # This would be tested in integration tests where multiple
        # test contexts are created and managed simultaneously
        context1 = TDDTestContext(test_id="test_1")
        context2 = TDDTestContext(test_id="test_2")

        assert context1.test_id != context2.test_id
        assert context1.savepoint_name != context2.savepoint_name


class TestTDDPerformanceOptimizations:
    """Test performance optimizations in TDD infrastructure."""

    def test_connection_reuse_strategy(self):
        """Test that connection reuse strategy is properly implemented."""
        db_manager = TDDDatabaseManager()

        # Mock multiple contexts using same connection
        context1 = TDDTestContext(test_id="test_1")
        context2 = TDDTestContext(test_id="test_2")

        mock_conn = AsyncMock()
        db_manager.active_connections["test_1"] = mock_conn

        # Should create new connection for different test
        assert db_manager.active_connections.get("test_2") is None
        assert db_manager.active_connections.get("test_1") == mock_conn

    def test_savepoint_naming_efficiency(self):
        """Test that savepoint naming is efficient and unique."""
        context1 = TDDTestContext()
        context2 = TDDTestContext()

        # Savepoint names should be short but unique
        assert len(context1.savepoint_name) < 20  # Keep names short for performance
        assert context1.savepoint_name != context2.savepoint_name
        assert context1.savepoint_name.startswith("sp_")

    def test_timeout_configuration(self):
        """Test that timeout configuration works correctly."""
        context = TDDTestContext(timeout=10)
        assert context.timeout == 10

        # Default should be reasonable for fast tests
        default_context = TDDTestContext()
        assert default_context.timeout <= 30  # Should be <= 30 seconds for fast tests


class TestTDDErrorHandling:
    """Test error handling in TDD infrastructure."""

    @pytest.mark.asyncio
    async def test_connection_failure_handling(self):
        """Test handling of connection failures."""
        db_manager = TDDDatabaseManager()
        context = TDDTestContext(test_id="test_fail")

        with patch("asyncpg.connect", side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="Connection failed"):
                await db_manager.get_test_connection(context)

    @pytest.mark.asyncio
    async def test_savepoint_creation_failure(self):
        """Test handling of savepoint creation failures."""
        transaction_manager = TDDTransactionManager()
        mock_connection = AsyncMock()
        mock_connection.execute.side_effect = Exception("Savepoint failed")

        context = TDDTestContext(savepoint_name="sp_fail")

        with pytest.raises(Exception, match="Savepoint failed"):
            await transaction_manager.create_savepoint(mock_connection, context)

        # Context should reflect failure
        assert context.savepoint_created is False

    @pytest.mark.asyncio
    async def test_cleanup_with_connection_errors(self):
        """Test cleanup handles connection errors gracefully."""
        db_manager = TDDDatabaseManager()
        mock_connection = AsyncMock()
        mock_connection.close.side_effect = Exception("Close failed")

        context = TDDTestContext(test_id="test_cleanup_fail")
        db_manager.active_connections["test_cleanup_fail"] = mock_connection

        # Should handle cleanup errors gracefully
        await db_manager.cleanup_test_connection(context)

        # Connection should still be removed from active connections
        assert "test_cleanup_fail" not in db_manager.active_connections


class TestTDDIntegrationPoints:
    """Test integration points with existing DataFlow infrastructure."""

    def test_feature_flag_integration(self):
        """Test integration with DataFlow feature flag system."""
        # This tests the integration with progressive_disclosure.py
        # which we'll implement next
        with patch.dict(os.environ, {"DATAFLOW_TDD_MODE": "true"}):
            assert is_tdd_mode() is True

        with patch.dict(os.environ, {}, clear=True):
            assert is_tdd_mode() is False

    def test_engine_integration_readiness(self):
        """Test that TDD infrastructure is ready for engine integration."""
        # Test that we can create contexts that engine.py can use
        context = TDDTestContext()

        # Should have all attributes needed for engine integration
        assert hasattr(context, "test_id")
        assert hasattr(context, "connection")
        assert hasattr(context, "savepoint_name")
        assert hasattr(context, "savepoint_created")

    def test_conftest_fixture_compatibility(self):
        """Test compatibility with pytest fixtures we'll add to conftest.py."""
        # Test that TDD contexts can be created in fixture-like scenarios
        context = TDDTestContext(test_id="pytest_fixture_test")

        assert context.test_id == "pytest_fixture_test"
        assert context.isolation_level == "READ COMMITTED"  # Good default for tests
        assert context.timeout <= 30  # Fast enough for unit tests
