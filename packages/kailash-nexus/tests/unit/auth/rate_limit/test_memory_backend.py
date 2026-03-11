"""Unit tests for InMemoryBackend (TODO-310D).

Tier 1 tests - mocking allowed.
Tests token bucket algorithm, atomic operations, thread safety, and reset.
"""

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from nexus.auth.rate_limit.backends.base import RateLimitBackend
from nexus.auth.rate_limit.backends.memory import InMemoryBackend

# =============================================================================
# Tests: Backend Interface
# =============================================================================


class TestInMemoryBackendInterface:
    """Test InMemoryBackend implements RateLimitBackend."""

    def test_is_rate_limit_backend(self):
        """InMemoryBackend is a RateLimitBackend."""
        backend = InMemoryBackend()
        assert isinstance(backend, RateLimitBackend)

    def test_init_default_burst_multiplier(self):
        """Default burst_multiplier is 1.0."""
        backend = InMemoryBackend()
        assert backend._burst_multiplier == 1.0

    def test_init_custom_burst_multiplier(self):
        """Custom burst_multiplier is stored."""
        backend = InMemoryBackend(burst_multiplier=1.5)
        assert backend._burst_multiplier == 1.5


# =============================================================================
# Tests: check() Method
# =============================================================================


class TestInMemoryBackendCheck:
    """Test check() method (token bucket algorithm)."""

    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        """Request under limit is allowed."""
        backend = InMemoryBackend()
        allowed, remaining, reset_at = await backend.check("user-1", limit=10)
        assert allowed is True
        # First check gets ~10 tokens (from refill since "last update")
        # remaining should be >= 0
        assert remaining >= 0

    @pytest.mark.asyncio
    async def test_returns_remaining_count(self):
        """Remaining count decreases with each check+record."""
        backend = InMemoryBackend()

        # First check fills bucket, then check
        allowed, remaining1, _ = await backend.check("user-1", limit=10)
        assert allowed is True
        await backend.record("user-1")

        allowed, remaining2, _ = await backend.check("user-1", limit=10)
        assert allowed is True
        assert remaining2 < remaining1

    @pytest.mark.asyncio
    async def test_returns_reset_at_in_future(self):
        """reset_at is in the future."""
        backend = InMemoryBackend()
        _, _, reset_at = await backend.check("user-1", limit=10)
        assert reset_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_blocks_over_limit(self):
        """Requests over limit are blocked."""
        backend = InMemoryBackend()

        # Exhaust limit with check_and_record for atomicity
        for _ in range(10):
            allowed, _, _ = await backend.check_and_record(
                "user-1", limit=10, window_seconds=60
            )

        # Next request should be blocked
        allowed, remaining, _ = await backend.check("user-1", limit=10)
        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_different_identifiers_independent(self):
        """Different identifiers have independent limits."""
        backend = InMemoryBackend()

        # Exhaust user-1
        for _ in range(10):
            await backend.check_and_record("user-1", limit=10)

        # user-2 should still be allowed
        allowed, _, _ = await backend.check("user-2", limit=10)
        assert allowed is True


# =============================================================================
# Tests: check_and_record() Atomic Method
# =============================================================================


class TestInMemoryBackendCheckAndRecord:
    """Test atomic check_and_record() method."""

    @pytest.mark.asyncio
    async def test_atomic_allows_under_limit(self):
        """Atomic check-and-record allows under limit."""
        backend = InMemoryBackend()
        allowed, remaining, reset_at = await backend.check_and_record(
            "user-1", limit=10
        )
        assert allowed is True
        assert remaining >= 0
        assert reset_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_atomic_blocks_when_exhausted(self):
        """Atomic check-and-record blocks when limit exhausted."""
        backend = InMemoryBackend()

        for _ in range(10):
            await backend.check_and_record("user-1", limit=10)

        allowed, remaining, _ = await backend.check_and_record("user-1", limit=10)
        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_atomic_remaining_decreases(self):
        """Remaining count decreases with each atomic call."""
        backend = InMemoryBackend()

        results = []
        for _ in range(5):
            allowed, remaining, _ = await backend.check_and_record("user-1", limit=10)
            results.append(remaining)

        # Remaining should be monotonically decreasing
        for i in range(1, len(results)):
            assert results[i] <= results[i - 1]


# =============================================================================
# Tests: Token Refill
# =============================================================================


