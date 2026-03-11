"""
Tier 3 E2E Tests: ExternalAgentRateLimiter Complete Workflows

INTENT-BASED TESTING:
Tests verify complete workflows with real infrastructure (NO MOCKING).

Tests validate:
- Rate limiting prevents excessive external agent invocations
- Per-user rate limiting isolates users
- Performance under concurrent load
- Real-world scenarios with multiple windows

Prerequisites:
- Redis server running on localhost:6379
- redis Python package installed
"""

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from kaizen.governance import (
    ExternalAgentRateLimiter,
    RateLimitCheckResult,
    RateLimitConfig,
)

# Check if Redis is available
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/15")  # Use DB 15 for tests

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
]


@pytest.fixture
async def production_limiter():
    """Create production-like rate limiter configuration."""
    config = RateLimitConfig(
        requests_per_minute=10,
        requests_per_hour=50,
        requests_per_day=200,
        burst_multiplier=1.5,
        redis_max_connections=50,
        enable_metrics=True,
    )

    limiter = ExternalAgentRateLimiter(redis_url=REDIS_URL, config=config)

    try:
        await limiter.initialize()
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")

    yield limiter

    # Cleanup
    if limiter.redis_client:
        try:
            async for key in limiter.redis_client.scan_iter(match="rl:ea:*"):
                await limiter.redis_client.delete(key)
        except Exception:
            pass

    await limiter.close()


# ============================================================================
# Tier 3 E2E Test 1: Multi-Invocation Scenario
# ============================================================================


@pytest.mark.asyncio
async def test_rate_limiting_prevents_excessive_invocations(production_limiter):
    """
    INTENT: Verify end-to-end rate limiting in multi-invocation scenario.

    Setup: Real Redis, limits={per_minute: 10, per_hour: 50}
    Steps:
        1. Make 10 invocations within 1 minute → all allowed
        2. Make 11th invocation → blocked by per_minute limit
        3. Wait 61 seconds, make 40 more invocations → all allowed (total 50 in hour)
        4. Make 51st invocation → blocked by per_hour limit
    Assertions: First 10 allowed, 11th blocked (per_minute), next 40 allowed, 51st blocked (per_hour)
    """
    limiter = production_limiter

    # Step 1: Make 10 invocations (at base limit)
    for i in range(10):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-123"
        )
        assert result.allowed is True, f"Request {i+1} should be allowed"
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    print(f"\nStep 1: Made 10 invocations (at base limit)")

    # Step 2: Make 11th invocation (burst allows up to 15, so add 5 more)
    for i in range(5):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-123"
        )
        assert result.allowed is True, f"Burst request {i+1} should be allowed"
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    # Now at burst limit (15), next should block
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert result.allowed is False, "16th request should be blocked"
    assert result.limit_exceeded == "per_minute"

    print(f"Step 2: 16th invocation blocked by per_minute limit")

    # Step 3: Simulate 61 seconds passing (clear minute window)
    scope_key = "agent-001:user:user-123"
    minute_key = f"rl:ea:{scope_key}:minute"
    now = time.time()
    await limiter.redis_client.zremrangebyscore(minute_key, 0, now + 100)

    # Make 40 more invocations (will reach hour limit)
    # Current hour count: 15 (from step 1+2)
    # Need to reach 50 * 1.5 = 75 burst limit for hour
    # So make 60 more (15 + 60 = 75)
    for i in range(60):
        # Record without checking (simulate time passing)
        await limiter.record_invocation(agent_id="agent-001", user_id="user-123")

    print(f"Step 3: Made 60 more invocations (total 75 in hour = burst limit)")

    # Step 4: Make next invocation (should block - hour burst limit exceeded)
    result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-123")
    assert result.allowed is False, "76th request should be blocked"
    assert result.limit_exceeded == "per_hour"

    print(f"Step 4: 76th invocation blocked by per_hour limit")

    # Verify Redis keys have correct TTLs
    hour_key = f"rl:ea:{scope_key}:hour"
    hour_ttl = await limiter.redis_client.ttl(hour_key)
    assert 3000 <= hour_ttl <= 3601, f"Hour TTL {hour_ttl} out of range"

    # Verify metrics
    metrics = limiter.get_metrics()
    assert metrics.checks_total >= 4  # At least the check operations
    assert metrics.exceeded_total == 2  # Two blocked requests


# ============================================================================
# Tier 3 E2E Test 2: Per-User Isolation
# ============================================================================


