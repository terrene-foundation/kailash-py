"""Example: Fixing gateway startup sleep pattern.

This example shows how to replace a 3-second sleep with proper health check polling.
"""


# BEFORE: Fixed 3-second sleep
def test_gateway_startup_before():
    """Original test with fixed sleep."""
    import threading
    import time

    import httpx

    # Start gateway in background thread
    gateway = create_gateway()
    server_thread = threading.Thread(
        target=lambda: gateway.run(host="localhost", port=8080), daemon=True
    )
    server_thread.start()

    # BAD: Fixed sleep hoping gateway is ready
    time.sleep(3)

    # Verify gateway is running
    response = httpx.get("http://localhost:8080/health")
    assert response.status_code == 200


# AFTER: Condition-based waiting (Edge Coordination Pattern)
def test_gateway_startup_after():
    """Improved test with condition-based waiting."""
    import threading
    import time
    from datetime import datetime

    import httpx

    # Start gateway in background thread
    gateway = create_gateway()
    server_thread = threading.Thread(
        target=lambda: gateway.run(host="localhost", port=8080), daemon=True
    )
    server_thread.start()

    # GOOD: Wait for gateway to be healthy with timeout
    start_time = datetime.now()
    gateway_ready = False

    while (datetime.now() - start_time).total_seconds() < 10.0:
        try:
            response = httpx.get("http://localhost:8080/health", timeout=1.0)
            if response.status_code == 200:
                gateway_ready = True
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            # Gateway not ready yet
            pass

        time.sleep(0.1)  # Small polling interval

    assert gateway_ready, "Gateway failed to start within 10 seconds"


# AFTER: Using wait_conditions helper
async def test_gateway_startup_with_helper():
    """Best practice using helper utilities."""
    import threading

    from tests.utils.wait_conditions import wait_for_http_health

    # Start gateway in background thread
    gateway = create_gateway()
    server_thread = threading.Thread(
        target=lambda: gateway.run(host="localhost", port=8080), daemon=True
    )
    server_thread.start()

    # BEST: Use helper function
    await wait_for_http_health(
        url="http://localhost:8080/health",
        timeout=10.0,
        interval=0.1,
        expected_status=200,
    )


# Example: Fixing Docker container waits
async def test_docker_services_after():
    """Replace 15-second Docker sleep with health checks."""
    from tests.utils.wait_conditions import wait_for_condition, wait_for_port

    with DockerCompose("docker-compose.yml") as compose:
        # Instead of: time.sleep(15)

        # Wait for specific services to be ready
        await wait_for_port("localhost", 6379, timeout=30.0)  # Redis
        await wait_for_port("localhost", 5432, timeout=30.0)  # PostgreSQL

        # Or wait for container health status
        await wait_for_condition(
            lambda: compose.get_service("redis").attrs["State"]["Health"]["Status"]
            == "healthy",
            timeout=30.0,
            error_message="Redis container failed health check",
        )

        # Now services are ready
        run_tests()


# Example: Fixing cache TTL waits
async def test_cache_expiration_after():
    """Replace long TTL waits with shorter cycles."""
    from tests.utils.wait_conditions import wait_for_condition

    cache = create_cache_node()

    # Instead of:
    # cache.set("key", "value", ttl=1)
    # time.sleep(1.1)

    # Use shorter TTL for tests
    await cache.set("key", "value", ttl=0.1)

    # Wait for expiration with condition
    await wait_for_condition(
        lambda: cache.get("key") is None,
        timeout=0.5,
        interval=0.02,
        error_message="Cache key did not expire",
    )


# Example: Fixing monitoring cycle waits
async def test_monitoring_detection_after():
    """Replace monitoring cycle sleep with event detection."""
    import asyncio
    from datetime import datetime

    monitor = create_transaction_monitor()
    monitor.start_monitoring()

    # Instead of: time.sleep(3.0)

    # Wait for monitoring to detect issues
    start_time = datetime.now()
    detected = False

    while (datetime.now() - start_time).total_seconds() < 5.0:
        if monitor.get_detection_count() > 0:
            detected = True
            break
        await asyncio.sleep(0.05)

    assert detected, "Monitor failed to detect issues within timeout"


# Performance comparison
def performance_comparison():
    """Show time savings from fixing sleeps."""

    # BEFORE: Fixed sleeps
    # - Gateway startup: 3 seconds
    # - Docker services: 15 seconds
    # - Cache TTL test: 1.1 seconds
    # - Monitoring: 3 seconds
    # Total: 22.1 seconds of waiting

    # AFTER: Condition-based
    # - Gateway startup: ~0.2 seconds (actual startup time)
    # - Docker services: ~5 seconds (actual startup time)
    # - Cache TTL test: ~0.15 seconds
    # - Monitoring: ~0.1 seconds (immediate detection)
    # Total: ~5.45 seconds

    # Savings: 16.65 seconds per test run!
    print("Time saved: 16.65 seconds (75% reduction)")


if __name__ == "__main__":
    # Example implementations
    performance_comparison()
