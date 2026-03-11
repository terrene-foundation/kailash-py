"""
Tier 1 Unit Tests: ExternalAgentRateLimiter

INTENT-BASED TESTING:
Tests verify INTENT (e.g., "61st request in minute is rejected") not just technical assertions.
Focus on sliding window logic, burst handling, configuration validation.

NO MOCKING: Uses real Redis via fakeredis for accurate behavior testing.
"""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from kaizen.governance import (
    ExternalAgentRateLimiter,
    RateLimitCheckResult,
    RateLimitConfig,
    RateLimitError,
)

# Import fakeredis for unit testing
try:
    import fakeredis.aioredis

    FAKEREDIS_AVAILABLE = True
except ImportError:
    FAKEREDIS_AVAILABLE = False


@pytest.fixture
def fake_redis_limiter():
    """Create rate limiter with fake Redis for unit testing."""
    if not FAKEREDIS_AVAILABLE:
        pytest.skip("fakeredis not installed")

    config = RateLimitConfig(
        requests_per_minute=10,
        requests_per_hour=100,
        requests_per_day=1000,
        burst_multiplier=1.5,
    )

    limiter = ExternalAgentRateLimiter(
        redis_url="redis://localhost:6379/0", config=config
    )

    # Patch Redis client with fakeredis
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    limiter.redis_client = fake_redis
    limiter._initialized = True

    return limiter


@pytest.fixture
def simple_config():
    """Simple rate limit config for testing."""
    return RateLimitConfig(
        requests_per_minute=5,
        requests_per_hour=20,
        requests_per_day=100,
        burst_multiplier=1.5,
    )


# ============================================================================
# Configuration Tests
# ============================================================================


def test_rate_limit_config_defaults():
    """INTENT: Verify default configuration values are reasonable."""
    config = RateLimitConfig()

    assert config.requests_per_minute == 60
    assert config.requests_per_hour == 1000
    assert config.requests_per_day == 10000
    assert config.burst_multiplier == 1.5
    assert config.enable_burst is True
    assert config.fail_open_on_error is True
    assert config.enable_metrics is True


def test_rate_limit_config_validation_positive_limits():
    """INTENT: Verify configuration rejects negative/zero limits."""
    with pytest.raises(ValueError, match="requests_per_minute must be positive"):
        RateLimitConfig(requests_per_minute=0)

    with pytest.raises(ValueError, match="requests_per_hour must be positive"):
        RateLimitConfig(requests_per_hour=-1)

    with pytest.raises(ValueError, match="requests_per_day must be positive"):
        RateLimitConfig(requests_per_day=0)


def test_rate_limit_config_validation_burst_multiplier():
    """INTENT: Verify burst multiplier must be >= 1.0."""
    with pytest.raises(ValueError, match="burst_multiplier must be >= 1.0"):
        RateLimitConfig(burst_multiplier=0.5)

    # Should allow 1.0 (no burst)
    config = RateLimitConfig(burst_multiplier=1.0)
    assert config.burst_multiplier == 1.0


# ============================================================================
# Tier 1 Unit Tests: Rate Limiting Logic
# ============================================================================


@pytest.mark.asyncio
async def test_allows_under_limit_invocations(fake_redis_limiter):
    """
    INTENT: Verify rate limiting allows invocations when under all limits.

    Scenario: User makes 5 requests (limit is 10/minute).
    Expected: All 5 requests are allowed.
    """
    limiter = fake_redis_limiter

    # Make 5 invocations (under limit of 10/minute)
    for i in range(5):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-123"
        )
        assert result.allowed is True, f"Request {i+1} should be allowed"
        assert result.limit_exceeded is None
        assert result.remaining >= 0
        assert result.retry_after_seconds is None

        # Record invocation
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    # Verify metrics
    metrics = limiter.get_metrics()
    assert metrics is not None
    assert metrics.checks_total == 5
    assert metrics.exceeded_total == 0


@pytest.mark.asyncio
async def test_blocks_when_minute_limit_exceeded(fake_redis_limiter):
    """
    INTENT: Verify per-minute rate limiting blocks at exact limit.

    Scenario: Limit is 10/minute with 1.5x burst = 15 effective limit.
              User makes 16 requests.
    Expected: First 15 allowed, 16th blocked with per_minute exceeded.
    """
    limiter = fake_redis_limiter

    # Make 15 invocations (at burst limit)
    for i in range(15):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-123"
        )
        assert result.allowed is True, f"Request {i+1} should be allowed (burst)"
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    # 16th invocation should be blocked
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert result.allowed is False, "16th request should be blocked"
    assert result.limit_exceeded == "per_minute"
    assert result.remaining == 0
    assert result.retry_after_seconds is not None
    assert result.retry_after_seconds > 0

    # Verify metrics
    metrics = limiter.get_metrics()
    assert metrics.exceeded_total == 1
    assert metrics.exceeded_by_limit["minute"] == 1


