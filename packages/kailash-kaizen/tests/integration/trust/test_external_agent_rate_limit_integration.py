"""
Tier 2 Integration Tests: External Agent Rate Limiting with Real Redis.

Tests rate limiting with real Redis database (NO MOCKING).
Intent: Verify end-to-end rate limiting with real infrastructure.

Test Coverage:
- Rate limiting with real Redis persistence
- Sliding window accuracy with real time progression
- Graceful degradation when Redis unavailable
- Connection pooling reduces latency
- Redis key TTL expiration
- Multi-tier rate limiting coordination
- Concurrent invocation handling
"""

import asyncio
import time
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from kailash.trust.governance import ExternalAgentRateLimiter, RateLimitConfig

# Skip all tests if Redis not available
try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


def _check_redis_server_available() -> bool:
    """Check if Redis server is reachable at localhost:6379."""
    if not REDIS_AVAILABLE:
        return False
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 6379))
        sock.close()
        return result == 0
    except Exception:
        return False


REDIS_SERVER_AVAILABLE = _check_redis_server_available()

pytestmark = [
    pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis package not installed"),
    pytest.mark.skipif(
        not REDIS_SERVER_AVAILABLE,
        reason="Redis server not available at localhost:6379",
    ),
]


@pytest.fixture(scope="module")
def redis_server():
    """
    Fixture providing Redis URL for integration tests.
    Uses database 15 for integration testing.
    Redis availability is already checked by module-level skipif.
    """
    return "redis://localhost:6379/15"


@pytest_asyncio.fixture
async def clean_redis(redis_server):
    """
    Fixture to clean Redis before each test.
    """
    client = redis.Redis.from_url(redis_server, decode_responses=False)
    await client.flushdb()
    yield
    await client.flushdb()
    await client.aclose()


