"""Unit tests for the ResourceQuotas and QuotaEnforcer module.

Tests quota validation, concurrency limiting via semaphore, duration
enforcement via asyncio.timeout, and queue depth limits.
"""

import asyncio

import pytest
import pytest_asyncio

from kailash.runtime.quotas import (
    QuotaEnforcer,
    QuotaExceededError,
    ResourceQuotas,
    WorkflowDurationExceededError,
)


class TestResourceQuotas:
    """Tests for the ResourceQuotas dataclass."""

    def test_default_values(self):
        """ResourceQuotas should have sensible defaults."""
        quotas = ResourceQuotas()

        assert quotas.max_concurrent_workflows == 100
        assert quotas.max_workflow_duration_seconds == 3600.0
        assert quotas.max_queued_workflows == 1000

    def test_custom_values(self):
        """ResourceQuotas should accept custom values."""
        quotas = ResourceQuotas(
            max_concurrent_workflows=20,
            max_workflow_duration_seconds=600.0,
            max_queued_workflows=50,
        )

        assert quotas.max_concurrent_workflows == 20
        assert quotas.max_workflow_duration_seconds == 600.0
        assert quotas.max_queued_workflows == 50

    def test_invalid_max_concurrent_raises(self):
        """max_concurrent_workflows must be >= 1."""
        with pytest.raises(ValueError, match="max_concurrent_workflows"):
            ResourceQuotas(max_concurrent_workflows=0)

        with pytest.raises(ValueError, match="max_concurrent_workflows"):
            ResourceQuotas(max_concurrent_workflows=-5)

    def test_invalid_max_duration_raises(self):
        """max_workflow_duration_seconds must be > 0."""
        with pytest.raises(ValueError, match="max_workflow_duration_seconds"):
            ResourceQuotas(max_workflow_duration_seconds=0)

        with pytest.raises(ValueError, match="max_workflow_duration_seconds"):
            ResourceQuotas(max_workflow_duration_seconds=-10.0)

    def test_invalid_max_queued_raises(self):
        """max_queued_workflows must be >= 0."""
        with pytest.raises(ValueError, match="max_queued_workflows"):
            ResourceQuotas(max_queued_workflows=-1)

    def test_zero_queue_allowed(self):
        """max_queued_workflows=0 should be valid (reject all queuing)."""
        quotas = ResourceQuotas(max_queued_workflows=0)
        assert quotas.max_queued_workflows == 0

    def test_nan_max_concurrent_rejected(self):
        """NaN for max_concurrent_workflows must be rejected."""
        import math

        with pytest.raises(ValueError, match="max_concurrent_workflows"):
            ResourceQuotas(max_concurrent_workflows=math.nan)

    def test_inf_duration_rejected(self):
        """Inf for max_workflow_duration_seconds must be rejected."""
        import math

        with pytest.raises(ValueError, match="max_workflow_duration_seconds"):
            ResourceQuotas(max_workflow_duration_seconds=math.inf)


class TestQuotaExceededError:
    """Tests for the QuotaExceededError exception."""

    def test_attributes(self):
        """Error should carry quota name, current, and max values."""
        err = QuotaExceededError(
            quota_name="max_queued_workflows",
            current_value=500,
            max_value=500,
        )

        assert err.quota_name == "max_queued_workflows"
        assert err.current_value == 500
        assert err.max_value == 500

    def test_message(self):
        """Error message should be informative."""
        err = QuotaExceededError("max_concurrent", 10, 10)
        msg = str(err)
        assert "max_concurrent" in msg
        assert "10" in msg


class TestWorkflowDurationExceededError:
    """Tests for the WorkflowDurationExceededError exception."""

    def test_attributes(self):
        """Error should carry duration, max, and optional workflow_id."""
        err = WorkflowDurationExceededError(
            duration_seconds=3601.5,
            max_seconds=3600.0,
            workflow_id="wf-123",
        )

        assert err.duration_seconds == 3601.5
        assert err.max_seconds == 3600.0
        assert err.workflow_id == "wf-123"

    def test_message_with_workflow_id(self):
        """Message should include workflow_id when provided."""
        err = WorkflowDurationExceededError(100.0, 60.0, "wf-abc")
        assert "wf-abc" in str(err)

    def test_message_without_workflow_id(self):
        """Message should work without workflow_id."""
        err = WorkflowDurationExceededError(100.0, 60.0)
        msg = str(err)
        assert "100.0" in msg
        assert "60.0" in msg


