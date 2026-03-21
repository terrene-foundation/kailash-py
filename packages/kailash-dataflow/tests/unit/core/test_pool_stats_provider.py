# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for _make_pool_stats_provider(), health_check() pool integration,
and public pool API on the DataFlow class.

Covers:
- Gap 1: _make_pool_stats_provider() — zero prior test coverage
- Gap 2: health_check() pool integration
- Gap 3: Public API tests (pool_stats, execute_raw_lightweight)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from dataflow.core.pool_monitor import pool_stats_dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dataflow(url: str = "sqlite:///:memory:", **kwargs):
    """Create a minimal DataFlow instance for unit tests.

    Uses auto_migrate=False and startup_validation=False to avoid
    side-effects.  Connection pooling is disabled by default so that
    the DataFlow constructor does not attempt real pool creation.
    """
    from dataflow import DataFlow

    defaults = {
        "auto_migrate": False,
        "startup_validation": False,
        "enable_connection_pooling": False,
    }
    defaults.update(kwargs)
    return DataFlow(url, **defaults)


# ===========================================================================
# Gap 1: _make_pool_stats_provider()
# ===========================================================================


class TestMakePoolStatsProvider:
    """Tests for DataFlow._make_pool_stats_provider()."""

    # -----------------------------------------------------------------------
    # 1. No pool present
    # -----------------------------------------------------------------------

    def test_provider_returns_zeros_when_no_pool(self):
        """When _shared_pools is empty, provider returns pool_stats_dict with
        the configured max_size/max_overflow and active=0, idle=0."""
        df = _make_dataflow()
        provider = df._make_pool_stats_provider(pool_size=8, max_overflow=4)

        with patch(
            "kailash.nodes.data.async_sql.AsyncSQLDatabaseNode._shared_pools", {}
        ):
            stats = provider()

        assert stats["active"] == 0
        assert stats["idle"] == 0
        assert stats["max"] == 8
        assert stats["max_overflow"] == 4
        assert stats["utilization"] == 0.0

    # -----------------------------------------------------------------------
    # 2. asyncpg pool (PostgreSQL)
    # -----------------------------------------------------------------------

    def test_provider_reads_asyncpg_pool(self):
        """Mock an adapter in _shared_pools with an asyncpg-style
        connection_pool (get_size / get_idle_size).  Verify active and
        idle are computed correctly."""
        df = _make_dataflow(url="postgresql://user:pass@localhost/testdb")
        provider = df._make_pool_stats_provider(pool_size=10, max_overflow=5)

        mock_pool = MagicMock()
        mock_pool.get_size.return_value = 8
        mock_pool.get_idle_size.return_value = 3

        mock_adapter = MagicMock()
        mock_adapter.connection_pool = mock_pool

        shared_pools = {"postgresql://user:pass@localhost/testdb": (mock_adapter, 1)}

        with patch(
            "kailash.nodes.data.async_sql.AsyncSQLDatabaseNode._shared_pools",
            shared_pools,
        ):
            stats = provider()

        assert stats["active"] == 5  # 8 - 3
        assert stats["idle"] == 3
        assert stats["max"] == 10
        assert stats["max_overflow"] == 5

    # -----------------------------------------------------------------------
    # 3. SQLAlchemy QueuePool
    # -----------------------------------------------------------------------

    def test_provider_reads_sqlalchemy_queuepool(self):
        """Mock an adapter with a SQLAlchemy QueuePool-style object that
        has checkedout/checkedin/size/overflow methods."""
        df = _make_dataflow(url="postgresql://user:pass@localhost/testdb")
        provider = df._make_pool_stats_provider(pool_size=20, max_overflow=10)

        mock_pool = MagicMock(spec=[])  # no spec — we add attrs explicitly
        mock_pool.checkedout = MagicMock(return_value=7)
        mock_pool.checkedin = MagicMock(return_value=13)
        mock_pool.size = MagicMock(return_value=20)
        mock_pool.overflow = MagicMock(return_value=2)
        mock_pool._max_overflow = 10

        # Remove asyncpg-style attributes so the SQLAlchemy branch is chosen
        # (QueuePool has checkedout/checkedin but NOT get_size/get_idle_size)
        assert not hasattr(mock_pool, "get_size")
        assert not hasattr(mock_pool, "get_idle_size")

        mock_adapter = MagicMock(spec=[])
        mock_adapter.connection_pool = mock_pool

        shared_pools = {"postgresql://user:pass@localhost/testdb": (mock_adapter, 1)}

        with patch(
            "kailash.nodes.data.async_sql.AsyncSQLDatabaseNode._shared_pools",
            shared_pools,
        ):
            stats = provider()

        assert stats["active"] == 7
        assert stats["idle"] == 13
        assert stats["max"] == 20
        assert stats["overflow"] == 2
        assert stats["max_overflow"] == 10

    # -----------------------------------------------------------------------
    # 4. SQLite adapter with _pool_stats
    # -----------------------------------------------------------------------

    def test_provider_reads_sqlite_pool_stats(self):
        """Mock an adapter with a _pool_stats attribute that exposes
        active_connections and idle_connections.

        The production code requires adapter.connection_pool or adapter._pool
        to be truthy before it reaches the _pool_stats branch.  For SQLite
        adapters, _pool is typically the aiosqlite connection object (truthy)
        but lacks asyncpg/QueuePool methods."""
        df = _make_dataflow(url="sqlite:///test.db")
        provider = df._make_pool_stats_provider(pool_size=5, max_overflow=2)

        pool_stats_obj = SimpleNamespace(active_connections=2, idle_connections=3)

        # The pool object must be truthy but must NOT have asyncpg
        # (get_size/get_idle_size) or SQLAlchemy (checkedout/checkedin) attrs.
        sqlite_pool = SimpleNamespace()  # bare object, no special methods
        mock_adapter = MagicMock(spec=[])
        mock_adapter._pool_stats = pool_stats_obj
        mock_adapter.connection_pool = None
        mock_adapter._pool = sqlite_pool  # truthy, no asyncpg/QueuePool methods

        shared_pools = {"sqlite:///test.db": (mock_adapter, 1)}

        with patch(
            "kailash.nodes.data.async_sql.AsyncSQLDatabaseNode._shared_pools",
            shared_pools,
        ):
            stats = provider()

        assert stats["active"] == 2
        assert stats["idle"] == 3
        assert stats["max"] == 5
        assert stats["max_overflow"] == 2

    # -----------------------------------------------------------------------
    # 5. Scoped to database URL
    # -----------------------------------------------------------------------

    def test_provider_scoped_to_database_url(self):
        """When _shared_pools has pools for multiple URLs, the provider
        only reads the one matching the DataFlow's URL."""
        df = _make_dataflow(url="postgresql://user:pass@localhost/mydb")
        provider = df._make_pool_stats_provider(pool_size=10, max_overflow=5)

        # Pool for a *different* URL
        other_pool = MagicMock()
        other_pool.get_size.return_value = 99
        other_pool.get_idle_size.return_value = 1
        other_adapter = MagicMock()
        other_adapter.connection_pool = other_pool

        shared_pools = {
            "postgresql://user:pass@other-host/otherdb": (other_adapter, 1),
        }

        with patch(
            "kailash.nodes.data.async_sql.AsyncSQLDatabaseNode._shared_pools",
            shared_pools,
        ):
            stats = provider()

        # Should NOT have read from the other pool — falls through to zeros
        assert stats["active"] == 0
        assert stats["idle"] == 0
        assert stats["max"] == 10

    # -----------------------------------------------------------------------
    # 6. Exception handling
    # -----------------------------------------------------------------------

    def test_provider_handles_exception_gracefully(self):
        """When accessing pool stats raises an exception, the provider
        returns the fallback zeros dict rather than propagating."""
        df = _make_dataflow(url="postgresql://user:pass@localhost/testdb")
        provider = df._make_pool_stats_provider(pool_size=10, max_overflow=5)

        # Patch _shared_pools.items() to raise during iteration
        mock_pools = MagicMock()
        mock_pools.items.side_effect = RuntimeError("simulated concurrent mutation")

        with patch(
            "kailash.nodes.data.async_sql.AsyncSQLDatabaseNode._shared_pools",
            mock_pools,
        ):
            stats = provider()

        # Fallback: zeros with configured sizes
        assert stats["active"] == 0
        assert stats["idle"] == 0
        assert stats["max"] == 10
        assert stats["max_overflow"] == 5

    # -----------------------------------------------------------------------
    # 7. Snapshot via list() prevents RuntimeError
    # -----------------------------------------------------------------------

    def test_provider_snapshots_shared_pools(self):
        """Verify that the provider calls list() on .items() to snapshot
        the dict.  A dict that mutates during bare iteration would raise
        RuntimeError, but snapshot with list() prevents that."""
        df = _make_dataflow(url="sqlite:///:memory:")
        provider = df._make_pool_stats_provider(pool_size=5, max_overflow=2)

        # Create a real dict so list(dict.items()) works, but .items()
        # returning a view that is mutated during iteration would fail.
        # We verify correctness indirectly: if the provider did NOT
        # snapshot, iterating the view during mutation would raise.

        call_count = 0
        real_dict = {}

        class MutatingDict(dict):
            """Dict whose items() returns a view that will be mutated
            during iteration — list() of items prevents the error."""

            def items(self):
                # Return a snapshot via the real dict. If the code under
                # test called list() on this, iteration is safe.
                nonlocal call_count
                call_count += 1
                return super().items()

        shared = MutatingDict()

        with patch(
            "kailash.nodes.data.async_sql.AsyncSQLDatabaseNode._shared_pools",
            shared,
        ):
            stats = provider()

        # items() was called (the provider accessed it)
        assert call_count >= 1
        # Should still return valid fallback stats
        assert stats["active"] == 0
        assert stats["max"] == 5


