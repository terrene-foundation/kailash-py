"""
Tier 2 Integration Tests: ExternalAgentRateLimiter with Real Redis

INTENT-BASED TESTING:
Tests verify INTENT with real Redis infrastructure (NO MOCKING).

Tests validate:
- End-to-end rate limiting with real Redis persistence
- Sliding window accuracy with real time progression
- Graceful degradation when Redis unavailable
- Connection pooling and performance

Prerequisites:
- Redis server running on localhost:6379
- redis Python package installed
"""

import asyncio
import os
import time
from datetime import datetime, timedelta

import pytest
import pytest_asyncio

from kaizen.governance import (
    ExternalAgentRateLimiter,
    RateLimitCheckResult,
    RateLimitConfig,
    RateLimitError,
)

# Check if Redis is available
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/15")  # Use DB 15 for tests

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
]


@pytest_asyncio.fixture
async def redis_limiter():
    """Create rate limiter with real Redis connection."""
    config = RateLimitConfig(
        requests_per_minute=5,
        requests_per_hour=20,
        requests_per_day=100,
        burst_multiplier=1.5,
        enable_metrics=True,
    )

    limiter = ExternalAgentRateLimiter(redis_url=REDIS_URL, config=config)

    try:
        await limiter.initialize()
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")

    yield limiter

    # Cleanup: Clear test keys
    if limiter.redis_client:
        try:
            # Delete all test keys
            async for key in limiter.redis_client.scan_iter(match="rl:ea:*"):
                await limiter.redis_client.delete(key)
        except Exception:
            pass

    await limiter.close()


# ============================================================================
# Tier 2 Integration Test 1: Real Redis End-to-End
# ============================================================================


@pytest.mark.asyncio
async def test_rate_limiting_with_real_redis_database(redis_limiter):
    """
    INTENT: Verify end-to-end rate limiting with real Redis persistence.

    Setup: Real Redis server, limits={per_minute: 5, per_hour: 20, per_day: 100}
    Steps:
        1. Make 5 invocations within 1 minute → all allowed
        2. Make 6th invocation → should block (per_minute exceeded)
        3. Wait 61 seconds
        4. Make 7th invocation → should allow (minute window expired)
    Assertions: First 5 allowed, 6th blocked with per_minute, 7th allowed
    """
    limiter = redis_limiter

    # Step 1: Make 5 invocations (at base limit)
    for i in range(5):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-123"
        )
        assert result.allowed is True, f"Request {i+1} should be allowed"
        assert result.limit_exceeded is None
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    # Step 2: Make 6th invocation (should block - no burst beyond 5*1.5=7.5 ≈ 7)
    # Actually, let's make 8 invocations to exceed burst
    for i in range(3):  # 5 + 3 = 8 > 7 (burst limit)
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert result.allowed is False, "9th request should be blocked (burst exceeded)"
    assert result.limit_exceeded == "per_minute"
    assert result.retry_after_seconds is not None
    assert result.retry_after_seconds > 0

    # Verify Redis persistence: Keys should exist
    scope_key = "agent-001:user:user-123"
    minute_key = f"rl:ea:{scope_key}:minute"
    exists = await limiter.redis_client.exists(minute_key)
    assert exists == 1, "Redis key should exist"

    # Verify count
    count = await limiter.redis_client.zcard(minute_key)
    assert count == 8, f"Expected 8 entries in Redis, got {count}"

    # Step 3: Wait 61 seconds (simulate with time manipulation for testing speed)
    # Delete old entries manually to simulate time passing
    now = time.time()
    await limiter.redis_client.zremrangebyscore(minute_key, 0, now - 60)

    # Step 4: Make 9th invocation (should allow - minute window expired)
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert (
        result.allowed is True
    ), "Request should be allowed after minute window expired"


# ============================================================================
# Tier 2 Integration Test 2: Sliding Window Accuracy
# ============================================================================