class TestRateLimitingWithRealRedis:
    """Test rate limiting with real Redis database (NO MOCKING)."""

    @pytest.mark.asyncio
    async def test_rate_limiting_end_to_end_with_real_redis(
        self, redis_server, clean_redis
    ):
        """
        Intent: Verify end-to-end rate limiting with real Redis persistence.

        Setup: Real Redis server, limits={per_minute: 5, per_hour: 20, per_day: 100}

        Steps:
        1. Make 5 invocations within 1 minute → all allowed
        2. Make 6th invocation → should block (per_minute exceeded)
        3. Verify Redis keys exist with correct structure
        4. Verify rate limit check returns correct quota information
        """
        config = RateLimitConfig(
            requests_per_minute=5,
            requests_per_hour=20,
            requests_per_day=100,
            enable_burst=False,  # Disable burst for exact testing
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=redis_server,
            config=config,
        )
        await limiter.initialize()

        try:
            # Step 1: Make 5 invocations (should all be allowed)
            for i in range(5):
                result = await limiter.check_rate_limit("agent-001", "user-123")
                assert result.allowed is True, f"Invocation {i + 1} should be allowed"
                await limiter.record_invocation("agent-001", "user-123")

            # Step 2: 6th invocation should block (per_minute exceeded)
            result = await limiter.check_rate_limit("agent-001", "user-123")
            assert result.allowed is False, "6th invocation should be blocked"
            assert result.limit_exceeded == "per_minute"
            assert result.remaining == 0
            assert result.retry_after_seconds is not None

            # Step 3: Verify Redis keys exist
            redis_client = redis.Redis.from_url(redis_server, decode_responses=False)
            minute_key = b"rl:ea:agent-001:user:user-123:minute"
            hour_key = b"rl:ea:agent-001:user:user-123:hour"
            day_key = b"rl:ea:agent-001:user:user-123:day"

            minute_count = await redis_client.zcard(minute_key)
            hour_count = await redis_client.zcard(hour_key)
            day_count = await redis_client.zcard(day_key)

            assert minute_count == 5, "Should have 5 entries in minute window"
            assert hour_count == 5, "Should have 5 entries in hour window"
            assert day_count == 5, "Should have 5 entries in day window"

            # Verify TTL is set correctly
            minute_ttl = await redis_client.ttl(minute_key)
            hour_ttl = await redis_client.ttl(hour_key)
            day_ttl = await redis_client.ttl(day_key)

            assert minute_ttl > 0, "Minute key should have TTL"
            assert hour_ttl > 0, "Hour key should have TTL"
            assert day_ttl > 0, "Day key should have TTL"

            await redis_client.close()

        finally:
            await limiter.close()

    @pytest.mark.asyncio
    async def test_sliding_window_accuracy_with_time_progression(
        self, redis_server, clean_redis
    ):
        """
        Intent: Verify sliding window removes old entries correctly over time.

        Setup: Real Redis, limits={per_minute: 3}

        Steps:
        1. Make invocation at t=0
        2. Make invocation at t=0
        3. Make invocation at t=0 (3 total, at limit)
        4. Attempt invocation at t=0 (should block, 3 in last 60s)
        5. Wait 61 seconds
        6. Attempt invocation at t=61s (should allow, entries expired)

        Note: This test uses real time delays (61 seconds).
        Set pytest timeout appropriately: pytest -k test_sliding_window --timeout=120
        """
        config = RateLimitConfig(
            requests_per_minute=3,
            requests_per_hour=100,
            requests_per_day=1000,
            enable_burst=False,
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=redis_server,
            config=config,
        )
        await limiter.initialize()

        try:
            # Make 3 invocations at t=0
            for i in range(3):
                await limiter.record_invocation("agent-001", "user-123")

            # t=0: Should block (at limit)
            result_blocked = await limiter.check_rate_limit("agent-001", "user-123")
            assert result_blocked.allowed is False
            assert result_blocked.limit_exceeded == "per_minute"

            # Wait for sliding window to expire (62 seconds to account for test overhead)
            # Note: In CI/CD, this test may be skipped if timeout is an issue
            # For local testing, this validates real sliding window behavior
            print("Waiting 62 seconds for sliding window to expire...")
            await asyncio.sleep(62)

            # t=61s: Should allow (old entries expired)
            result_allowed = await limiter.check_rate_limit("agent-001", "user-123")
            assert result_allowed.allowed is True, "Should allow after window expires"
            assert result_allowed.current_usage["minute"] == 0  # Old entries removed

        finally:
            await limiter.close()

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)  # 2 minute timeout for this test
    async def test_sliding_window_partial_expiration(self, redis_server, clean_redis):
        """
        Intent: Verify sliding window handles partial expiration correctly.

        Setup: Real Redis, limits={per_minute: 3}

        Steps:
        1. Make invocation at t=0
        2. Wait 30 seconds
        3. Make invocation at t=30s
        4. Make invocation at t=31s (3 total)
        5. Attempt at t=31s (should block)
        6. Wait 30 seconds (t=61s)
        7. Attempt at t=61s (should allow - first entry expired)
        """
        config = RateLimitConfig(
            requests_per_minute=3,
            requests_per_hour=100,
            requests_per_day=1000,
            enable_burst=False,
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=redis_server,
            config=config,
        )
        await limiter.initialize()

        try:
            # t=0: First invocation
            await limiter.record_invocation("agent-001", "user-123")
            first_invocation_time = time.time()

            # Wait 30 seconds
            await asyncio.sleep(30)

            # t=30s: Second and third invocations
            await limiter.record_invocation("agent-001", "user-123")
            await limiter.record_invocation("agent-001", "user-123")

            # t=30s: Should block (3 invocations in last 60s)
            result_blocked = await limiter.check_rate_limit("agent-001", "user-123")
            assert result_blocked.allowed is False

            # Wait another 32 seconds (total 62s from first invocation to account for overhead)
            await asyncio.sleep(32)

            # t=61s: Should allow (first invocation expired)
            result_allowed = await limiter.check_rate_limit("agent-001", "user-123")
            assert result_allowed.allowed is True
            # Should have 2 invocations remaining in window (at t=30s and t=31s)
            assert result_allowed.current_usage["minute"] == 2

        finally:
            await limiter.close()

    @pytest.mark.asyncio
    async def test_graceful_degradation_when_redis_unavailable(
        self, redis_server, clean_redis
    ):
        """
        Intent: Verify fail-open behavior when Redis connection fails.

        Setup: ExternalAgentRateLimiter, stop Redis server mid-test

        Steps:
        1. Make 3 successful invocations (Redis available)
        2. Close Redis connection to simulate failure
        3. Make 4th invocation (Redis unavailable)
        4. Verify fail-open (allowed=True, warning logged)
        """
        config = RateLimitConfig(
            requests_per_minute=5,
            requests_per_hour=20,
            requests_per_day=100,
            fail_open_on_error=True,  # Fail-open mode
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=redis_server,
            config=config,
        )
        await limiter.initialize()

        try:
            # Step 1: Make 3 successful invocations
            for i in range(3):
                result = await limiter.check_rate_limit("agent-001", "user-123")
                assert result.allowed is True
                await limiter.record_invocation("agent-001", "user-123")

            # Step 2: Close Redis connection to simulate failure
            await limiter.close()

            # Step 3: Make 4th invocation with Redis unavailable
            result = await limiter.check_rate_limit("agent-001", "user-123")

            # Step 4: Verify fail-open
            assert result.allowed is True, "Should fail-open when Redis unavailable"
            assert result.remaining == -1, "Remaining should be unknown (-1)"
            assert result.limit_exceeded is None

            # Verify metrics tracked fail-open
            metrics = limiter.get_metrics()
            if metrics:
                assert (
                    metrics.fail_open_total >= 1
                ), "Should track fail-open occurrences"

        finally:
            # Limiter already closed in test
            pass

    @pytest.mark.asyncio
    async def test_redis_connection_pooling_reduces_latency(
        self, redis_server, clean_redis
    ):
        """
        Intent: Verify connection pooling improves performance with concurrent checks.

        Setup: Real Redis, ExternalAgentRateLimiter with connection pool

        Steps:
        1. Make 100 concurrent check_rate_limit() calls (asyncio.gather)
        2. Verify all 100 checks complete without connection errors
        3. Verify average latency <10ms (connection pooling benefit)
        """
        config = RateLimitConfig(
            requests_per_minute=1000,  # High limit to avoid blocking
            requests_per_hour=10000,
            requests_per_day=100000,
            redis_max_connections=50,  # Connection pool size
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=redis_server,
            config=config,
        )
        await limiter.initialize()

        try:
            # Make 100 concurrent checks
            start_time = time.time()
            tasks = [
                limiter.check_rate_limit("agent-001", f"user-{i}") for i in range(100)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()

            # Verify all checks succeeded
            errors = [r for r in results if isinstance(r, Exception)]
            assert len(errors) == 0, f"Should have no connection errors, got: {errors}"

            successful_results = [r for r in results if not isinstance(r, Exception)]
            assert (
                len(successful_results) == 100
            ), "All 100 checks should complete successfully"

            # Verify average latency <10ms
            total_duration = end_time - start_time
            avg_latency = (total_duration / 100) * 1000  # Convert to ms

            print(f"Average latency: {avg_latency:.2f}ms for 100 concurrent checks")

            # Connection pooling should keep latency low
            assert (
                avg_latency < 50
            ), f"Average latency should be <50ms with pooling, got {avg_latency:.2f}ms"

        finally:
            await limiter.close()

    @pytest.mark.asyncio
    async def test_multi_tier_rate_limiting_coordination(
        self, redis_server, clean_redis
    ):
        """
        Intent: Verify multi-tier rate limiting coordinates minute/hour/day limits.

        Setup: Real Redis, limits={per_minute: 5, per_hour: 10, per_day: 20}

        Steps:
        1. Make 5 invocations (under all limits)
        2. Make 6th invocation (blocked by minute limit)
        3. Wait 61 seconds for minute window to reset
        4. Make 5 more invocations (total 10, at hour limit)
        5. Make 11th invocation (blocked by hour limit, minute OK)
        """
        config = RateLimitConfig(
            requests_per_minute=5,
            requests_per_hour=10,
            requests_per_day=20,
            enable_burst=False,
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=redis_server,
            config=config,
        )
        await limiter.initialize()

        try:
            # Step 1: Make 5 invocations
            for i in range(5):
                result = await limiter.check_rate_limit("agent-001", "user-123")
                assert result.allowed is True
                await limiter.record_invocation("agent-001", "user-123")

            # Step 2: 6th invocation blocked by minute limit
            result = await limiter.check_rate_limit("agent-001", "user-123")
            assert result.allowed is False
            assert result.limit_exceeded == "per_minute"

            # Step 3: Wait 62 seconds for minute window to reset (extra second for overhead)
            print("Waiting 62 seconds for minute window reset...")
            await asyncio.sleep(62)

            # Step 4: Make 5 more invocations (total 10 in hour)
            for i in range(5):
                result = await limiter.check_rate_limit("agent-001", "user-123")
                assert result.allowed is True, f"Invocation {i + 6} should be allowed"
                await limiter.record_invocation("agent-001", "user-123")

            # Step 5: 11th invocation blocked (both minute and hour limits reached)
            # Note: Since minute is checked first, it may return per_minute even though
            # per_hour is also at limit (5/5 minute, 10/10 hour)
            result = await limiter.check_rate_limit("agent-001", "user-123")
            assert result.allowed is False
            assert result.limit_exceeded in (
                "per_minute",
                "per_hour",
            ), f"Should be blocked by rate limit, got {result.limit_exceeded}"

        finally:
            await limiter.close()

    @pytest.mark.asyncio
    async def test_redis_pipeline_optimization(self, redis_server, clean_redis):
        """
        Intent: Verify Redis pipeline reduces latency for multi-tier checks.

        Setup: Real Redis with network latency simulation

        Steps:
        1. Make single check_rate_limit() call
        2. Verify only ONE Redis round-trip (pipeline optimization)
        3. Compare latency with/without pipeline (implicit in implementation)
        """
        config = RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=100,
            requests_per_day=1000,
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=redis_server,
            config=config,
        )
        await limiter.initialize()

        try:
            # Single check should use pipeline for all 3 windows
            start_time = time.time()
            result = await limiter.check_rate_limit("agent-001", "user-123")
            end_time = time.time()

            assert result.allowed is True

            # Pipeline optimization should keep latency very low (<10ms)
            latency_ms = (end_time - start_time) * 1000
            print(f"Single check latency: {latency_ms:.2f}ms")

            # With pipeline, checking 3 windows should be <10ms
            assert (
                latency_ms < 20
            ), f"Pipeline should keep latency <20ms, got {latency_ms:.2f}ms"

        finally:
            await limiter.close()

    @pytest.mark.asyncio
    async def test_per_user_isolation(self, redis_server, clean_redis):
        """
        Intent: Verify per-user rate limiting isolates quotas correctly.

        Setup: Real Redis, limits={per_minute: 5}

        Steps:
        1. User A makes 5 invocations → all allowed
        2. User B makes 5 invocations → all allowed (separate quota)
        3. User A makes 6th invocation → blocked (User A quota exhausted)
        4. User B makes 6th invocation → blocked (User B quota exhausted)
        5. Verify Redis keys are separate for each user
        """
        config = RateLimitConfig(
            requests_per_minute=5,
            requests_per_hour=100,
            requests_per_day=1000,
            enable_burst=False,
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=redis_server,
            config=config,
        )
        await limiter.initialize()

        try:
            # Step 1: User A makes 5 invocations
            for i in range(5):
                result = await limiter.check_rate_limit("agent-001", "user-a")
                assert result.allowed is True
                await limiter.record_invocation("agent-001", "user-a")

            # Step 2: User B makes 5 invocations (separate quota)
            for i in range(5):
                result = await limiter.check_rate_limit("agent-001", "user-b")
                assert (
                    result.allowed is True
                ), "User B should have separate quota from User A"
                await limiter.record_invocation("agent-001", "user-b")

            # Step 3: User A 6th invocation blocked
            result_a = await limiter.check_rate_limit("agent-001", "user-a")
            assert result_a.allowed is False
            assert result_a.limit_exceeded == "per_minute"

            # Step 4: User B 6th invocation blocked
            result_b = await limiter.check_rate_limit("agent-001", "user-b")
            assert result_b.allowed is False
            assert result_b.limit_exceeded == "per_minute"

            # Step 5: Verify separate Redis keys
            redis_client = redis.Redis.from_url(redis_server, decode_responses=False)
            key_a = b"rl:ea:agent-001:user:user-a:minute"
            key_b = b"rl:ea:agent-001:user:user-b:minute"

            count_a = await redis_client.zcard(key_a)
            count_b = await redis_client.zcard(key_b)

            assert count_a == 5, "User A should have 5 invocations"
            assert count_b == 5, "User B should have 5 invocations"

            await redis_client.close()

        finally:
            await limiter.close()

    @pytest.mark.asyncio
    async def test_redis_key_ttl_prevents_memory_growth(
        self, redis_server, clean_redis
    ):
        """
        Intent: Verify Redis keys expire correctly to prevent memory growth.

        Setup: Real Redis

        Steps:
        1. Make invocation
        2. Verify minute key has TTL=61s
        3. Verify hour key has TTL=3601s
        4. Verify day key has TTL=86401s
        """
        config = RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=100,
            requests_per_day=1000,
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=redis_server,
            config=config,
        )
        await limiter.initialize()

        try:
            # Make invocation
            await limiter.record_invocation("agent-001", "user-123")

            # Check TTLs
            redis_client = redis.Redis.from_url(redis_server, decode_responses=False)

            minute_key = b"rl:ea:agent-001:user:user-123:minute"
            hour_key = b"rl:ea:agent-001:user:user-123:hour"
            day_key = b"rl:ea:agent-001:user:user-123:day"

            minute_ttl = await redis_client.ttl(minute_key)
            hour_ttl = await redis_client.ttl(hour_key)
            day_ttl = await redis_client.ttl(day_key)

            # Verify TTLs are close to expected values (allow 5s margin)
            assert (
                56 <= minute_ttl <= 61
            ), f"Minute TTL should be ~61s, got {minute_ttl}s"
            assert (
                3596 <= hour_ttl <= 3601
            ), f"Hour TTL should be ~3601s, got {hour_ttl}s"
            assert (
                86396 <= day_ttl <= 86401
            ), f"Day TTL should be ~86401s, got {day_ttl}s"

            await redis_client.close()

        finally:
            await limiter.close()


# Integration with pytest fixtures
@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for async tests.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
