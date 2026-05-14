"""Unit tests for DataFlow test mode API (ADR-017).

This test file covers:
1. Test mode auto-detection (pytest environment)
2. Explicit test mode enable/disable
3. Global test mode control (class methods)
4. Priority order (explicit > global > auto)
5. Cleanup methods (cleanup_stale_pools, cleanup_all_pools, get_cleanup_metrics)

Test Strategy:
- Tier 1 (Unit): Fast (<1s), isolated, focused on DataFlow API
- No external dependencies (uses SQLite in-memory)
- Tests written BEFORE implementation (TDD)
"""

import logging
import sys

import pytest

from dataflow import DataFlow


class TestDataFlowTestModeDetection:
    """Test automatic pytest environment detection."""

    def test_auto_detect_pytest_environment(self):
        """Test that pytest environment is auto-detected via PYTEST_CURRENT_TEST."""
        # PYTEST_CURRENT_TEST is set by pytest automatically
        # This test verifies auto-detection works
        with DataFlow(":memory:") as db:
            # Should be True since we're running in pytest
            assert db._test_mode is True

    def test_auto_detect_pytest_via_sys_modules(self, monkeypatch):
        """Test detection via pytest in sys.modules."""
        # pytest should be in sys.modules when running
        assert "pytest" in sys.modules

        # Create DataFlow - should detect pytest
        with DataFlow(":memory:") as db:
            assert db._test_mode is True

    def test_explicit_test_mode_true(self):
        """Test explicit test_mode=True."""
        with DataFlow(":memory:", test_mode=True) as db:
            assert db._test_mode is True

    def test_explicit_test_mode_false(self):
        """Test explicit test_mode=False disables auto-detection."""
        # Even though we're in pytest, explicit False overrides
        with DataFlow(":memory:", test_mode=False) as db:
            assert db._test_mode is False

    def test_explicit_test_mode_none(self):
        """Test test_mode=None falls back to auto-detection."""
        with DataFlow(":memory:", test_mode=None) as db:
            # Should detect pytest environment
            assert db._test_mode is True

    def test_test_mode_aggressive_cleanup_default(self):
        """Test test_mode_aggressive_cleanup defaults to True."""
        with DataFlow(":memory:", test_mode=True) as db:
            assert db._test_mode_aggressive_cleanup is True

    def test_test_mode_aggressive_cleanup_custom(self):
        """Test custom test_mode_aggressive_cleanup setting."""
        with DataFlow(
            ":memory:", test_mode=True, test_mode_aggressive_cleanup=False
        ) as db:
            assert db._test_mode is True
            assert db._test_mode_aggressive_cleanup is False


class TestDataFlowGlobalTestMode:
    """Test global test mode control (class methods)."""

    def setup_method(self):
        """Ensure global test mode is reset before each test."""
        DataFlow.disable_test_mode()

    def teardown_method(self):
        """Clean up global test mode after each test."""
        DataFlow.disable_test_mode()

    def test_enable_global_test_mode(self):
        """Test DataFlow.enable_test_mode() class method."""
        DataFlow.enable_test_mode()

        # Verify global setting
        assert DataFlow.is_test_mode_enabled() is True

        # New instance should have test mode enabled
        with DataFlow(":memory:") as db:
            assert db._test_mode is True

    def test_disable_global_test_mode(self):
        """Test DataFlow.disable_test_mode() class method."""
        DataFlow.enable_test_mode()
        assert DataFlow.is_test_mode_enabled() is True

        DataFlow.disable_test_mode()
        assert DataFlow.is_test_mode_enabled() is None

        # Should fall back to auto-detection
        with DataFlow(":memory:") as db:
            assert db._test_mode is True  # Still True due to pytest auto-detection

    def test_is_test_mode_enabled_returns_none_by_default(self):
        """Test is_test_mode_enabled() returns None when not set."""
        DataFlow.disable_test_mode()
        assert DataFlow.is_test_mode_enabled() is None

    def test_global_mode_affects_new_instances(self):
        """Test global mode only affects new instances."""
        # Create instance before enabling global mode
        with DataFlow(":memory:", test_mode=False) as db1:
            assert db1._test_mode is False

            # Enable global test mode
            DataFlow.enable_test_mode()

            # Old instance unaffected
            assert db1._test_mode is False

            # New instance affected
            with DataFlow(":memory:") as db2:
                assert db2._test_mode is True


class TestDataFlowTestModePriority:
    """Test priority order: explicit > global > auto."""

    def setup_method(self):
        """Reset global test mode before each test."""
        DataFlow.disable_test_mode()

    def teardown_method(self):
        """Clean up global test mode after each test."""
        DataFlow.disable_test_mode()

    def test_explicit_overrides_global(self):
        """Test explicit test_mode overrides global setting."""
        DataFlow.enable_test_mode()

        # Explicit False overrides global True
        with DataFlow(":memory:", test_mode=False) as db:
            assert db._test_mode is False

    def test_explicit_overrides_auto_detection(self):
        """Test explicit test_mode overrides auto-detection."""
        # We're in pytest, so auto-detection would be True
        with DataFlow(":memory:", test_mode=False) as db:
            assert db._test_mode is False

    def test_global_overrides_auto_detection(self):
        """Test global setting overrides auto-detection."""
        # Disable global test mode explicitly (not None)
        DataFlow._global_test_mode = False

        # Should use global False instead of auto-detected True
        with DataFlow(":memory:") as db:
            assert db._test_mode is False

        # Cleanup
        DataFlow.disable_test_mode()

    def test_priority_order_all_three_set(self):
        """Test priority when all three are set."""
        DataFlow._global_test_mode = True
        # Explicit wins over global and auto
        with DataFlow(":memory:", test_mode=False) as db:
            assert db._test_mode is False


