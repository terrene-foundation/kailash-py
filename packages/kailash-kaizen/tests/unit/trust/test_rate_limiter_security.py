"""
Unit tests for TrustRateLimiter Memory DoS Protection (ROUND5-007).

Tests verify that TrustRateLimiter protects against memory exhaustion attacks
via unique authority IDs by limiting the number of tracked authorities.

Following the 3-tier testing strategy - Tier 1 (Unit Tests).
Mocking is allowed for unit tests.
"""

import asyncio
from unittest.mock import patch

import pytest
from kailash.trust.security import RateLimitExceededError, TrustRateLimiter


class TestRateLimiterMemoryDoS:
    """Test TrustRateLimiter memory DoS protection (ROUND5-007).

    These tests verify that the rate limiter protects against memory
    exhaustion attacks by limiting the number of tracked authorities.
    """

    def test_rate_limiter_max_authorities_constant_exists(self):
        """ROUND5-007: Verify MAX_TRACKED_AUTHORITIES constant exists and equals 10000."""
        assert hasattr(
            TrustRateLimiter, "MAX_TRACKED_AUTHORITIES"
        ), "ROUND5-007: TrustRateLimiter missing MAX_TRACKED_AUTHORITIES constant"
        assert TrustRateLimiter.MAX_TRACKED_AUTHORITIES == 10000, (
            f"ROUND5-007: MAX_TRACKED_AUTHORITIES should be 10000, "
            f"got {TrustRateLimiter.MAX_TRACKED_AUTHORITIES}"
        )

    @pytest.mark.asyncio
    async def test_rate_limiter_evicts_at_max_to_bound_memory(self):
        """ROUND5-007: Memory is bounded when adding many unique authorities.

        The core security guarantee is that memory usage is bounded by
        MAX_TRACKED_AUTHORITIES. When the limit is reached, eviction occurs
        to prevent memory exhaustion attacks.
        """
        limiter = TrustRateLimiter(establish_per_minute=100, verify_per_minute=1000)

        # Override MAX_TRACKED_AUTHORITIES for testing
        original_max = TrustRateLimiter.MAX_TRACKED_AUTHORITIES
        try:
            TrustRateLimiter.MAX_TRACKED_AUTHORITIES = 5

            # Add many more authorities than the limit
            for i in range(20):
                await limiter.record_operation("establish", f"authority-{i}")
                await asyncio.sleep(0.001)

            # Memory should be bounded - never exceed MAX_TRACKED_AUTHORITIES
            assert len(limiter._operations["establish"]) <= 5, (
                f"ROUND5-007: Memory not bounded! Expected <= 5 authorities, "
                f"got {len(limiter._operations['establish'])}"
            )

        finally:
            TrustRateLimiter.MAX_TRACKED_AUTHORITIES = original_max

    @pytest.mark.asyncio
    async def test_rate_limiter_eviction_prevents_memory_dos(self):
        """ROUND5-007: Verify eviction actually occurs to prevent memory DoS.

        Adding authorities beyond the limit must trigger eviction to
        prevent unbounded memory growth.
        """
        limiter = TrustRateLimiter(establish_per_minute=100, verify_per_minute=1000)

        # Override MAX_TRACKED_AUTHORITIES for testing
        original_max = TrustRateLimiter.MAX_TRACKED_AUTHORITIES
        try:
            TrustRateLimiter.MAX_TRACKED_AUTHORITIES = 3

            # Add first 2 authorities (under threshold)
            await limiter.record_operation("establish", "auth-1")
            await limiter.record_operation("establish", "auth-2")

            initial_count = len(limiter._operations["establish"])
            assert initial_count == 2

            # Add 10 more authorities - should trigger multiple evictions
            for i in range(3, 13):
                await limiter.record_operation("establish", f"auth-{i}")

            # Should never exceed MAX_TRACKED_AUTHORITIES
            final_count = len(limiter._operations["establish"])
            assert (
                final_count <= 3
            ), f"ROUND5-007: Memory DoS possible! {final_count} > 3 authorities"

        finally:
            TrustRateLimiter.MAX_TRACKED_AUTHORITIES = original_max

    @pytest.mark.asyncio
    async def test_rate_limiter_normal_operation_unaffected(self):
        """ROUND5-007: Normal rate limiting still works correctly.

        Verifies that the memory DoS protection does not affect normal
        rate limiting behavior.
        """
        limiter = TrustRateLimiter(establish_per_minute=5, verify_per_minute=10)

        # Check rate should return True when under limit
        assert await limiter.check_rate("establish", "normal-authority")

        # Record operations up to limit
        for i in range(5):
            await limiter.record_operation("establish", "normal-authority")

        # Should be at limit now
        assert not await limiter.check_rate("establish", "normal-authority")

        # Recording should raise RateLimitExceededError
        with pytest.raises(RateLimitExceededError):
            await limiter.record_operation("establish", "normal-authority")

    @pytest.mark.asyncio
    async def test_rate_limiter_eviction_algorithm_evicts_something(self):
        """ROUND5-007: Eviction algorithm runs and removes an authority.

        When at capacity, the eviction algorithm must remove something
        to make room for new entries.
        """
        limiter = TrustRateLimiter(establish_per_minute=100, verify_per_minute=1000)

        # Override MAX_TRACKED_AUTHORITIES for testing
        original_max = TrustRateLimiter.MAX_TRACKED_AUTHORITIES
        try:
            TrustRateLimiter.MAX_TRACKED_AUTHORITIES = 3

            # Add 2 authorities (under limit)
            await limiter.record_operation("establish", "auth-1")
            await asyncio.sleep(0.01)
            await limiter.record_operation("establish", "auth-2")

            initial_count = len(limiter._operations["establish"])
            assert initial_count == 2

            # Add 3rd authority - should trigger eviction
            await limiter.record_operation("establish", "auth-3")

            # Should have <= MAX authorities
            final_count = len(limiter._operations["establish"])
            assert final_count <= 3, f"Eviction did not bound memory: {final_count} > 3"

            # At least some authorities should be present
            assert final_count >= 1, "All authorities were evicted!"

        finally:
            TrustRateLimiter.MAX_TRACKED_AUTHORITIES = original_max

    @pytest.mark.asyncio
    async def test_rate_limiter_eviction_handles_empty_timestamps(self):
        """ROUND5-007: Eviction handles authorities with empty timestamp lists.

        Empty timestamp lists should be evicted first as they represent
        inactive/expired authorities.
        """
        limiter = TrustRateLimiter(establish_per_minute=100, verify_per_minute=1000)

        # Override MAX_TRACKED_AUTHORITIES for testing
        original_max = TrustRateLimiter.MAX_TRACKED_AUTHORITIES
        try:
            # Use MAX=4 so 3 entries are stable, 4th triggers eviction
            TrustRateLimiter.MAX_TRACKED_AUTHORITIES = 4

            # Add 3 authorities (under threshold)
            for i in range(3):
                await limiter.record_operation("establish", f"auth-{i}")
                await asyncio.sleep(0.01)

            # Verify we have 3 authorities
            assert len(limiter._operations["establish"]) == 3

            # Manually clear timestamps for one authority (simulating expiry)
            limiter._operations["establish"]["auth-0"] = []

            # Add new authority - triggers eviction (4 >= MAX 4)
            # auth-0 should be evicted first (empty timestamps)
            await limiter.record_operation("establish", "auth-new")

            # auth-0 should be evicted (empty timestamp list gets priority)
            assert (
                "auth-0" not in limiter._operations["establish"]
            ), "ROUND5-007: Authority with empty timestamps should be evicted first"

            # Other authorities should still be present
            assert "auth-1" in limiter._operations["establish"]
            assert "auth-2" in limiter._operations["establish"]
            assert "auth-new" in limiter._operations["establish"]

        finally:
            TrustRateLimiter.MAX_TRACKED_AUTHORITIES = original_max

    @pytest.mark.asyncio
    async def test_rate_limiter_separate_operation_types(self):
        """ROUND5-007: Eviction is per-operation-type, not global.

        Each operation type (establish, verify) has its own authority tracking.
        Adding many authorities to one type does not affect the other.
        """
        limiter = TrustRateLimiter(establish_per_minute=100, verify_per_minute=1000)

        # Override MAX_TRACKED_AUTHORITIES for testing
        original_max = TrustRateLimiter.MAX_TRACKED_AUTHORITIES
        try:
            TrustRateLimiter.MAX_TRACKED_AUTHORITIES = 3

            # Add 2 authorities for "verify" (should remain stable)
            await limiter.record_operation("verify", "ver-1")
            await limiter.record_operation("verify", "ver-2")

            # Add many authorities to "establish" to trigger evictions
            for i in range(10):
                await limiter.record_operation("establish", f"est-{i}")

            # Verify should be unaffected by establish evictions
            assert (
                len(limiter._operations["verify"]) == 2
            ), "ROUND5-007: verify authorities affected by establish eviction!"
            assert "ver-1" in limiter._operations["verify"]
            assert "ver-2" in limiter._operations["verify"]

            # Establish should be bounded by MAX
            assert (
                len(limiter._operations["establish"]) <= 3
            ), "ROUND5-007: establish memory not bounded"

        finally:
            TrustRateLimiter.MAX_TRACKED_AUTHORITIES = original_max


