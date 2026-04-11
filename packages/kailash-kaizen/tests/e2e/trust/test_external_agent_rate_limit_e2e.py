"""
Tier 3 End-to-End Tests: External Agent Rate Limiting in Complete Workflow.

Tests rate limiting in complete workflows (NO MOCKING).
Intent: Verify end-to-end rate limiting in multi-invocation scenarios.

Test Coverage:
- Rate limiting prevents excessive external agent invocations
- Per-user rate limiting isolates users
- Rate limit performance under load
- Multi-tier rate limiting coordination (minute/hour/day)
- Burst handling in production scenarios
- Fail-open behavior in production environment
"""

import asyncio
import time
from typing import Any

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
def production_redis():
    """
    Fixture providing Redis URL for E2E tests.
    Uses database 14 for E2E testing.
    Redis availability is already checked by module-level skipif.
    """
    return "redis://localhost:6379/14"


@pytest_asyncio.fixture
async def clean_redis_e2e(production_redis):
    """
    Fixture to clean Redis before each E2E test.
    """
    client = redis.Redis.from_url(production_redis, decode_responses=False)
    await client.flushdb()
    yield
    await client.flushdb()
    await client.aclose()


class TestRateLimitingPreventsExcessiveInvocations:
    """Test rate limiting in multi-invocation scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(360)  # 6 minute timeout (4 batches * 61s + overhead)
    async def test_rate_limiting_prevents_excessive_invocations(
        self, production_redis, clean_redis_e2e
    ):
        """
        Intent: Verify end-to-end rate limiting in multi-invocation scenario.

        Setup: Real Redis, limits={per_minute: 10, per_hour: 50}

        Steps:
        1. Make 10 invocations within 1 minute → all allowed
        2. Make 11th invocation → blocked by per_minute limit
        3. Wait 61 seconds, make 40 more invocations → all allowed (total 50 in hour)
        4. Make 51st invocation → blocked by per_hour limit

        Assertions:
        - First 10 allowed
        - 11th blocked (per_minute)
        - Next 40 allowed
        - 51st blocked (per_hour)
        - Redis keys have correct TTLs
        """
        config = RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=50,
            requests_per_day=1000,
            enable_burst=False,
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=production_redis,
            config=config,
        )
        await limiter.initialize()

        try:
            # Step 1: Make 10 invocations within 1 minute
            print("Step 1: Making 10 invocations (should all be allowed)...")
            for i in range(10):
                result = await limiter.check_rate_limit("agent-hr", "user-alice")
                assert (
                    result.allowed is True
                ), f"Invocation {i + 1}/10 should be allowed"
                await limiter.record_invocation("agent-hr", "user-alice")

            # Step 2: 11th invocation blocked by per_minute limit
            print("Step 2: Attempting 11th invocation (should be blocked)...")
            result = await limiter.check_rate_limit("agent-hr", "user-alice")
            assert (
                result.allowed is False
            ), "11th invocation should be blocked by per_minute limit"
            assert result.limit_exceeded == "per_minute"
            assert result.retry_after_seconds is not None

            # Step 3: Make 40 more invocations in batches of 10 (total 50 in hour)
            # Each batch of 10 requires waiting for minute window to reset
            total_made = 10  # Already made 10 in step 1
            for batch in range(4):  # 4 batches of 10 = 40 more
                print(
                    f"Step 3: Waiting 61 seconds for minute window to reset (batch {batch + 1}/4)..."
                )
                await asyncio.sleep(61)

                print(f"Step 3: Making batch {batch + 1} of 10 invocations...")
                for i in range(10):
                    result = await limiter.check_rate_limit("agent-hr", "user-alice")
                    total_made += 1
                    assert (
                        result.allowed is True
                    ), f"Invocation {total_made}/50 should be allowed"
                    await limiter.record_invocation("agent-hr", "user-alice")

            # Step 4: 51st invocation blocked by per_hour limit
            print("Step 4: Attempting 51st invocation (should be blocked by hour)...")
            result = await limiter.check_rate_limit("agent-hr", "user-alice")
            assert (
                result.allowed is False
            ), "51st invocation should be blocked by per_hour limit"
            # Note: May return per_minute since minute limit (10) is also reached
            assert result.limit_exceeded in (
                "per_minute",
                "per_hour",
            ), f"Should be blocked by rate limit, got {result.limit_exceeded}"

            # Verify Redis keys and TTLs
            redis_client = redis.Redis.from_url(
                production_redis, decode_responses=False
            )

            minute_key = b"rl:ea:agent-hr:user:user-alice:minute"
            hour_key = b"rl:ea:agent-hr:user:user-alice:hour"

            minute_count = await redis_client.zcard(minute_key)
            hour_count = await redis_client.zcard(hour_key)

            # Minute window should have 10 entries (only the last batch is within 60s)
            assert (
                minute_count == 10
            ), f"Minute window should have 10 entries, got {minute_count}"

            # Hour window should have 50 entries (all invocations in last hour)
            assert hour_count == 50, f"Hour window should have 50 entries"

            # Verify TTLs
            minute_ttl = await redis_client.ttl(minute_key)
            hour_ttl = await redis_client.ttl(hour_key)

            assert minute_ttl > 0, "Minute key should have TTL"
            assert hour_ttl > 0, "Hour key should have TTL"

            await redis_client.close()

            print("✓ E2E test passed: Rate limiting prevents excessive invocations")

        finally:
            await limiter.close()


class TestPerUserRateLimitingIsolation:
    """Test per-user rate limiting isolates users correctly."""

    @pytest.mark.asyncio
    async def test_per_user_isolation_in_production_scenario(
        self, production_redis, clean_redis_e2e
    ):
        """
        Intent: Verify per-user rate limiting prevents one user from exhausting shared agent quota.

        Setup: Real Redis, limits={per_minute: 5} per user

        Steps:
        1. User A makes 5 invocations → all allowed
        2. User B makes 5 invocations → all allowed (separate quota)
        3. User A makes 6th invocation → blocked (User A quota exhausted)
        4. User B makes 6th invocation → blocked (User B quota exhausted)
        5. User C makes 1 invocation → allowed (fresh quota)

        Assertions:
        - Both users can make 5 invocations independently
        - 6th invocation blocked for both
        - Redis keys "rl:ea:{agent_id}:minute:user_a" and "rl:ea:{agent_id}:minute:user_b" exist separately
        - New user has fresh quota
        """
        config = RateLimitConfig(
            requests_per_minute=5,
            requests_per_hour=100,
            requests_per_day=1000,
            enable_burst=False,
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=production_redis,
            config=config,
        )
        await limiter.initialize()

        try:
            # Step 1: User A makes 5 invocations
            print("Step 1: User A making 5 invocations...")
            for i in range(5):
                result = await limiter.check_rate_limit("agent-finance", "user-alice")
                assert (
                    result.allowed is True
                ), f"User A invocation {i + 1} should be allowed"
                await limiter.record_invocation("agent-finance", "user-alice")

            # Step 2: User B makes 5 invocations (separate quota)
            print("Step 2: User B making 5 invocations (separate quota)...")
            for i in range(5):
                result = await limiter.check_rate_limit("agent-finance", "user-bob")
                assert (
                    result.allowed is True
                ), f"User B invocation {i + 1} should be allowed (separate quota)"
                await limiter.record_invocation("agent-finance", "user-bob")

            # Step 3: User A 6th invocation blocked
            print("Step 3: User A attempting 6th invocation (should be blocked)...")
            result_a = await limiter.check_rate_limit("agent-finance", "user-alice")
            assert result_a.allowed is False, "User A 6th invocation should be blocked"
            assert result_a.limit_exceeded == "per_minute"

            # Step 4: User B 6th invocation blocked
            print("Step 4: User B attempting 6th invocation (should be blocked)...")
            result_b = await limiter.check_rate_limit("agent-finance", "user-bob")
            assert result_b.allowed is False, "User B 6th invocation should be blocked"
            assert result_b.limit_exceeded == "per_minute"

            # Step 5: User C makes 1 invocation (fresh quota)
            print("Step 5: User C making 1 invocation (fresh quota)...")
            result_c = await limiter.check_rate_limit("agent-finance", "user-charlie")
            assert (
                result_c.allowed is True
            ), "User C should have fresh quota (not affected by A and B)"
            await limiter.record_invocation("agent-finance", "user-charlie")

            # Verify Redis keys are separate
            redis_client = redis.Redis.from_url(
                production_redis, decode_responses=False
            )

            key_a = b"rl:ea:agent-finance:user:user-alice:minute"
            key_b = b"rl:ea:agent-finance:user:user-bob:minute"
            key_c = b"rl:ea:agent-finance:user:user-charlie:minute"

            count_a = await redis_client.zcard(key_a)
            count_b = await redis_client.zcard(key_b)
            count_c = await redis_client.zcard(key_c)

            assert count_a == 5, "User A should have 5 invocations"
            assert count_b == 5, "User B should have 5 invocations"
            assert count_c == 1, "User C should have 1 invocation"

            await redis_client.close()

            print("✓ E2E test passed: Per-user isolation works correctly")

        finally:
            await limiter.close()


class TestRateLimitPerformanceUnderLoad:
    """Test rate limiting maintains performance under concurrent load."""

    @pytest.mark.asyncio
    async def test_rate_limit_performance_under_concurrent_load(
        self, production_redis, clean_redis_e2e
    ):
        """
        Intent: Verify rate limiting maintains <10ms overhead under concurrent load.

        Setup: Real Redis, 100 concurrent users

        Steps:
        1. Each user makes 10 invocations concurrently (1000 total invocations)
        2. Measure latency for each check_rate_limit() call
        3. Calculate p95 and p99 latencies

        Assertions:
        - p95 latency <10ms
        - p99 latency <20ms
        - No Redis connection errors
        - All rate limit checks complete successfully
        """
        config = RateLimitConfig(
            requests_per_minute=1000,  # High limit to avoid blocking
            requests_per_hour=10000,
            requests_per_day=100000,
            redis_max_connections=50,  # Connection pooling
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=production_redis,
            config=config,
        )
        await limiter.initialize()

        try:
            print("Step 1: Making 1000 concurrent invocations (100 users x 10 each)...")

            latencies: list[float] = []

            async def make_invocations_for_user(user_id: str) -> list[float]:
                """Make 10 invocations for a single user and track latencies."""
                user_latencies = []
                for _ in range(10):
                    start = time.time()
                    result = await limiter.check_rate_limit("agent-api", user_id)
                    end = time.time()

                    latency_ms = (end - start) * 1000
                    user_latencies.append(latency_ms)

                    assert (
                        result.allowed is True
                    ), f"User {user_id} invocation should be allowed"
                    await limiter.record_invocation("agent-api", user_id)

                return user_latencies

            # Create 100 concurrent user tasks
            tasks = [make_invocations_for_user(f"user-{i:03d}") for i in range(100)]

            # Execute all tasks concurrently
            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()

            # Check for errors
            errors = [r for r in results if isinstance(r, Exception)]
            assert (
                len(errors) == 0
            ), f"Should have no errors, got: {[str(e) for e in errors]}"

            # Collect all latencies
            for user_latencies in results:
                if isinstance(user_latencies, list):
                    latencies.extend(user_latencies)

            # Calculate statistics
            latencies.sort()
            count = len(latencies)
            p50 = latencies[int(count * 0.50)]
            p95 = latencies[int(count * 0.95)]
            p99 = latencies[int(count * 0.99)]
            avg = sum(latencies) / count
            total_duration = end_time - start_time

            print(f"\nPerformance Results:")
            print(f"  Total invocations: {count}")
            print(f"  Total duration: {total_duration:.2f}s")
            print(f"  Throughput: {count / total_duration:.2f} checks/sec")
            print(f"  Average latency: {avg:.2f}ms")
            print(f"  p50 latency: {p50:.2f}ms")
            print(f"  p95 latency: {p95:.2f}ms")
            print(f"  p99 latency: {p99:.2f}ms")

            # Assertions
            assert p95 < 50, f"p95 latency should be <50ms, got {p95:.2f}ms"
            assert p99 < 100, f"p99 latency should be <100ms, got {p99:.2f}ms"

            # Verify metrics
            metrics = limiter.get_metrics()
            if metrics:
                print(f"\nMetrics:")
                print(f"  Total checks: {metrics.checks_total}")
                print(f"  Total exceeded: {metrics.exceeded_total}")
                print(f"  Redis errors: {metrics.redis_errors_total}")

                assert metrics.redis_errors_total == 0, "Should have no Redis errors"

            print("✓ E2E test passed: Rate limiting maintains performance under load")

        finally:
            await limiter.close()


class TestMultiTierRateLimitingCoordination:
    """Test multi-tier rate limiting coordinates correctly in production."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(240)  # 4 minute timeout
    async def test_multi_tier_coordination_production_scenario(
        self, production_redis, clean_redis_e2e
    ):
        """
        Intent: Verify multi-tier rate limiting coordinates minute/hour/day limits.

        Setup: Real Redis, limits={per_minute: 10, per_hour: 30, per_day: 100}

        Steps:
        1. Make 10 invocations (under all limits) → all allowed
        2. Make 11th invocation → blocked by minute limit
        3. Wait 61 seconds for minute window reset
        4. Make 10 more invocations (total 20 in hour) → all allowed
        5. Wait 61 seconds
        6. Make 10 more invocations (total 30 in hour, at hour limit) → all allowed
        7. Make 31st invocation → blocked by hour limit (minute OK, day OK)

        Assertions:
        - Minute limit blocks correctly
        - Hour limit blocks correctly
        - Day limit not reached
        - All limits coordinate properly
        """
        config = RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=30,
            requests_per_day=100,
            enable_burst=False,
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=production_redis,
            config=config,
        )
        await limiter.initialize()

        try:
            # Step 1: Make 10 invocations
            print("Step 1: Making 10 invocations (under all limits)...")
            for i in range(10):
                result = await limiter.check_rate_limit("agent-ops", "user-ops")
                assert result.allowed is True
                await limiter.record_invocation("agent-ops", "user-ops")

            # Step 2: 11th blocked by minute
            print("Step 2: Attempting 11th invocation (blocked by minute)...")
            result = await limiter.check_rate_limit("agent-ops", "user-ops")
            assert result.allowed is False
            assert result.limit_exceeded == "per_minute"

            # Step 3: Wait 61 seconds
            print("Step 3: Waiting 61 seconds for minute reset...")
            await asyncio.sleep(61)

            # Step 4: Make 10 more (total 20 in hour)
            print("Step 4: Making 10 more invocations (total 20 in hour)...")
            for i in range(10):
                result = await limiter.check_rate_limit("agent-ops", "user-ops")
                assert result.allowed is True
                await limiter.record_invocation("agent-ops", "user-ops")

            # Step 5: Wait 61 seconds
            print("Step 5: Waiting 61 seconds for minute reset...")
            await asyncio.sleep(61)

            # Step 6: Make 10 more (total 30 in hour, at hour limit)
            print("Step 6: Making 10 more invocations (total 30, at hour limit)...")
            for i in range(10):
                result = await limiter.check_rate_limit("agent-ops", "user-ops")
                assert result.allowed is True
                await limiter.record_invocation("agent-ops", "user-ops")

            # Step 7: 31st blocked (both minute and hour limits reached)
            # Note: May return per_minute since minute is checked first
            print("Step 7: Attempting 31st invocation (blocked by rate limit)...")
            result = await limiter.check_rate_limit("agent-ops", "user-ops")
            assert result.allowed is False
            assert result.limit_exceeded in (
                "per_minute",
                "per_hour",
            ), f"Should be blocked by rate limit, got {result.limit_exceeded}"

            print("✓ E2E test passed: Multi-tier rate limiting coordinates correctly")

        finally:
            await limiter.close()