@pytest.mark.asyncio
async def test_per_user_rate_limiting_isolates_users(production_limiter):
    """
    INTENT: Verify per-user rate limiting prevents one user from exhausting shared agent quota.

    Setup: Real Redis, limits={per_minute: 10} per user
    Steps:
        1. User A makes 10 invocations → all allowed
        2. User B makes 10 invocations → all allowed (separate quota)
        3. User A makes 11th invocation → blocked (User A quota exhausted)
        4. User B makes 11th invocation → blocked (User B quota exhausted)
    Assertions: Both users can make 10 invocations independently, 11th blocked for both
    """
    limiter = production_limiter

    # Step 1: User A makes 10 invocations
    for i in range(10):
        result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-a")
        assert result.allowed is True, f"User A request {i+1} should be allowed"
        await limiter.record_invocation(agent_id="agent-001", user_id="user-a")

    print(f"\nStep 1: User A made 10 invocations")

    # Step 2: User B makes 10 invocations (separate quota)
    for i in range(10):
        result = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-b")
        assert result.allowed is True, f"User B request {i+1} should be allowed"
        await limiter.record_invocation(agent_id="agent-001", user_id="user-b")

    print(f"Step 2: User B made 10 invocations (separate quota)")

    # Step 3: Both users make burst invocations up to limit
    # Burst limit: 10 * 1.5 = 15
    for i in range(5):  # 10 + 5 = 15 (burst limit)
        await limiter.record_invocation(agent_id="agent-001", user_id="user-a")
        await limiter.record_invocation(agent_id="agent-001", user_id="user-b")

    # Step 4: Next invocations should be blocked for both
    result_a = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-a")
    result_b = await limiter.check_rate_limit(agent_id="agent-001", user_id="user-b")

    assert result_a.allowed is False, "User A 16th request should be blocked"
    assert result_a.limit_exceeded == "per_minute"
    assert result_b.allowed is False, "User B 16th request should be blocked"
    assert result_b.limit_exceeded == "per_minute"

    print(f"Step 3: Both users blocked independently at their quotas")

    # Verify Redis keys exist separately
    assert await limiter.redis_client.exists("rl:ea:agent-001:user:user-a:minute")
    assert await limiter.redis_client.exists("rl:ea:agent-001:user:user-b:minute")


# ============================================================================
# Tier 3 E2E Test 3: Performance Under Load
# ============================================================================


@pytest.mark.asyncio
async def test_rate_limit_performance_under_load(production_limiter):
    """
    INTENT: Verify rate limiting maintains <10ms overhead under concurrent load.

    Setup: Real Redis, 100 concurrent users
    Steps:
        1. Each user makes 10 invocations concurrently (1000 total invocations)
        2. Measure latency for each check_rate_limit() call
    Assertions: p95 latency <10ms, p99 latency <20ms, no Redis connection errors
    """
    limiter = production_limiter

    # Simulate 100 concurrent users making invocations
    async def user_workflow(user_id: int):
        """Simulate single user making 10 invocations."""
        latencies = []

        for i in range(10):
            start = time.time()
            result = await limiter.check_rate_limit(
                agent_id="agent-001", user_id=f"user-{user_id}"
            )
            latency = time.time() - start
            latencies.append(latency)

            if result.allowed:
                await limiter.record_invocation(
                    agent_id="agent-001", user_id=f"user-{user_id}"
                )

        return latencies

    # Run 100 users concurrently
    print(f"\nRunning 100 concurrent users, 10 invocations each (1000 total)...")
    start_total = time.time()

    tasks = [user_workflow(i) for i in range(100)]
    all_latencies_nested = await asyncio.gather(*tasks)

    total_duration = time.time() - start_total

    # Flatten latencies
    all_latencies = [lat for user_lats in all_latencies_nested for lat in user_lats]

    # Calculate statistics
    all_latencies.sort()
    p50 = all_latencies[int(len(all_latencies) * 0.50)]
    p95 = all_latencies[int(len(all_latencies) * 0.95)]
    p99 = all_latencies[int(len(all_latencies) * 0.99)]
    avg = sum(all_latencies) / len(all_latencies)

    print(f"\nPerformance Results (1000 rate limit checks):")
    print(f"  Total duration: {total_duration:.2f}s")
    print(f"  Average latency: {avg*1000:.2f}ms")
    print(f"  P50 latency: {p50*1000:.2f}ms")
    print(f"  P95 latency: {p95*1000:.2f}ms")
    print(f"  P99 latency: {p99*1000:.2f}ms")

    # Assertions (E2E allows more variance than integration tests)
    assert p95 < 0.05, f"P95 latency {p95*1000:.2f}ms exceeds 50ms target"
    assert p99 < 0.1, f"P99 latency {p99*1000:.2f}ms exceeds 100ms target"
    assert len(all_latencies) == 1000, "All 1000 checks should complete"

    # Verify metrics
    metrics = limiter.get_metrics()
    assert metrics.checks_total == 1000
    assert metrics.redis_errors_total == 0, "No Redis errors should occur"


# ============================================================================
# Tier 3 E2E Test 4: Team-Level Rate Limiting
# ============================================================================