@pytest.mark.asyncio
async def test_blocks_when_hour_limit_exceeded(fake_redis_limiter):
    """
    INTENT: Verify per-hour rate limiting blocks at exact limit.

    Scenario: Limit is 100/hour with 1.5x burst = 150 effective limit.
              Simulate 150 requests then try 151st.
    Expected: 151st request blocked with per_hour exceeded.
    """
    limiter = fake_redis_limiter

    # Simulate 150 invocations in the hour window
    # (Using bulk addition for performance)
    scope_key = "agent-001:user:user-123"
    now = time.time()

    # Add 150 timestamps to hour window
    async with limiter.redis_client.pipeline(transaction=True) as pipe:
        for i in range(150):
            timestamp = now - i * 10  # Spread over last 1500 seconds
            pipe.zadd(f"rl:ea:{scope_key}:hour", {str(timestamp): timestamp})
        await pipe.execute()

    # 151st invocation should be blocked
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert result.allowed is False, "151st request should be blocked"
    assert result.limit_exceeded == "per_hour"
    assert result.remaining == 0


@pytest.mark.asyncio
async def test_blocks_when_day_limit_exceeded(fake_redis_limiter):
    """
    INTENT: Verify per-day rate limiting blocks at exact limit.

    Scenario: Limit is 1000/day with 1.5x burst = 1500 effective limit.
              Simulate 1500 requests then try 1501st.
    Expected: 1501st request blocked with per_day exceeded.
    """
    limiter = fake_redis_limiter

    # Simulate 1500 invocations in the day window
    scope_key = "agent-001:user:user-123"
    now = time.time()

    # Add 1500 timestamps to day window
    async with limiter.redis_client.pipeline(transaction=True) as pipe:
        for i in range(1500):
            timestamp = now - i * 30  # Spread over last 45000 seconds (~12.5h)
            pipe.zadd(f"rl:ea:{scope_key}:day", {str(timestamp): timestamp})
        await pipe.execute()

    # 1501st invocation should be blocked
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert result.allowed is False, "1501st request should be blocked"
    assert result.limit_exceeded == "per_day"
    assert result.remaining == 0


@pytest.mark.asyncio
async def test_sliding_window_accuracy_prevents_burst_at_boundary(fake_redis_limiter):
    """
    INTENT: Verify sliding window is more accurate than fixed window (no burst allowed at boundary).

    Scenario: Limit is 10/minute with 1.5x burst = 15 effective.
              User makes 15 requests at t=0-50s, then tries at t=55s.
    Expected: Request at t=55s blocked because <60s elapsed since first request.

    Fixed window would allow this (new minute), sliding window correctly blocks it.
    """
    limiter = fake_redis_limiter
    scope_key = "agent-001:user:user-123"
    now = time.time()

    # Simulate 15 invocations between t=0 and t=50 (burst limit)
    async with limiter.redis_client.pipeline(transaction=True) as pipe:
        for i in range(15):
            timestamp = now - 50 + i * 3  # Spread over 45 seconds
            pipe.zadd(f"rl:ea:{scope_key}:minute", {str(timestamp): timestamp})
        await pipe.execute()

    # Try invocation at t=55 (only 5 seconds after last request)
    # Sliding window: All 15 requests are still in 60-second window
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert (
        result.allowed is False
    ), "Sliding window should block request at boundary (all 15 still in window)"
    assert result.limit_exceeded == "per_minute"


@pytest.mark.asyncio
async def test_rate_limit_check_result_includes_correct_remaining(fake_redis_limiter):
    """
    INTENT: Verify remaining field shows correct requests remaining in window.

    Scenario: Limit is 10/minute with 1.5x burst = 15 effective. User makes 5 requests.
    Expected: remaining = 10 (15 - 5 = 10 requests left).
    """
    limiter = fake_redis_limiter

    # Make 5 invocations
    for i in range(5):
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    # Check rate limit
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert result.allowed is True
    # Effective limit = 10 * 1.5 = 15, used = 5, remaining = 10
    assert result.remaining == 10, f"Expected remaining=10, got {result.remaining}"