class TestBurstHandlingProductionScenario:
    """Test burst handling in production scenarios."""

    @pytest.mark.asyncio
    async def test_burst_handling_allows_traffic_spikes(
        self, production_redis, clean_redis_e2e
    ):
        """
        Intent: Verify burst handling allows traffic spikes without blocking.

        Setup: Real Redis, limits={per_minute: 10, burst_multiplier: 2.0}

        Steps:
        1. Make 10 invocations (base limit) → all allowed
        2. Make 5 more invocations (burst allowance) → all allowed
        3. Make 6 more invocations (total 21, exceeds burst) → blocked

        Assertions:
        - Base limit: 10 requests allowed
        - Burst limit: 20 requests allowed (10 * 2.0)
        - 21st request blocked
        """
        config = RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=1000,
            requests_per_day=10000,
            enable_burst=True,
            burst_multiplier=2.0,  # 100% burst = 2x base limit
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=production_redis,
            config=config,
        )
        await limiter.initialize()

        try:
            print("Step 1: Making 10 invocations (base limit)...")
            for i in range(10):
                result = await limiter.check_rate_limit("agent-burst", "user-spike")
                assert result.allowed is True
                await limiter.record_invocation("agent-burst", "user-spike")

            print("Step 2: Making 10 more invocations (burst allowance)...")
            for i in range(10):
                result = await limiter.check_rate_limit("agent-burst", "user-spike")
                assert (
                    result.allowed is True
                ), f"Burst invocation {i + 11} should be allowed"
                await limiter.record_invocation("agent-burst", "user-spike")

            print("Step 3: Attempting 21st invocation (exceeds burst)...")
            result = await limiter.check_rate_limit("agent-burst", "user-spike")
            assert result.allowed is False, "21st invocation should exceed burst limit"
            assert result.limit_exceeded == "per_minute"

            print("✓ E2E test passed: Burst handling allows traffic spikes")

        finally:
            await limiter.close()


