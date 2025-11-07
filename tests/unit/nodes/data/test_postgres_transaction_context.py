"""
Unit tests for PostgreSQLTransactionContext.

Tests the context manager pattern for guaranteed transaction cleanup.
Follows 3-Tier Testing Strategy - Tier 1 (Unit): Fast, isolated, can use mocks.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.nodes.data.async_sql import PostgreSQLTransactionContext


class TestPostgreSQLTransactionContext:
    """Test suite for PostgreSQLTransactionContext context manager."""

    @pytest.mark.asyncio
    async def test_successful_commit_with_cleanup(self):
        """Test successful transaction commit releases connection."""
        # Arrange
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_tx = AsyncMock()

        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_conn.transaction = MagicMock(return_value=mock_tx)
        mock_tx.start = AsyncMock()
        mock_tx.commit = AsyncMock()
        mock_pool.release = AsyncMock()

        # Act
        async with PostgreSQLTransactionContext(mock_pool) as ctx:
            # Verify connection is acquired
            assert ctx.connection == mock_conn
            await ctx.commit()

        # Assert
        mock_pool.acquire.assert_called_once()
        mock_conn.transaction.assert_called_once()
        mock_tx.start.assert_called_once()
        mock_tx.commit.assert_called_once()
        mock_pool.release.assert_called_once_with(mock_conn)

    @pytest.mark.asyncio
    async def test_automatic_rollback_on_exception(self):
        """Test automatic rollback when exception occurs in context."""
        # Arrange
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_tx = AsyncMock()

        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_conn.transaction = MagicMock(return_value=mock_tx)
        mock_tx.start = AsyncMock()
        mock_tx.rollback = AsyncMock()
        mock_pool.release = AsyncMock()

        # Act & Assert
        with pytest.raises(ValueError):
            async with PostgreSQLTransactionContext(mock_pool) as ctx:
                raise ValueError("Test error")

        # Assert rollback was called, not commit
        mock_tx.rollback.assert_called_once()
        mock_tx.commit.assert_not_called()
        mock_pool.release.assert_called_once_with(mock_conn)

    @pytest.mark.asyncio
    async def test_defensive_commit_when_no_action_taken(self):
        """Test defensive commit when neither commit nor exception occurs."""
        # Arrange
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_tx = AsyncMock()

        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_conn.transaction = MagicMock(return_value=mock_tx)
        mock_tx.start = AsyncMock()
        mock_tx.commit = AsyncMock()
        mock_pool.release = AsyncMock()

        # Act
        async with PostgreSQLTransactionContext(mock_pool) as ctx:
            # Do nothing - context manager should defensively commit
            pass

        # Assert
        mock_tx.commit.assert_called_once()
        mock_pool.release.assert_called_once_with(mock_conn)

    @pytest.mark.asyncio
    async def test_double_commit_raises_error(self):
        """Test that calling commit twice raises clear error."""
        # Arrange
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_tx = AsyncMock()

        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_conn.transaction = MagicMock(return_value=mock_tx)
        mock_tx.start = AsyncMock()
        mock_tx.commit = AsyncMock()
        mock_pool.release = AsyncMock()

        # Act & Assert
        with pytest.raises(RuntimeError, match="already committed"):
            async with PostgreSQLTransactionContext(mock_pool) as ctx:
                await ctx.commit()
                await ctx.commit()  # Should raise

    @pytest.mark.asyncio
    async def test_connection_released_even_on_cleanup_errors(self):
        """Test connection is released even if commit/rollback fails."""
        # Arrange
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_tx = AsyncMock()

        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_conn.transaction = MagicMock(return_value=mock_tx)
        mock_tx.start = AsyncMock()
        mock_tx.commit = AsyncMock(side_effect=Exception("Commit failed"))
        mock_pool.release = AsyncMock()

        # Act & Assert
        with pytest.raises(Exception, match="Commit failed"):
            async with PostgreSQLTransactionContext(mock_pool) as ctx:
                pass  # Defensive commit should fail

        # Assert connection is still released
        mock_pool.release.assert_called_once_with(mock_conn)

    @pytest.mark.asyncio
    async def test_explicit_rollback(self):
        """Test explicit rollback method."""
        # Arrange
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_tx = AsyncMock()

        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_conn.transaction = MagicMock(return_value=mock_tx)
        mock_tx.start = AsyncMock()
        mock_tx.rollback = AsyncMock()
        mock_pool.release = AsyncMock()

        # Act
        async with PostgreSQLTransactionContext(mock_pool) as ctx:
            await ctx.rollback()

        # Assert
        mock_tx.rollback.assert_called_once()
        mock_tx.commit.assert_not_called()  # Should not commit after rollback
        mock_pool.release.assert_called_once_with(mock_conn)

    @pytest.mark.asyncio
    async def test_connection_property_exposes_underlying_connection(self):
        """Test that connection property exposes the underlying connection."""
        # Arrange
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_tx = AsyncMock()

        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_conn.transaction = MagicMock(return_value=mock_tx)
        mock_tx.start = AsyncMock()
        mock_tx.commit = AsyncMock()
        mock_pool.release = AsyncMock()

        # Act
        async with PostgreSQLTransactionContext(mock_pool) as ctx:
            # Assert
            assert ctx.connection is mock_conn
            assert ctx.connection is not None

    @pytest.mark.asyncio
    async def test_rollback_after_commit_raises_error(self):
        """Test that calling rollback after commit raises error."""
        # Arrange
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_tx = AsyncMock()

        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_conn.transaction = MagicMock(return_value=mock_tx)
        mock_tx.start = AsyncMock()
        mock_tx.commit = AsyncMock()
        mock_pool.release = AsyncMock()

        # Act & Assert
        with pytest.raises(RuntimeError, match="already committed"):
            async with PostgreSQLTransactionContext(mock_pool) as ctx:
                await ctx.commit()
                await ctx.rollback()  # Should raise