@pytest.mark.asyncio
async def test_rate_limit_check_result_includes_retry_after_seconds(fake_redis_limiter):
    """
    INTENT: Verify retry_after_seconds calculated from oldest entry in window.

    Scenario: Limit is 10/minute. User makes 15 requests (burst limit).
              Oldest request was 30 seconds ago.
    Expected: retry_after_seconds = 30 (60s window - 30s elapsed = 30s remaining).
    """
    limiter = fake_redis_limiter
    scope_key = "agent-001:user:user-123"
    now = time.time()

    # Simulate 15 invocations, oldest at t=-30 (30 seconds ago)
    async with limiter.redis_client.pipeline(transaction=True) as pipe:
        for i in range(15):
            timestamp = now - 30 + i * 2  # Spread over 30 seconds
            pipe.zadd(f"rl:ea:{scope_key}:minute", {str(timestamp): timestamp})
        await pipe.execute()

    # Check rate limit (should be at limit)
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert result.allowed is False
    assert result.retry_after_seconds is not None
    # Should be approximately 30 seconds (oldest entry expires in ~30s)
    assert (
        28 <= result.retry_after_seconds <= 32
    ), f"Expected retry_after ~30s, got {result.retry_after_seconds}"


# ============================================================================
# Burst Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_burst_allows_temporary_spike(fake_redis_limiter):
    """
    INTENT: Verify burst multiplier allows temporary spike above base limit.

    Scenario: Base limit is 10/minute, burst multiplier is 1.5 (50% extra).
              User makes 12 requests rapidly.
    Expected: All 12 requests allowed (within burst capacity of 15).
    """
    limiter = fake_redis_limiter

    # Make 12 invocations (above base limit of 10, but within burst of 15)
    for i in range(12):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-123"
        )
        assert (
            result.allowed is True
        ), f"Request {i+1} should be allowed (burst capacity)"
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    # Verify all 12 allowed
    metrics = limiter.get_metrics()
    assert metrics.exceeded_total == 0


@pytest.mark.asyncio
async def test_burst_disabled_enforces_base_limit(simple_config):
    """
    INTENT: Verify disabling burst enforces strict base limit.

    Scenario: Base limit is 5/minute, burst disabled (multiplier=1.0).
              User makes 6 requests.
    Expected: First 5 allowed, 6th blocked.
    """
    if not FAKEREDIS_AVAILABLE:
        pytest.skip("fakeredis not installed")

    # Disable burst
    simple_config.enable_burst = False
    simple_config.burst_multiplier = 1.0

    limiter = ExternalAgentRateLimiter(
        redis_url="redis://localhost:6379/0", config=simple_config
    )

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    limiter.redis_client = fake_redis
    limiter._initialized = True

    # Make 5 invocations (at limit)
    for i in range(5):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-123"
        )
        assert result.allowed is True, f"Request {i+1} should be allowed"
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    # 6th invocation should be blocked (no burst)
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert result.allowed is False, "6th request should be blocked (burst disabled)"
    assert result.limit_exceeded == "per_minute"

    await fake_redis.aclose()


# ============================================================================
# Graceful Degradation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_fail_open_when_redis_unavailable(simple_config):
    """
    INTENT: Verify fail-open behavior when Redis connection fails.

    Scenario: Redis unavailable, fail_open_on_error=True.
    Expected: Requests allowed without rate limiting (fail-open).
    """
    limiter = ExternalAgentRateLimiter(
        redis_url="redis://localhost:6379/0", config=simple_config
    )

    # Don't initialize Redis (simulate unavailable)
    limiter._initialized = False

    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")

    # Should allow request (fail-open)
    assert result.allowed is True
    assert result.remaining == -1  # Unknown
    assert result.reset_time is None

    # Verify metrics tracked fail-open
    metrics = limiter.get_metrics()
    assert metrics.fail_open_total == 1


@pytest.mark.asyncio
async def test_fail_closed_when_redis_unavailable_and_fail_open_disabled():
    """
    INTENT: Verify fail-closed behavior when Redis unavailable and fail_open_on_error=False.

    Scenario: Redis unavailable, fail_open_on_error=False.
    Expected: RateLimitError raised.
    """
    config = RateLimitConfig(fail_open_on_error=False)
    limiter = ExternalAgentRateLimiter(
        redis_url="redis://localhost:6379/0", config=config
    )

    # Mock Redis client to raise exception
    limiter._initialized = True
    limiter.redis_client = AsyncMock()
    limiter.redis_client.pipeline.side_effect = Exception("Redis connection failed")

    with pytest.raises(RateLimitError, match="Rate limit check failed"):
        await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")


# ============================================================================
# Scope Key Tests (Per-User, Per-Team, Per-Org)
# ============================================================================


