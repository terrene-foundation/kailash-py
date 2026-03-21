# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for pool utilization monitor and leak detection (PY-2, PY-5)."""

from __future__ import annotations

import logging
import time

import pytest

from dataflow.core.pool_monitor import PoolMonitor, pool_stats_dict


class TestPoolStatsDict:
    """Test the standardized pool stats dictionary."""

    def test_returns_all_keys(self):
        stats = pool_stats_dict(active=5, idle=10, max_size=20)
        assert "active" in stats
        assert "idle" in stats
        assert "max" in stats
        assert "overflow" in stats
        assert "max_overflow" in stats
        assert "utilization" in stats

    def test_calculates_utilization(self):
        stats = pool_stats_dict(active=10, idle=10, max_size=20)
        assert stats["utilization"] == 0.5

    def test_utilization_with_overflow(self):
        stats = pool_stats_dict(active=15, idle=5, max_size=20, max_overflow=10)
        # 15 / (20 + 10) = 0.5
        assert stats["utilization"] == 0.5

    def test_zero_capacity(self):
        stats = pool_stats_dict(active=0, idle=0, max_size=0)
        assert stats["utilization"] == 0.0


class TestPoolMonitor:
    """Test pool utilization monitoring."""

    def _make_monitor(self, stats=None, **kwargs):
        if stats is None:
            stats = pool_stats_dict(active=0, idle=5, max_size=10)
        provider = lambda: stats
        defaults = {
            "interval_secs": 0.1,
            "leak_detection_enabled": False,
        }
        defaults.update(kwargs)
        return PoolMonitor(stats_provider=provider, **defaults)

    def test_get_stats_returns_dict(self):
        monitor = self._make_monitor()
        stats = monitor.get_stats()
        assert isinstance(stats, dict)
        assert "active" in stats

    def test_start_and_stop(self):
        monitor = self._make_monitor()
        monitor.start()
        assert monitor.is_running
        monitor.stop()
        assert not monitor.is_running

    def test_daemon_thread(self):
        monitor = self._make_monitor()
        monitor.start()
        assert monitor._thread.daemon is True
        monitor.stop()

    def test_double_start_is_safe(self):
        monitor = self._make_monitor()
        monitor.start()
        monitor.start()  # Should not create a second thread
        assert monitor.is_running
        monitor.stop()

    def test_stop_without_start_is_safe(self):
        monitor = self._make_monitor()
        monitor.stop()  # Should not raise

    def test_collects_stats_on_cycle(self):
        stats = pool_stats_dict(active=5, idle=5, max_size=10)
        monitor = self._make_monitor(stats=stats)
        monitor.start()
        time.sleep(0.3)  # Let at least one cycle complete
        collected = monitor.get_stats()
        monitor.stop()
        assert collected["active"] == 5
        assert collected["utilization"] == 0.5

    def test_logs_warning_at_80_percent(self, caplog):
        stats = pool_stats_dict(active=17, idle=3, max_size=20)
        monitor = self._make_monitor(stats=stats)
        with caplog.at_level(logging.WARNING):
            monitor.start()
            time.sleep(0.3)
            monitor.stop()
        assert any(
            "[POOL]" in r.message and "approaching" in r.message for r in caplog.records
        )

    def test_logs_error_at_95_percent(self, caplog):
        stats = pool_stats_dict(active=19, idle=1, max_size=20)
        monitor = self._make_monitor(stats=stats, alert_on_exhaustion=True)
        with caplog.at_level(logging.ERROR):
            monitor.start()
            time.sleep(0.3)
            monitor.stop()
        assert any("EXHAUSTION IMMINENT" in r.message for r in caplog.records)

    def test_no_alert_when_disabled(self, caplog):
        stats = pool_stats_dict(active=19, idle=1, max_size=20)
        monitor = self._make_monitor(stats=stats, alert_on_exhaustion=False)
        with caplog.at_level(logging.ERROR):
            monitor.start()
            time.sleep(0.3)
            monitor.stop()
        assert not any("EXHAUSTION IMMINENT" in r.message for r in caplog.records)

    def test_silent_below_70_percent(self, caplog):
        stats = pool_stats_dict(active=5, idle=15, max_size=20)
        monitor = self._make_monitor(stats=stats)
        with caplog.at_level(logging.DEBUG):
            monitor.start()
            time.sleep(0.3)
            monitor.stop()
        pool_msgs = [r for r in caplog.records if "[POOL]" in r.message]
        assert len(pool_msgs) == 0

    def test_exception_in_provider_does_not_crash(self, caplog):
        def bad_provider():
            raise RuntimeError("simulated failure")

        monitor = PoolMonitor(
            stats_provider=bad_provider,
            interval_secs=0.1,
            leak_detection_enabled=False,
        )
        monitor.start()
        time.sleep(0.3)
        assert monitor.is_running  # Should not have crashed
        monitor.stop()