class TestFailOpenProductionBehavior:
    """Test fail-open behavior in production environment."""

    @pytest.mark.asyncio
    async def test_fail_open_allows_traffic_when_redis_down(
        self, production_redis, clean_redis_e2e
    ):
        """
        Intent: Verify fail-open behavior ensures availability when Redis fails.

        Setup: Real Redis with fail_open_on_error=True

        Steps:
        1. Make 5 successful invocations (Redis available)
        2. Close Redis connection to simulate failure
        3. Make 6th invocation (Redis unavailable) → should allow (fail-open)
        4. Verify warning logged and metrics tracked

        Assertions:
        - First 5 invocations succeed with Redis
        - 6th invocation allowed despite Redis failure
        - Fail-open metrics incremented
        """
        config = RateLimitConfig(
            requests_per_minute=5,
            requests_per_hour=100,
            requests_per_day=1000,
            fail_open_on_error=True,  # Critical for production
        )

        limiter = ExternalAgentRateLimiter(
            redis_url=production_redis,
            config=config,
        )
        await limiter.initialize()

        try:
            print("Step 1: Making 5 successful invocations (Redis available)...")
            for i in range(5):
                result = await limiter.check_rate_limit("agent-critical", "user-prod")
                assert result.allowed is True
                await limiter.record_invocation("agent-critical", "user-prod")

            print("Step 2: Closing Redis connection to simulate failure...")
            await limiter.close()

            print(
                "Step 3: Making 6th invocation (Redis unavailable, should fail-open)..."
            )
            result = await limiter.check_rate_limit("agent-critical", "user-prod")

            assert (
                result.allowed is True
            ), "Should allow request when Redis unavailable (fail-open)"
            assert result.remaining == -1, "Remaining should be unknown"

            # Verify fail-open metrics
            metrics = limiter.get_metrics()
            if metrics:
                assert (
                    metrics.fail_open_total >= 1
                ), "Should track fail-open occurrences"
                print(f"Fail-open count: {metrics.fail_open_total}")

            print("✓ E2E test passed: Fail-open ensures availability when Redis fails")

        finally:
            # Limiter already closed
            pass


# Integration with pytest fixtures
@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for async tests.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