class TestDataFlowTestModeLogging:
    """Test logging output for test mode activation."""

    def test_test_mode_explicit_logged(self, caplog):
        """Test explicit test mode activation is logged."""
        caplog.set_level(logging.INFO)

        with DataFlow(":memory:", test_mode=True):
            # Check log contains test mode message
            assert any(
                "Test mode enabled" in record.message for record in caplog.records
            )
            assert any("explicitly set" in record.message for record in caplog.records)

    def test_test_mode_auto_detect_logged(self, caplog):
        """Test auto-detected test mode is logged."""
        caplog.set_level(logging.INFO)

        with DataFlow(":memory:"):  # Auto-detect
            # Check log contains auto-detection message
            assert any(
                "Test mode enabled" in record.message for record in caplog.records
            )
            assert any("auto-detected" in record.message for record in caplog.records)

    def test_test_mode_global_logged(self, caplog):
        """Test global test mode activation is logged."""
        caplog.set_level(logging.INFO)

        DataFlow.enable_test_mode()
        try:
            with DataFlow(":memory:"):
                # Check log contains global setting message
                assert any(
                    "Test mode enabled" in record.message for record in caplog.records
                )
                assert any(
                    "global setting" in record.message for record in caplog.records
                )
        finally:
            DataFlow.disable_test_mode()

    def test_aggressive_cleanup_logged(self, caplog):
        """Test aggressive cleanup activation is logged."""
        caplog.set_level(logging.DEBUG)

        with DataFlow(":memory:", test_mode=True, test_mode_aggressive_cleanup=True):
            # Check debug log contains aggressive cleanup message
            assert any(
                "Aggressive pool cleanup enabled" in record.message
                for record in caplog.records
            )


@pytest.mark.asyncio
class TestDataFlowCleanupMethods:
    """Test cleanup methods (cleanup_stale_pools, cleanup_all_pools, get_cleanup_metrics)."""

    async def test_cleanup_stale_pools_returns_metrics(self):
        """Test cleanup_stale_pools() returns proper metrics structure."""
        db = DataFlow(":memory:", test_mode=True)
        try:
            metrics = await db.cleanup_stale_pools()

            # Verify metrics structure
            assert "stale_pools_found" in metrics
            assert "stale_pools_cleaned" in metrics
            assert "cleanup_failures" in metrics
            assert "cleanup_errors" in metrics
            assert "cleanup_duration_ms" in metrics

            # Verify types
            assert isinstance(metrics["stale_pools_found"], int)
            assert isinstance(metrics["stale_pools_cleaned"], int)
            assert isinstance(metrics["cleanup_failures"], int)
            assert isinstance(metrics["cleanup_errors"], list)
            assert isinstance(metrics["cleanup_duration_ms"], float)
        finally:
            await db.close_async()

    async def test_cleanup_stale_pools_no_failures(self):
        """Test cleanup_stale_pools() succeeds with no pools."""
        db = DataFlow(":memory:", test_mode=True)
        try:
            metrics = await db.cleanup_stale_pools()

            # Should succeed with no failures
            assert metrics["cleanup_failures"] == 0
            assert len(metrics["cleanup_errors"]) == 0
        finally:
            await db.close_async()

    async def test_cleanup_all_pools_returns_metrics(self):
        """Test cleanup_all_pools() returns proper metrics structure."""
        db = DataFlow(":memory:", test_mode=True)
        try:
            metrics = await db.cleanup_all_pools()

            # Verify metrics structure
            assert "total_pools" in metrics
            assert "pools_cleaned" in metrics
            assert "cleanup_failures" in metrics
            assert "cleanup_errors" in metrics
            assert "cleanup_duration_ms" in metrics
            assert "forced" in metrics

            # Verify types
            assert isinstance(metrics["total_pools"], int)
            assert isinstance(metrics["pools_cleaned"], int)
            assert isinstance(metrics["cleanup_failures"], int)
            assert isinstance(metrics["cleanup_errors"], list)
            assert isinstance(metrics["cleanup_duration_ms"], float)
            assert isinstance(metrics["forced"], bool)
        finally:
            await db.close_async()

    async def test_cleanup_all_pools_force_parameter(self):
        """Test cleanup_all_pools() respects force parameter."""
        db = DataFlow(":memory:", test_mode=True)
        try:
            metrics_graceful = await db.cleanup_all_pools(force=False)
            assert metrics_graceful["forced"] is False

            metrics_forced = await db.cleanup_all_pools(force=True)
            assert metrics_forced["forced"] is True
        finally:
            await db.close_async()

    async def test_cleanup_all_pools_no_failures(self):
        """Test cleanup_all_pools() succeeds with no pools."""
        db = DataFlow(":memory:", test_mode=True)
        try:
            metrics = await db.cleanup_all_pools()

            # Should succeed with no failures
            assert metrics["cleanup_failures"] == 0
            assert len(metrics["cleanup_errors"]) == 0
        finally:
            await db.close_async()

    async def test_get_cleanup_metrics_returns_metrics(self):
        """Test get_cleanup_metrics() returns proper metrics structure."""
        db = DataFlow(":memory:", test_mode=True)
        try:
            metrics = db.get_cleanup_metrics()

            # Verify metrics structure
            assert "active_pools" in metrics
            assert "total_pools_created" in metrics
            assert "test_mode_enabled" in metrics
            assert "aggressive_cleanup_enabled" in metrics
            assert "pool_keys" in metrics
            assert "event_loop_ids" in metrics

            # Verify types
            assert isinstance(metrics["active_pools"], int)
            assert isinstance(metrics["total_pools_created"], int)
            assert isinstance(metrics["test_mode_enabled"], bool)
            assert isinstance(metrics["aggressive_cleanup_enabled"], bool)
            assert isinstance(metrics["pool_keys"], list)
            assert isinstance(metrics["event_loop_ids"], list)
        finally:
            await db.close_async()

    async def test_get_cleanup_metrics_test_mode_enabled(self):
        """Test get_cleanup_metrics() reports test mode status."""
        db = DataFlow(":memory:", test_mode=True)
        try:
            metrics = db.get_cleanup_metrics()

            assert metrics["test_mode_enabled"] is True
            assert metrics["aggressive_cleanup_enabled"] is True
        finally:
            await db.close_async()

    async def test_get_cleanup_metrics_test_mode_disabled(self):
        """Test get_cleanup_metrics() reports test mode disabled."""
        db = DataFlow(":memory:", test_mode=False)
        try:
            metrics = db.get_cleanup_metrics()

            assert metrics["test_mode_enabled"] is False
        finally:
            await db.close_async()