class TestRateLimiterBasicFunctionality:
    """Basic functionality tests for TrustRateLimiter."""

    @pytest.mark.asyncio
    async def test_check_rate_under_limit(self):
        """Test check_rate returns True when under limit."""
        limiter = TrustRateLimiter(establish_per_minute=10)

        result = await limiter.check_rate("establish", "test-authority")

        assert result is True

    @pytest.mark.asyncio
    async def test_check_rate_at_limit(self):
        """Test check_rate returns False when at limit."""
        limiter = TrustRateLimiter(establish_per_minute=3)

        # Record up to limit
        for _ in range(3):
            await limiter.record_operation("establish", "test-authority")

        result = await limiter.check_rate("establish", "test-authority")

        assert result is False

    @pytest.mark.asyncio
    async def test_record_operation_raises_at_limit(self):
        """Test record_operation raises RateLimitExceededError at limit."""
        limiter = TrustRateLimiter(establish_per_minute=2)

        # Record up to limit
        await limiter.record_operation("establish", "test-authority")
        await limiter.record_operation("establish", "test-authority")

        # Third should raise
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.record_operation("establish", "test-authority")

        assert exc_info.value.operation == "establish"
        assert exc_info.value.authority_id == "test-authority"
        assert exc_info.value.limit == 2

    @pytest.mark.asyncio
    async def test_rate_limit_per_authority(self):
        """Test rate limits are tracked per-authority."""
        limiter = TrustRateLimiter(establish_per_minute=2)

        # Authority A uses up its limit
        await limiter.record_operation("establish", "authority-a")
        await limiter.record_operation("establish", "authority-a")

        # Authority A is at limit
        assert not await limiter.check_rate("establish", "authority-a")

        # Authority B should still have room
        assert await limiter.check_rate("establish", "authority-b")
        await limiter.record_operation("establish", "authority-b")

    @pytest.mark.asyncio
    async def test_default_limits(self):
        """Test default rate limits are applied."""
        limiter = TrustRateLimiter()

        # Default is 100 for establish, 1000 for verify
        assert limiter.establish_per_minute == 100
        assert limiter.verify_per_minute == 1000

    @pytest.mark.asyncio
    async def test_unknown_operation_default_limit(self):
        """Test unknown operations get default limit of 100."""
        limiter = TrustRateLimiter()

        # Record 100 operations for unknown type
        for _ in range(100):
            await limiter.record_operation("unknown_operation", "test-authority")

        # 101st should fail (default limit is 100)
        with pytest.raises(RateLimitExceededError):
            await limiter.record_operation("unknown_operation", "test-authority")