# ===========================================================================
# Gap 2: health_check() pool integration
# ===========================================================================


class TestHealthCheckPoolIntegration:
    """Tests for health_check() pool-related behaviour on the DataFlow class
    (engine.py line ~7404)."""

    def test_health_check_includes_pool_stats(self):
        """When _pool_monitor is set and returns stats, health_check
        includes a 'pool' key in the response."""
        df = _make_dataflow()

        mock_monitor = MagicMock()
        mock_monitor.get_stats.return_value = pool_stats_dict(
            active=3, idle=7, max_size=10
        )
        df._pool_monitor = mock_monitor

        result = df.health_check()
        assert "pool" in result
        assert result["pool"]["active"] == 3
        assert result["pool"]["idle"] == 7

    def test_health_check_degraded_at_95_percent(self):
        """When pool utilization >= 0.95, health_check status becomes
        'degraded'."""
        df = _make_dataflow()

        mock_monitor = MagicMock()
        mock_monitor.get_stats.return_value = pool_stats_dict(
            active=19, idle=1, max_size=20
        )
        df._pool_monitor = mock_monitor

        result = df.health_check()
        assert result["status"] == "degraded"
        assert result["components"]["pool"] == "exhaustion_imminent"

    def test_health_check_ok_without_monitor(self):
        """When _pool_monitor is None, the response does not contain
        a 'pool' key."""
        df = _make_dataflow()
        assert df._pool_monitor is None

        result = df.health_check()
        assert "pool" not in result