class TestLeakDetection:
    """Test connection leak detection (PY-5)."""

    def _make_monitor_with_leaks(self, threshold=0.5, interval=0.1):
        stats = pool_stats_dict(active=1, idle=9, max_size=10)
        return PoolMonitor(
            stats_provider=lambda: stats,
            interval_secs=interval,
            leak_detection_enabled=True,
            leak_threshold_secs=threshold,
        )

    def test_checkout_registers_connection(self):
        monitor = self._make_monitor_with_leaks()
        monitor.on_checkout(42)
        assert 42 in monitor._tracked_connections
        monitor.on_checkin(42)
        assert 42 not in monitor._tracked_connections

    def test_checkin_removes_connection(self):
        monitor = self._make_monitor_with_leaks()
        monitor.on_checkout(42)
        monitor.on_checkin(42)
        assert 42 not in monitor._tracked_connections

    def test_warning_on_held_connection(self, caplog):
        monitor = self._make_monitor_with_leaks(threshold=0.1)
        monitor.on_checkout(42)
        time.sleep(0.15)  # Hold past threshold
        with caplog.at_level(logging.WARNING):
            monitor.start()
            time.sleep(0.3)
            monitor.stop()
        assert any("Connection held" in r.message for r in caplog.records)
        monitor.on_checkin(42)

    def test_error_on_probable_leak(self, caplog):
        monitor = self._make_monitor_with_leaks(threshold=0.05)
        monitor.on_checkout(42)
        time.sleep(0.2)  # Hold past 3x threshold (0.15s)
        with caplog.at_level(logging.ERROR):
            monitor.start()
            time.sleep(0.3)
            monitor.stop()
        assert any("PROBABLE LEAK" in r.message for r in caplog.records)
        monitor.on_checkin(42)

    def test_no_warning_when_returned_quickly(self, caplog):
        monitor = self._make_monitor_with_leaks(threshold=10)
        monitor.on_checkout(42)
        monitor.on_checkin(42)  # Return immediately
        with caplog.at_level(logging.WARNING):
            monitor.start()
            time.sleep(0.3)
            monitor.stop()
        leak_msgs = [r for r in caplog.records if "Connection held" in r.message]
        assert len(leak_msgs) == 0

    def test_disabled_leak_detection(self):
        stats = pool_stats_dict(active=1, idle=9, max_size=10)
        monitor = PoolMonitor(
            stats_provider=lambda: stats,
            interval_secs=0.1,
            leak_detection_enabled=False,
        )
        monitor.on_checkout(42)
        assert 42 not in monitor._tracked_connections  # Not tracked

    def test_traceback_included_in_warning(self, caplog):
        monitor = self._make_monitor_with_leaks(threshold=0.1)
        monitor.on_checkout(42)
        time.sleep(0.15)
        with caplog.at_level(logging.WARNING):
            monitor.start()
            time.sleep(0.3)
            monitor.stop()
        msgs = [r.message for r in caplog.records if "Connection held" in r.message]
        assert len(msgs) > 0
        assert "File" in msgs[0]  # Traceback should be present
        monitor.on_checkin(42)

    def test_bounded_tracking(self):
        monitor = self._make_monitor_with_leaks()
        monitor._max_tracked = 10
        for i in range(15):
            monitor.on_checkout(i)
        assert len(monitor._tracked_connections) == 10  # Bounded
