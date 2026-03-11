"""
External Agent Rate Limiting Demo

This script demonstrates the complete rate limiting workflow with Redis.

Prerequisites:
- Redis server running on localhost:6379
- redis package installed: pip install redis

Usage:
    python rate_limiting_demo.py
"""

import asyncio
import os

from kaizen.governance import ExternalAgentRateLimiter, RateLimitConfig, RateLimitError


async def main():
    """Demonstrate rate limiting functionality."""

    print("=" * 70)
    print("External Agent Rate Limiting Demo")
    print("=" * 70)

    # Configure rate limiter
    config = RateLimitConfig(
        requests_per_minute=5,  # Base limit
        requests_per_hour=20,
        requests_per_day=100,
        burst_multiplier=1.5,  # Allow 50% burst = 7 effective per minute
        enable_metrics=True,
    )

    # Initialize rate limiter
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/15")
    limiter = ExternalAgentRateLimiter(redis_url=redis_url, config=config)

    try:
        await limiter.initialize()
        print(f"\n✅ Connected to Redis: {redis_url}")
    except Exception as e:
        print(f"\n❌ Redis connection failed: {e}")
        print("   Make sure Redis is running: redis-server --port 6379")
        return

    print("\nConfiguration:")
    print(f"  Base limit: {config.requests_per_minute}/minute")
    print(
        f"  Burst limit: {int(config.requests_per_minute * config.burst_multiplier)}/minute"
    )
    print(f"  Hour limit: {config.requests_per_hour}/hour")
    print(f"  Day limit: {config.requests_per_day}/day")

    # Demonstration
    agent_id = "demo-agent-001"
    user_id = "demo-user-123"

    print("\n" + "=" * 70)
    print("Demo 1: Normal Usage (Under Limit)")
    print("=" * 70)

    # Make 5 requests (at base limit)
    for i in range(5):
        result = await limiter.check_rate_limit(
            agent_id=agent_id,
            user_id=user_id,
        )

        if result.allowed:
            print(f"✅ Request {i+1}: Allowed (remaining: {result.remaining})")
            await limiter.record_invocation(agent_id, user_id)
        else:
            print(f"❌ Request {i+1}: Blocked ({result.limit_exceeded})")

    print("\n" + "=" * 70)
    print("Demo 2: Burst Handling")
    print("=" * 70)

    # Make 2 more requests (within burst of 7)
    for i in range(2):
        result = await limiter.check_rate_limit(
            agent_id=agent_id,
            user_id=user_id,
        )

        if result.allowed:
            print(f"✅ Burst request {i+1}: Allowed (remaining: {result.remaining})")
            await limiter.record_invocation(agent_id, user_id)
        else:
            print(f"❌ Burst request {i+1}: Blocked ({result.limit_exceeded})")

    print("\n" + "=" * 70)
    print("Demo 3: Rate Limit Exceeded")
    print("=" * 70)

    # Try one more request (should be blocked)
    result = await limiter.check_rate_limit(
        agent_id=agent_id,
        user_id=user_id,
    )

    if result.allowed:
        print("✅ Extra request: Allowed")
    else:
        print("❌ Extra request: BLOCKED")
        print(f"   Limit exceeded: {result.limit_exceeded}")
        print(f"   Retry after: {result.retry_after_seconds} seconds")
        print(f"   Current usage: {result.current_usage}")

    print("\n" + "=" * 70)
    print("Demo 4: Metrics Tracking")
    print("=" * 70)

    metrics = limiter.get_metrics()
    if metrics:
        print(f"  Total checks: {metrics.checks_total}")
        print(f"  Total exceeded: {metrics.exceeded_total}")
        print(f"  Exceeded by limit: {metrics.exceeded_by_limit}")
        print(
            f"  Average duration: {metrics.check_duration_total / metrics.checks_total * 1000:.2f}ms"
        )
    else:
        print("  Metrics tracking disabled")

    print("\n" + "=" * 70)
    print("Demo 5: Per-User Isolation")
    print("=" * 70)

    # Different user should have separate quota
    user2_id = "demo-user-456"
    result = await limiter.check_rate_limit(
        agent_id=agent_id,
        user_id=user2_id,
    )

    if result.allowed:
        print("✅ User 2 request: Allowed (separate quota)")
        print(f"   Remaining: {result.remaining}")
        print(f"   Current usage: {result.current_usage}")
    else:
        print("❌ User 2 request: Blocked")

    # Cleanup
    await limiter.close()
    print("\n✅ Demo complete! Rate limiter connection closed.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