class TestQuotaEnforcer:
    """Tests for the QuotaEnforcer class."""

    def test_init_with_defaults(self):
        """QuotaEnforcer should initialize with default quotas."""
        enforcer = QuotaEnforcer()

        assert enforcer.quotas.max_concurrent_workflows == 100
        assert enforcer.active_count == 0
        assert enforcer.queued_count == 0
        assert enforcer.available_slots == 100

    def test_init_with_custom_quotas(self):
        """QuotaEnforcer should accept custom ResourceQuotas."""
        quotas = ResourceQuotas(max_concurrent_workflows=5)
        enforcer = QuotaEnforcer(quotas)

        assert enforcer.quotas.max_concurrent_workflows == 5
        assert enforcer.available_slots == 5

    def test_stats_property(self):
        """stats should return a comprehensive statistics dict."""
        quotas = ResourceQuotas(
            max_concurrent_workflows=10,
            max_workflow_duration_seconds=300.0,
            max_queued_workflows=50,
        )
        enforcer = QuotaEnforcer(quotas)

        stats = enforcer.stats
        assert stats["active"] == 0
        assert stats["queued"] == 0
        assert stats["available"] == 10
        assert stats["total_acquired"] == 0
        assert stats["total_released"] == 0
        assert stats["total_rejected"] == 0
        assert stats["max_concurrent"] == 10
        assert stats["max_duration_seconds"] == 300.0
        assert stats["max_queued"] == 50