@pytest.mark.asyncio
class TestDataFlowCleanupGracefulDegradation:
    """Test graceful error handling in cleanup methods."""

    async def test_cleanup_stale_pools_handles_errors(self):
        """Test cleanup_stale_pools() gracefully handles errors."""
        db = DataFlow(":memory:", test_mode=True)
        try:
            # Should not raise even if cleanup fails
            try:
                metrics = await db.cleanup_stale_pools()
                # Verify metrics returned
                assert "cleanup_failures" in metrics
                assert "cleanup_errors" in metrics
            except Exception as e:
                pytest.fail(f"cleanup_stale_pools() should not raise: {e}")
        finally:
            await db.close_async()

    async def test_cleanup_all_pools_handles_errors(self):
        """Test cleanup_all_pools() gracefully handles errors."""
        db = DataFlow(":memory:", test_mode=True)
        try:
            # Should not raise even if cleanup fails
            try:
                metrics = await db.cleanup_all_pools()
                # Verify metrics returned
                assert "cleanup_failures" in metrics
                assert "cleanup_errors" in metrics
            except Exception as e:
                pytest.fail(f"cleanup_all_pools() should not raise: {e}")
        finally:
            await db.close_async()

    async def test_get_cleanup_metrics_handles_errors(self):
        """Test get_cleanup_metrics() gracefully handles errors."""
        db = DataFlow(":memory:", test_mode=True)
        try:
            # Should not raise
            try:
                metrics = db.get_cleanup_metrics()
                # Verify metrics returned
                assert "active_pools" in metrics
            except Exception as e:
                pytest.fail(f"get_cleanup_metrics() should not raise: {e}")
        finally:
            await db.close_async()


class TestDataFlowBackwardCompatibility:
    """Test backward compatibility - existing code works unchanged."""

    def test_existing_code_no_test_mode(self):
        """Test existing code without test_mode parameter works."""
        # Old code without test_mode parameter
        with DataFlow(":memory:") as db:
            # Should work and auto-detect test mode
            assert db._test_mode is True  # Auto-detected in pytest

    def test_existing_code_with_config(self):
        """Test existing code with DataFlowConfig still works."""
        from dataflow.core.config import DataFlowConfig

        config = DataFlowConfig(database_url=":memory:")
        with DataFlow(config=config) as db:
            # Should work and auto-detect test mode
            assert db._test_mode is True

    def test_no_breaking_changes(self):
        """Test no breaking changes to constructor signature."""
        # All existing parameter combinations should work
        with (
            DataFlow(":memory:") as db1,
            DataFlow(database_url=":memory:") as db2,
            DataFlow(":memory:", pool_size=10) as db3,
            DataFlow(":memory:", debug=True) as db4,
        ):
            # All should succeed
            assert db1 is not None
            assert db2 is not None
            assert db3 is not None
            assert db4 is not None