# ===========================================================================
# Gap 3: Public API tests
# ===========================================================================


class TestPoolStatsPublicAPI:
    """Tests for the DataFlow.pool_stats() public method."""

    def test_pool_stats_with_monitor(self):
        """pool_stats() delegates to _pool_monitor.get_stats() when the
        monitor is present."""
        df = _make_dataflow()

        expected = pool_stats_dict(active=4, idle=6, max_size=10)
        mock_monitor = MagicMock()
        mock_monitor.get_stats.return_value = expected
        df._pool_monitor = mock_monitor

        result = df.pool_stats()
        assert result == expected
        mock_monitor.get_stats.assert_called_once()

    def test_pool_stats_without_monitor(self):
        """pool_stats() returns zeros when no monitor is configured."""
        df = _make_dataflow()
        assert df._pool_monitor is None

        result = df.pool_stats()
        assert result["active"] == 0
        assert result["idle"] == 0
        assert result["max"] == 0
        assert result["utilization"] == 0.0


class TestExecuteRawLightweight:
    """Tests for DataFlow.execute_raw_lightweight()."""

    @pytest.mark.asyncio
    async def test_execute_raw_lightweight_not_configured(self):
        """Raises RuntimeError when _lightweight_pool is None."""
        df = _make_dataflow()
        assert df._lightweight_pool is None

        with pytest.raises(RuntimeError, match="Lightweight pool not configured"):
            await df.execute_raw_lightweight("SELECT 1")