@pytest.mark.asyncio
class TestQuotaEnforcerAsync:
    """Async tests for QuotaEnforcer acquire/release operations."""

    async def test_acquire_and_release(self):
        """Basic acquire/release cycle should work."""
        enforcer = QuotaEnforcer(ResourceQuotas(max_concurrent_workflows=5))

        token = await enforcer.acquire_slot()
        assert enforcer.active_count == 1
        assert enforcer.available_slots == 4

        enforcer.release_slot(token)
        assert enforcer.active_count == 0
        assert enforcer.available_slots == 5

    async def test_acquire_multiple_slots(self):
        """Multiple slots should be acquirable up to the limit."""
        enforcer = QuotaEnforcer(ResourceQuotas(max_concurrent_workflows=3))

        t1 = await enforcer.acquire_slot()
        t2 = await enforcer.acquire_slot()
        t3 = await enforcer.acquire_slot()

        assert enforcer.active_count == 3
        assert enforcer.available_slots == 0

        enforcer.release_slot(t1)
        assert enforcer.active_count == 2

        enforcer.release_slot(t2)
        enforcer.release_slot(t3)
        assert enforcer.active_count == 0

    async def test_release_invalid_token_raises(self):
        """Releasing an unknown token should raise KeyError."""
        enforcer = QuotaEnforcer()

        from kailash.runtime.quotas import _SlotToken

        fake_token = _SlotToken(token_id="nonexistent")

        with pytest.raises(KeyError, match="not found"):
            enforcer.release_slot(fake_token)

    async def test_double_release_raises(self):
        """Releasing the same token twice should raise KeyError."""
        enforcer = QuotaEnforcer(ResourceQuotas(max_concurrent_workflows=5))

        token = await enforcer.acquire_slot()
        enforcer.release_slot(token)

        with pytest.raises(KeyError, match="already been released"):
            enforcer.release_slot(token)

    async def test_queue_depth_enforcement(self):
        """Attempting to queue beyond max_queued_workflows should raise."""
        enforcer = QuotaEnforcer(
            ResourceQuotas(
                max_concurrent_workflows=1,
                max_queued_workflows=0,
            )
        )

        # Acquire the only slot
        token = await enforcer.acquire_slot()

        # With max_queued=0, the next acquire should fail immediately
        with pytest.raises(QuotaExceededError) as exc_info:
            await enforcer.acquire_slot()

        assert exc_info.value.quota_name == "max_queued_workflows"
        assert exc_info.value.max_value == 0

        enforcer.release_slot(token)

    async def test_context_manager_acquire_and_release(self):
        """The acquire() context manager should acquire and release automatically."""
        enforcer = QuotaEnforcer(
            ResourceQuotas(
                max_concurrent_workflows=5,
                max_workflow_duration_seconds=10.0,
            )
        )

        async with enforcer.acquire() as token:
            assert enforcer.active_count == 1
            assert token.token_id in enforcer._active_slots

        # After exiting, slot should be released
        assert enforcer.active_count == 0

    async def test_context_manager_duration_enforcement(self):
        """The acquire() context manager should enforce duration limits."""
        enforcer = QuotaEnforcer(
            ResourceQuotas(
                max_concurrent_workflows=5,
                max_workflow_duration_seconds=0.1,  # 100ms timeout
            )
        )

        with pytest.raises(WorkflowDurationExceededError):
            async with enforcer.acquire():
                await asyncio.sleep(0.5)  # Exceeds the 100ms timeout

        # Slot should be released even on timeout
        assert enforcer.active_count == 0

    async def test_context_manager_custom_timeout(self):
        """The acquire() context manager should accept per-call timeout."""
        enforcer = QuotaEnforcer(
            ResourceQuotas(
                max_concurrent_workflows=5,
                max_workflow_duration_seconds=3600.0,  # Large default
            )
        )

        with pytest.raises(WorkflowDurationExceededError):
            async with enforcer.acquire(timeout_seconds=0.1):
                await asyncio.sleep(0.5)

    async def test_context_manager_releases_on_exception(self):
        """The acquire() context manager should release the slot on exceptions."""
        enforcer = QuotaEnforcer(ResourceQuotas(max_concurrent_workflows=5))

        with pytest.raises(RuntimeError, match="test error"):
            async with enforcer.acquire():
                raise RuntimeError("test error")

        assert enforcer.active_count == 0

    async def test_stats_tracking(self):
        """Stats should track total acquired, released, and rejected."""
        enforcer = QuotaEnforcer(
            ResourceQuotas(
                max_concurrent_workflows=1,
                max_queued_workflows=0,
            )
        )

        t1 = await enforcer.acquire_slot()
        assert enforcer.stats["total_acquired"] == 1

        # This should be rejected (queue full)
        with pytest.raises(QuotaExceededError):
            await enforcer.acquire_slot()
        assert enforcer.stats["total_rejected"] == 1

        enforcer.release_slot(t1)
        assert enforcer.stats["total_released"] == 1

    async def test_concurrent_acquire_respects_limit(self):
        """Concurrent acquires should respect the concurrency limit."""
        enforcer = QuotaEnforcer(
            ResourceQuotas(
                max_concurrent_workflows=2,
                max_queued_workflows=10,
            )
        )

        acquired_count = 0
        max_concurrent_observed = 0

        async def worker():
            nonlocal acquired_count, max_concurrent_observed
            token = await enforcer.acquire_slot()
            acquired_count += 1
            current = enforcer.active_count
            if current > max_concurrent_observed:
                max_concurrent_observed = current
            await asyncio.sleep(0.05)
            enforcer.release_slot(token)

        # Launch 5 workers that should be limited to 2 concurrent
        tasks = [asyncio.create_task(worker()) for _ in range(5)]
        await asyncio.gather(*tasks)

        assert acquired_count == 5
        assert max_concurrent_observed <= 2

    async def test_semaphore_fairness(self):
        """Slots should become available after release for waiting acquires."""
        enforcer = QuotaEnforcer(
            ResourceQuotas(
                max_concurrent_workflows=1,
                max_queued_workflows=5,
            )
        )

        results = []

        async def first_worker():
            token = await enforcer.acquire_slot()
            results.append("first_acquired")
            await asyncio.sleep(0.05)
            enforcer.release_slot(token)
            results.append("first_released")

        async def second_worker():
            # Small delay to ensure first worker acquires first
            await asyncio.sleep(0.01)
            token = await enforcer.acquire_slot()
            results.append("second_acquired")
            enforcer.release_slot(token)

        await asyncio.gather(first_worker(), second_worker())

        # Second worker should acquire after first releases
        assert results.index("first_released") < results.index("second_acquired")