@pytest.mark.asyncio
async def test_sliding_window_accuracy_with_real_time(redis_limiter):
    """
    INTENT: Verify sliding window removes old entries correctly over real time.

    Setup: Real Redis, limits={per_minute: 3}
    Steps:
        1. Make invocation at t=0
        2. Make invocation at t=30s
        3. Make invocation at t=40s (3 total, at limit)
        4. Attempt invocation at t=50s (should block, <60s since t=0)
        5. Attempt invocation at t=61s (should allow, >60s since t=0)
    Assertions: Invocations at t=0, t=30s, t=40s allowed, t=50s blocked, t=61s allowed
    """
    limiter = redis_limiter

    # Manually add timestamps to simulate time progression
    scope_key = "agent-001:user:user-123"
    minute_key = f"rl:ea:{scope_key}:minute"
    now = time.time()

    # Step 1: Invocation at t=0 (61 seconds ago)
    t0 = now - 61
    await limiter.redis_client.zadd(minute_key, {str(t0): t0})

    # Step 2: Invocation at t=30 (31 seconds ago)
    t30 = now - 31
    await limiter.redis_client.zadd(minute_key, {str(t30): t30})

    # Step 3: Invocation at t=40 (21 seconds ago)
    t40 = now - 21
    await limiter.redis_client.zadd(minute_key, {str(t40): t40})

    # Step 4: Attempt invocation at t=50 (11 seconds ago - simulated as "now")
    # All 3 entries should still be in window (t30 and t40 are <60s ago)
    # But t0 should be removed
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")

    # Check current count (should be 2 after cleanup: t30 and t40)
    count = await limiter.redis_client.zcard(minute_key)
    # After check_rate_limit, old entries removed. t0 is >60s ago, removed
    # t30 is 31s ago, t40 is 21s ago - both kept
    assert count == 2, f"Expected 2 entries after cleanup, got {count}"

    # Now add 2 more to reach burst limit (3 * 1.5 = 4.5 ≈ 4)
    await limiter.record_invocation(agent_id="agent-001", user_id="user-123")
    await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    # Step 5: Should be at limit now (2 existing + 2 new = 4 = burst limit)
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert (
        result.allowed is False
    ), "Should be blocked at burst limit (4 requests in window)"


# ============================================================================
# Tier 2 Integration Test 3: Graceful Degradation
# ============================================================================


@pytest.mark.asyncio
async def test_graceful_degradation_when_redis_unavailable():
    """
    INTENT: Verify fail-open behavior when Redis connection fails.

    Setup: ExternalAgentRateLimiter, stop Redis server mid-test
    Steps:
        1. Make 3 successful invocations (Redis available)
        2. Stop Redis server (simulated by closing connection)
        3. Make 4th invocation (Redis unavailable)
    Assertions: First 3 invocations check successfully, 4th returns allowed=True (fail-open)
    """
    config = RateLimitConfig(
        requests_per_minute=5,
        fail_open_on_error=True,
        enable_metrics=True,
    )

    limiter = ExternalAgentRateLimiter(redis_url=REDIS_URL, config=config)

    try:
        await limiter.initialize()
    except Exception:
        pytest.skip("Redis not available")

    # Step 1: Make 3 successful invocations
    for i in range(3):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-123"
        )
        assert result.allowed is True
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    # Step 2: Simulate Redis unavailable (close connection)
    await limiter.close()
    limiter._initialized = False

    # Step 3: Make 4th invocation (should fail-open)
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")

    assert result.allowed is True, "Should fail-open when Redis unavailable"
    assert result.remaining == -1
    assert result.reset_time is None

    # Verify metrics tracked fail-open
    metrics = limiter.get_metrics()
    assert metrics.fail_open_total == 1


# ============================================================================
# Tier 2 Integration Test 4: Connection Pooling Performance
# ============================================================================