@pytest.mark.asyncio
async def test_per_user_rate_limiting_isolates_users(fake_redis_limiter):
    """
    INTENT: Verify per-user rate limiting prevents one user from exhausting shared agent quota.

    Scenario: User A and User B both use same agent, each has 5/minute limit.
    Expected: Both users can make 5 requests independently.
    """
    limiter = fake_redis_limiter

    # User A makes 5 invocations
    for i in range(5):
        result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-a")
        assert result.allowed is True
        await limiter.record_invocation(agent_id="agent-001", user_id="user-a")

    # User B makes 5 invocations (separate quota)
    for i in range(5):
        result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-b")
        assert result.allowed is True
        await limiter.record_invocation(agent_id="agent-001", user_id="user-b")

    # Both users should now be at their limits
    result_a = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-a")
    result_b = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-b")

    # Effective limit is 10 * 1.5 = 15, used = 5, so should still be allowed
    # Let's exhaust their quotas
    for i in range(10):  # 5 + 10 = 15 (burst limit)
        await limiter.record_invocation(agent_id="agent-001", user_id="user-a")
        await limiter.record_invocation(agent_id="agent-001", user_id="user-b")

    # Now both should be blocked
    result_a = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-a")
    result_b = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-b")

    assert result_a.allowed is False, "User A should be blocked"
    assert result_b.allowed is False, "User B should be blocked"


@pytest.mark.asyncio
async def test_team_scope_overrides_user_scope(fake_redis_limiter):
    """
    INTENT: Verify team-level rate limiting takes precedence over user-level.

    Scenario: Rate limit applied at team level, not individual users.
    Expected: All team members share same quota.
    """
    limiter = fake_redis_limiter

    # Team members share team quota
    for i in range(7):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-a", team_id="team-alpha"
        )
        assert result.allowed is True
        await limiter.record_invocation(
            agent_id="agent-001", user_id="user-a", team_id="team-alpha"
        )

    # Another team member tries to use agent (same team quota)
    for i in range(8):  # 7 + 8 = 15 (burst limit)
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-b", team_id="team-alpha"
        )
        assert result.allowed is True
        await limiter.record_invocation(
            agent_id="agent-001", user_id="user-b", team_id="team-alpha"
        )

    # Next request should be blocked (team quota exhausted)
    result = await limiter.check_rate_limit(
        agent_id="agent-001", user_id="user-c", team_id="team-alpha"
    )
    assert result.allowed is False, "Team quota should be exhausted"
    assert result.limit_exceeded == "per_minute"


# ============================================================================
# Metrics Tests
# ============================================================================


@pytest.mark.asyncio
async def test_metrics_tracking_enabled(fake_redis_limiter):
    """
    INTENT: Verify metrics are tracked when enabled.

    Scenario: Make requests, some allowed, some blocked.
    Expected: Metrics reflect accurate counts.
    """
    limiter = fake_redis_limiter

    # Make 15 allowed requests (at burst limit of 10 * 1.5 = 15)
    for i in range(15):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-123"
        )
        assert result.allowed is True, f"Request {i+1} should be allowed (within burst)"
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    # Make 5 more requests (will exceed burst limit)
    for i in range(5):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-123"
        )
        assert (
            result.allowed is False
        ), f"Request {i+16} should be blocked (burst exceeded)"

    metrics = limiter.get_metrics()
    assert metrics is not None
    assert metrics.checks_total == 20  # 15 + 5
    assert metrics.exceeded_total == 5  # Last 5 exceeded
    assert metrics.exceeded_by_limit["minute"] == 5


@pytest.mark.asyncio
async def test_metrics_tracking_disabled():
    """
    INTENT: Verify metrics are not tracked when disabled.

    Scenario: Disable metrics in config.
    Expected: get_metrics() returns None.
    """
    if not FAKEREDIS_AVAILABLE:
        pytest.skip("fakeredis not installed")

    config = RateLimitConfig(enable_metrics=False)
    limiter = ExternalAgentRateLimiter(
        redis_url="redis://localhost:6379/0", config=config
    )

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    limiter.redis_client = fake_redis
    limiter._initialized = True

    await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")

    metrics = limiter.get_metrics()
    assert metrics is None

    await fake_redis.aclose()


# ============================================================================
# Error Handling Tests
# ============================================================================


def test_rate_limiter_requires_redis_package():
    """
    INTENT: Verify ImportError raised when redis package not installed.

    Scenario: Mock redis import failure.
    Expected: ImportError with helpful message.
    """
    with patch("kaizen.governance.rate_limiter.REDIS_AVAILABLE", False):
        with pytest.raises(ImportError, match="redis package required"):
            ExternalAgentRateLimiter()


# ============================================================================
# Performance Baseline Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rate_limit_check_performance_baseline(fake_redis_limiter):
    """
    INTENT: Verify rate limit checks complete quickly (baseline for integration tests).

    Scenario: Single rate limit check.
    Expected: Completes in <50ms (unit test baseline, integration target <10ms with real Redis).
    """
    limiter = fake_redis_limiter

    start = time.time()
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    duration = time.time() - start

    assert result.allowed is True
    assert (
        duration < 0.05
    ), f"Rate limit check took {duration*1000:.2f}ms (expected <50ms)"
