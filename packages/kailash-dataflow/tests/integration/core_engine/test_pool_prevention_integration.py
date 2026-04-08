# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for connection pool prevention features.

Requires: PostgreSQL running on localhost:5434
  docker run -d --name kailash_sdk_test_postgres \
    -e POSTGRES_USER=test_user -e POSTGRES_PASSWORD=test_password \
    -e POSTGRES_DB=kailash_test -p 5434:5432 postgres:16-alpine

Tests M0 (consolidated defaults), M2 (auto-scaling), M3 (startup validation),
M4 (pool monitor), M5 (leak detection), M10 (lightweight pool).
"""

from __future__ import annotations

import contextlib
import logging
import os
import time

import pytest


@contextlib.contextmanager
def env_override(updates: dict, clear: bool = False):
    """Temporarily override environment variables.

    Real-infrastructure replacement for ``unittest.mock.patch.dict`` — mutates
    ``os.environ`` in place and restores the prior state on exit, so tests
    remain fully isolated from the process environment without relying on
    ``unittest.mock`` in Tier 2.
    """
    previous = os.environ.copy()
    try:
        if clear:
            os.environ.clear()
        os.environ.update(updates)
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


# Database URL for integration tests
PG_URL = "postgresql://test_user:test_password@localhost:5434/kailash_test"


def pg_available() -> bool:
    """Check if PostgreSQL is available on the expected port."""
    try:
        import psycopg2

        conn = psycopg2.connect(PG_URL, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


skip_no_pg = pytest.mark.skipif(
    not pg_available(), reason="PostgreSQL not available on localhost:5434"
)


# ---------------------------------------------------------------------------
# M2: Auto-Scaling Integration Tests
# ---------------------------------------------------------------------------


@skip_no_pg
class TestAutoScalingIntegration:
    """Test pool auto-scaling against real PostgreSQL."""

    def test_probe_max_connections_returns_real_value(self):
        """probe_max_connections() should return the actual PG max_connections."""
        from dataflow.core.pool_utils import probe_max_connections

        result = probe_max_connections(PG_URL)
        assert result is not None
        assert isinstance(result, int)
        assert result >= 10  # PG default is 100, but could be configured lower

    def test_auto_scaling_produces_safe_pool_size(self):
        """Auto-scaled pool_size must be <= 70% of max_connections."""
        from dataflow.core.config import DatabaseConfig
        from dataflow.core.pool_utils import probe_max_connections

        # Clear env vars so auto-scaling engages
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("DATAFLOW_POOL_SIZE", "DB_POOL_SIZE")
        }
        with env_override(env, clear=True):
            config = DatabaseConfig(url=PG_URL)
            pool_size = config.get_pool_size()

        db_max = probe_max_connections(PG_URL)
        assert pool_size <= int(db_max * 0.7)
        assert pool_size >= 2

    def test_explicit_pool_size_overrides_auto(self):
        """Explicit pool_size=25 should ignore auto-scaling."""
        from dataflow.core.config import DatabaseConfig

        config = DatabaseConfig(url=PG_URL, pool_size=25)
        assert config.get_pool_size() == 25

    def test_env_var_overrides_auto(self):
        """DATAFLOW_POOL_SIZE env var should override auto-scaling."""
        from dataflow.core.config import DatabaseConfig

        with env_override({"DATAFLOW_POOL_SIZE": "15"}):
            config = DatabaseConfig(url=PG_URL)
            assert config.get_pool_size() == 15

    def test_worker_count_affects_pool_size(self):
        """More workers should produce smaller per-worker pool size."""
        from dataflow.core.config import DatabaseConfig

        env_base = {
            k: v
            for k, v in os.environ.items()
            if k not in ("DATAFLOW_POOL_SIZE", "DB_POOL_SIZE", "DATAFLOW_WORKER_COUNT")
        }

        with env_override({**env_base, "DATAFLOW_WORKER_COUNT": "1"}, clear=True):
            config1 = DatabaseConfig(url=PG_URL)
            size_1_worker = config1.get_pool_size()

        with env_override({**env_base, "DATAFLOW_WORKER_COUNT": "4"}, clear=True):
            config4 = DatabaseConfig(url=PG_URL)
            size_4_workers = config4.get_pool_size()

        assert size_4_workers < size_1_worker
        assert size_4_workers >= 2


# ---------------------------------------------------------------------------
# M3: Startup Validation Integration Tests
# ---------------------------------------------------------------------------


@skip_no_pg
class TestStartupValidationIntegration:
    """Test startup validation against real PostgreSQL."""

    def test_safe_config_logs_info(self, caplog):
        """Safe pool config should log INFO 'validated'."""
        from dataflow.core.pool_validator import validate_pool_config

        with caplog.at_level(logging.INFO):
            result = validate_pool_config(PG_URL, pool_size=5, max_overflow=2)

        assert result["status"] == "safe"
        assert result["db_max"] is not None
        assert result["db_max"] >= 10  # PG default is 100, accept any reasonable value

    def test_dangerous_config_logs_error(self, caplog):
        """Pool_size=50 x 4 workers should trigger ERROR."""
        from dataflow.core.pool_validator import validate_pool_config

        with env_override({"DATAFLOW_WORKER_COUNT": "4"}):
            with caplog.at_level(logging.ERROR):
                result = validate_pool_config(PG_URL, pool_size=50, max_overflow=10)

        assert result["status"] == "error"
        assert "WILL EXHAUST" in result["message"]
        assert result["total_possible"] == (50 + 10) * 4  # 240

    def test_near_limit_logs_warning(self, caplog):
        """75% utilization should trigger WARNING."""
        from dataflow.core.pool_validator import validate_pool_config

        with env_override({"DATAFLOW_WORKER_COUNT": "1"}):
            with caplog.at_level(logging.WARNING):
                # 75 out of 100 = 75%, above safe threshold of 70%
                result = validate_pool_config(PG_URL, pool_size=60, max_overflow=15)

        assert result["status"] == "warning"
        assert "NEAR LIMIT" in result["message"]

    def test_remediation_message_is_actionable(self, caplog):
        """ERROR log should include correct suggested pool_size."""
        from dataflow.core.pool_validator import validate_pool_config

        with env_override({"DATAFLOW_WORKER_COUNT": "4"}):
            result = validate_pool_config(PG_URL, pool_size=50, max_overflow=10)

        # Suggested: max(2, int(100 * 0.7) // 4) = 17
        # Suggested: max(2, int(100 * 0.7) // (4 * 3 // 2)) = 11
        assert "DATAFLOW_POOL_SIZE=11" in result["message"]


# ---------------------------------------------------------------------------
# M4+M5: Pool Monitor + Leak Detection Integration Tests
# ---------------------------------------------------------------------------


@skip_no_pg
class TestPoolMonitorIntegration:
    """Test pool monitor with real pool operations."""

    def test_pool_stats_returns_valid_structure(self):
        """pool_stats() should return dict with all required keys."""
        from dataflow.core.pool_monitor import PoolMonitor, pool_stats_dict

        stats = pool_stats_dict(active=3, idle=7, max_size=10)
        monitor = PoolMonitor(
            stats_provider=lambda: stats,
            interval_secs=0.5,
            leak_detection_enabled=False,
        )
        monitor.start()
        time.sleep(1)
        result = monitor.get_stats()
        monitor.stop()

        assert "active" in result
        assert "idle" in result
        assert "max" in result
        assert "utilization" in result
        assert result["utilization"] == 0.3  # 3/10

    def test_monitor_thread_lifecycle(self):
        """Monitor should start and stop cleanly with no leaked threads."""
        import threading

        from dataflow.core.pool_monitor import PoolMonitor, pool_stats_dict

        initial_threads = threading.active_count()
        stats = pool_stats_dict(active=0, idle=5, max_size=10)
        monitor = PoolMonitor(
            stats_provider=lambda: stats,
            interval_secs=0.1,
            leak_detection_enabled=False,
        )

        monitor.start()
        assert monitor.is_running
        time.sleep(0.3)
        monitor.stop()
        time.sleep(0.2)  # Let thread join

        assert not monitor.is_running
        assert threading.active_count() <= initial_threads + 1  # Allow 1 for GC

    def test_leak_detection_with_real_timing(self, caplog):
        """Leak detection should fire with real time measurements."""
        from dataflow.core.pool_monitor import PoolMonitor, pool_stats_dict

        stats = pool_stats_dict(active=1, idle=9, max_size=10)
        monitor = PoolMonitor(
            stats_provider=lambda: stats,
            interval_secs=0.1,
            leak_detection_enabled=True,
            leak_threshold_secs=0.2,
        )

        monitor.on_checkout(99)
        time.sleep(0.3)  # Hold past 0.2s threshold

        with caplog.at_level(logging.WARNING):
            monitor.start()
            time.sleep(0.5)
            monitor.stop()

        assert any("Connection held" in r.message for r in caplog.records)
        monitor.on_checkin(99)

    def test_no_thread_leaks_across_create_destroy(self):
        """Creating and destroying 10 monitors should not leak threads."""
        import threading

        from dataflow.core.pool_monitor import PoolMonitor, pool_stats_dict

        initial = threading.active_count()
        stats = pool_stats_dict(active=0, idle=5, max_size=5)

        for _ in range(10):
            m = PoolMonitor(
                stats_provider=lambda: stats,
                interval_secs=0.05,
                leak_detection_enabled=False,
            )
            m.start()
            time.sleep(0.1)
            m.stop()
            time.sleep(0.1)

        # Allow some tolerance for GC
        assert threading.active_count() <= initial + 2


# ---------------------------------------------------------------------------
# M10: Lightweight Pool Integration Tests
# ---------------------------------------------------------------------------


@skip_no_pg
class TestLightweightPoolIntegration:
    """Test lightweight health check pool against real PostgreSQL."""

    @pytest.mark.asyncio
    async def test_lightweight_pool_select_1(self):
        """Lightweight pool should execute SELECT 1 on real PostgreSQL."""
        from dataflow.core.pool_lightweight import LightweightPool

        pool = LightweightPool(PG_URL)
        await pool.initialize()
        result = await pool.execute_raw("SELECT 1")
        assert len(result) == 1
        assert result[0][0] == 1  # asyncpg returns Record objects
        await pool.close()

    @pytest.mark.asyncio
    async def test_lightweight_pool_show_max_connections(self):
        """Lightweight pool should be able to run SHOW max_connections."""
        from dataflow.core.pool_lightweight import LightweightPool

        pool = LightweightPool(PG_URL)
        await pool.initialize()
        result = await pool.execute_raw("SHOW max_connections")
        assert len(result) == 1
        max_conn = int(result[0][0])
        assert max_conn >= 10
        await pool.close()

    @pytest.mark.asyncio
    async def test_lightweight_pool_limited_to_2_connections(self):
        """Lightweight pool should have max 2 connections."""
        from dataflow.core.pool_lightweight import LightweightPool

        pool = LightweightPool(PG_URL, pool_size=2)
        await pool.initialize()
        assert pool._pool.get_max_size() == 2
        await pool.close()