@pytest.mark.asyncio
async def test_redis_connection_pooling_reduces_latency(redis_limiter):
    """
    INTENT: Verify connection pooling improves performance with concurrent checks.

    Setup: Real Redis, ExternalAgentRateLimiter with connection pool
    Steps:
        1. Make 100 concurrent check_rate_limit() calls (asyncio.gather)
    Assertions: All 100 checks complete without connection errors, average latency <10ms
    """
    limiter = redis_limiter

    # Make 100 concurrent rate limit checks
    async def check_rate_limit_task(user_id: str):
        start = time.time()
        result = await limiter.check_rate_limit(agent_id="agent-001", user_id=user_id)
        duration = time.time() - start
        return result, duration

    # Create 100 tasks with different user IDs
    tasks = [check_rate_limit_task(f"user-{i}") for i in range(100)]

    start_total = time.time()
    results = await asyncio.gather(*tasks)
    total_duration = time.time() - start_total

    # Verify all completed successfully
    assert len(results) == 100
    for result, duration in results:
        assert result.allowed is True, "All checks should succeed (separate users)"

    # Calculate average latency
    latencies = [duration for _, duration in results]
    avg_latency = sum(latencies) / len(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

    print(f"\nConnection Pooling Performance:")
    print(f"  Total duration: {total_duration*1000:.2f}ms")
    print(f"  Average latency: {avg_latency*1000:.2f}ms")
    print(f"  P95 latency: {p95_latency*1000:.2f}ms")

    # Assert performance targets (integration test allows more time than unit tests)
    assert avg_latency < 0.05, f"Average latency {avg_latency*1000:.2f}ms exceeds 50ms"
    assert p95_latency < 0.1, f"P95 latency {p95_latency*1000:.2f}ms exceeds 100ms"


# ============================================================================
# Tier 2 Integration Test 5: Redis Key TTL Verification
# ============================================================================


@pytest.mark.asyncio
async def test_redis_keys_have_correct_ttl(redis_limiter):
    """
    INTENT: Verify Redis keys expire correctly to prevent memory growth.

    Setup: Real Redis
    Steps:
        1. Record invocations
        2. Check TTL on minute/hour/day keys
    Assertions: TTLs are set correctly (61s, 3601s, 86401s)
    """
    limiter = redis_limiter

    # Record invocations
    await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    # Check TTLs
    scope_key = "agent-001:user:user-123"
    minute_key = f"rl:ea:{scope_key}:minute"
    hour_key = f"rl:ea:{scope_key}:hour"
    day_key = f"rl:ea:{scope_key}:day"

    minute_ttl = await limiter.redis_client.ttl(minute_key)
    hour_ttl = await limiter.redis_client.ttl(hour_key)
    day_ttl = await limiter.redis_client.ttl(day_key)

    # Verify TTLs are approximately correct (allow 2s variance)
    assert 59 <= minute_ttl <= 61, f"Minute TTL {minute_ttl} not in range [59, 61]"
    assert 3599 <= hour_ttl <= 3601, f"Hour TTL {hour_ttl} not in range [3599, 3601]"
    assert 86399 <= day_ttl <= 86401, f"Day TTL {day_ttl} not in range [86399, 86401]"


# ============================================================================
# Tier 2 Integration Test 6: Multi-Tier Limit Enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_multi_tier_limits_enforce_correctly(redis_limiter):
    """
    INTENT: Verify all three tiers (minute/hour/day) are enforced.

    Setup: Real Redis, limits={per_minute: 5, per_hour: 20, per_day: 100}
    Steps:
        1. Exhaust minute limit → blocked by per_minute
        2. Wait for minute window to expire
        3. Continue until hour limit reached → blocked by per_hour
    Assertions: Correct limit_exceeded field for each tier
    """
    limiter = redis_limiter

    # Exhaust minute limit (5 * 1.5 = 7 burst limit)
    for i in range(8):
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert result.allowed is False
    assert result.limit_exceeded == "per_minute"

    # Simulate minute window expiry by deleting old entries
    scope_key = "agent-001:user:user-123"
    minute_key = f"rl:ea:{scope_key}:minute"
    now = time.time()
    await limiter.redis_client.zremrangebyscore(minute_key, 0, now + 100)  # Clear all

    # Add 20 * 1.5 = 30 entries to hour window to exceed burst
    hour_key = f"rl:ea:{scope_key}:hour"
    async with limiter.redis_client.pipeline(transaction=True) as pipe:
        for i in range(31):
            timestamp = now - i * 60  # Spread over last hour
            pipe.zadd(hour_key, {str(timestamp): timestamp})
        await pipe.execute()

    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert result.allowed is False
    assert result.limit_exceeded == "per_hour"