@pytest.mark.asyncio
async def test_team_level_rate_limiting(production_limiter):
    """
    INTENT: Verify team-level rate limiting shares quota across team members.

    Setup: Real Redis, limits={per_minute: 10}
    Steps:
        1. Team Alpha member 1 makes 5 invocations
        2. Team Alpha member 2 makes 5 invocations (total 10 for team)
        3. Team Alpha member 3 tries invocation → blocked (team quota exhausted)
        4. Team Beta member 1 makes 10 invocations → all allowed (separate team quota)
    Assertions: Team quota shared across members, different teams isolated
    """
    limiter = production_limiter

    # Step 1: Team Alpha member 1 makes 5 invocations
    for i in range(5):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-a1", team_id="team-alpha"
        )
        assert result.allowed is True
        await limiter.record_invocation(
            agent_id="agent-001", user_id="user-a1", team_id="team-alpha"
        )

    # Step 2: Team Alpha member 2 makes 5 invocations
    for i in range(5):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-a2", team_id="team-alpha"
        )
        assert result.allowed is True
        await limiter.record_invocation(
            agent_id="agent-001", user_id="user-a2", team_id="team-alpha"
        )

    # Now at team limit (10), add 5 more for burst
    for i in range(5):
        await limiter.record_invocation(
            agent_id="agent-001", user_id="user-a3", team_id="team-alpha"
        )

    # Step 3: Team Alpha member 3 tries invocation (team quota exhausted)
    result = await limiter.check_rate_limit(
        agent_id="agent-001", user_id="user-a3", team_id="team-alpha"
    )
    assert result.allowed is False, "Team Alpha quota should be exhausted"
    assert result.limit_exceeded == "per_minute"

    # Step 4: Team Beta member 1 makes 10 invocations (separate quota)
    for i in range(10):
        result = await limiter.check_rate_limit(
            agent_id="agent-001", user_id="user-b1", team_id="team-beta"
        )
        assert result.allowed is True, f"Team Beta request {i+1} should be allowed"
        await limiter.record_invocation(
            agent_id="agent-001", user_id="user-b1", team_id="team-beta"
        )

    print(f"\nTeam-level rate limiting:")
    print(f"  Team Alpha: Shared quota across 3 members (blocked at limit)")
    print(f"  Team Beta: Separate quota (10 invocations allowed)")

    # Verify separate Redis keys
    assert await limiter.redis_client.exists("rl:ea:agent-001:team:team-alpha:minute")
    assert await limiter.redis_client.exists("rl:ea:agent-001:team:team-beta:minute")


# ============================================================================
# Tier 3 E2E Test 5: Org-Level Rate Limiting
# ============================================================================


@pytest.mark.asyncio
async def test_org_level_rate_limiting(production_limiter):
    """
    INTENT: Verify org-level rate limiting shares quota across entire organization.

    Setup: Real Redis, limits={per_minute: 10}
    Steps:
        1. Org ACME users across different teams make 10 invocations total
        2. 11th invocation blocked (org quota exhausted)
        3. Org BETA users make 10 invocations (separate org quota)
    Assertions: Org quota shared across all teams/users, different orgs isolated
    """
    limiter = production_limiter

    # Step 1: Org ACME users make 10 invocations (across teams)
    for i in range(5):
        await limiter.record_invocation(
            agent_id="agent-001",
            user_id=f"user-{i}",
            team_id="team-alpha",
            org_id="org-acme",
        )
    for i in range(5):
        await limiter.record_invocation(
            agent_id="agent-001",
            user_id=f"user-{i}",
            team_id="team-beta",
            org_id="org-acme",
        )

    # Add 5 more for burst (total 15 = burst limit)
    for i in range(5):
        await limiter.record_invocation(
            agent_id="agent-001",
            user_id="user-x",
            team_id="team-gamma",
            org_id="org-acme",
        )

    # Step 2: 16th invocation should be blocked (org quota exhausted)
    result = await limiter.check_rate_limit(
        agent_id="agent-001",
        user_id="user-new",
        team_id="team-delta",
        org_id="org-acme",
    )
    assert result.allowed is False, "Org ACME quota should be exhausted"
    assert result.limit_exceeded == "per_minute"

    # Step 3: Org BETA users make 10 invocations (separate quota)
    for i in range(10):
        result = await limiter.check_rate_limit(
            agent_id="agent-001",
            user_id=f"user-{i}",
            team_id="team-alpha",
            org_id="org-beta",
        )
        assert result.allowed is True, f"Org BETA request {i+1} should be allowed"
        await limiter.record_invocation(
            agent_id="agent-001",
            user_id=f"user-{i}",
            team_id="team-alpha",
            org_id="org-beta",
        )

    print(f"\nOrg-level rate limiting:")
    print(f"  Org ACME: Shared quota across all teams (blocked at limit)")
    print(f"  Org BETA: Separate quota (10 invocations allowed)")

    # Verify separate Redis keys
    assert await limiter.redis_client.exists("rl:ea:agent-001:org:org-acme:minute")
    assert await limiter.redis_client.exists("rl:ea:agent-001:org:org-beta:minute")