class TestInMemoryBackendRefill:
    """Test token refill over time."""

    @pytest.mark.asyncio
    async def test_tokens_refill_over_time(self):
        """Tokens refill after time passes."""
        backend = InMemoryBackend()

        # Exhaust limit
        for _ in range(10):
            await backend.check_and_record("user-1", limit=10, window_seconds=60)

        # Verify blocked
        allowed, _, _ = await backend.check("user-1", limit=10, window_seconds=60)
        assert allowed is False

        # Simulate time passing by directly manipulating bucket
        with backend._lock:
            tokens, _ = backend._buckets["user-1"]
            # Set last_update to 30 seconds ago (half the window)
            from datetime import timedelta

            past = datetime.now(timezone.utc) - timedelta(seconds=30)
            backend._buckets["user-1"] = (tokens, past)

        # Now tokens should have refilled partially
        allowed, remaining, _ = await backend.check(
            "user-1", limit=10, window_seconds=60
        )
        assert allowed is True
        assert remaining >= 0

    @pytest.mark.asyncio
    async def test_burst_multiplier_increases_capacity(self):
        """Burst multiplier increases bucket capacity."""
        backend = InMemoryBackend(burst_multiplier=1.5)

        # With 1.5x multiplier, limit of 10 gives capacity of 15
        count = 0
        for _ in range(20):
            allowed, _, _ = await backend.check_and_record(
                "user-1", limit=10, window_seconds=60
            )
            if allowed:
                count += 1
            else:
                break

        # Should allow more than 10 but not more than 15
        assert count > 10
        assert count <= 15


# =============================================================================
# Tests: reset() Method
# =============================================================================


class TestInMemoryBackendReset:
    """Test reset() method."""

    @pytest.mark.asyncio
    async def test_reset_clears_identifier(self):
        """Reset removes rate limit state for identifier."""
        backend = InMemoryBackend()

        # Exhaust limit
        for _ in range(10):
            await backend.check_and_record("user-1", limit=10)

        # Verify blocked
        allowed, _, _ = await backend.check("user-1", limit=10)
        assert allowed is False

        # Reset
        await backend.reset("user-1")

        # Should be allowed again
        allowed, _, _ = await backend.check("user-1", limit=10)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_reset_nonexistent_is_noop(self):
        """Reset on nonexistent identifier does nothing."""
        backend = InMemoryBackend()
        await backend.reset("nonexistent")  # Should not raise

    @pytest.mark.asyncio
    async def test_reset_only_affects_target(self):
        """Reset only clears the specified identifier."""
        backend = InMemoryBackend()

        # Exhaust both
        for _ in range(10):
            await backend.check_and_record("user-1", limit=10)
            await backend.check_and_record("user-2", limit=10)

        # Reset only user-1
        await backend.reset("user-1")

        allowed1, _, _ = await backend.check("user-1", limit=10)
        allowed2, _, _ = await backend.check("user-2", limit=10)
        assert allowed1 is True
        assert allowed2 is False


# =============================================================================
# Tests: close() Method
# =============================================================================


class TestInMemoryBackendClose:
    """Test close() method."""

    @pytest.mark.asyncio
    async def test_close_is_noop(self):
        """Close does nothing for in-memory backend."""
        backend = InMemoryBackend()
        await backend.close()  # Should not raise


# =============================================================================
# Tests: Thread Safety
# =============================================================================


class TestInMemoryBackendThreadSafety:
    """Test thread safety with concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_check_and_record(self):
        """Concurrent check_and_record operations are safe."""
        backend = InMemoryBackend()

        # Run many concurrent checks
        tasks = [
            backend.check_and_record("user-1", limit=100, window_seconds=60)
            for _ in range(50)
        ]
        results = await asyncio.gather(*tasks)

        # Count allowed requests
        allowed_count = sum(1 for allowed, _, _ in results if allowed)
        blocked_count = sum(1 for allowed, _, _ in results if not allowed)

        # All 50 should be allowed with limit=100
        assert allowed_count == 50
        assert blocked_count == 0

    @pytest.mark.asyncio
    async def test_concurrent_over_limit(self):
        """Concurrent requests over limit block correctly."""
        backend = InMemoryBackend()

        # Send 20 requests with limit of 10
        tasks = [
            backend.check_and_record("user-1", limit=10, window_seconds=60)
            for _ in range(20)
        ]
        results = await asyncio.gather(*tasks)

        allowed_count = sum(1 for allowed, _, _ in results if allowed)
        blocked_count = sum(1 for allowed, _, _ in results if not allowed)

        # Exactly 10 should be allowed
        assert allowed_count == 10
        assert blocked_count == 10
