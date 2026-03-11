"""
Basic Monitoring Example - Demonstrates performance analytics and dashboard.

This example shows how to use the Kaizen monitoring system for:
1. Collecting metrics with MetricsCollector
2. Aggregating statistics with AnalyticsAggregator
3. Setting up alerts with AlertManager
4. Viewing real-time dashboard

Run this example:
    python examples/monitoring/basic_monitoring_example.py

Then visit http://localhost:8000 to view the dashboard.
"""

import asyncio
import random
import time

from kaizen.monitoring import (
    AlertManager,
    AnalyticsAggregator,
    MetricsCollector,
    PerformanceDashboard,
    app,
)


async def simulate_agent_execution():
    """Simulate agent execution with varying performance."""
    collector = MetricsCollector()

    for i in range(100):
        # Simulate varying latency
        latency = random.uniform(10, 150)  # 10-150ms

        # Record metric
        await collector.record_metric(
            metric_name="agent.execution.latency",
            value=latency,
            tags={"agent_type": "QA", "iteration": str(i)},
        )

        # Simulate some work
        await asyncio.sleep(0.1)


async def simulate_cache_operations():
    """Simulate cache operations across different tiers."""
    collector = MetricsCollector()

    tiers = ["hot", "warm", "cold"]
    base_latencies = {"hot": 5, "warm": 15, "cold": 50}

    for i in range(100):
        tier = random.choice(tiers)
        base = base_latencies[tier]
        latency = base + random.uniform(0, base * 0.5)  # +0-50% variance

        await collector.record_metric(
            metric_name="cache.access.latency",
            value=latency,
            tags={"tier": tier, "hit": "true"},
        )

        await asyncio.sleep(0.05)


async def simulate_signature_resolution():
    """Simulate signature resolution with occasional spikes."""
    collector = MetricsCollector()

    for i in range(100):
        # Normal: 20-40ms, Spike: 100-200ms (10% of the time)
        if random.random() < 0.1:
            latency = random.uniform(100, 200)  # Spike!
        else:
            latency = random.uniform(20, 40)  # Normal

        await collector.record_metric(
            metric_name="signature.resolution.latency", value=latency
        )

        await asyncio.sleep(0.08)


async def setup_monitoring():
    """Set up the complete monitoring stack."""
    print("Setting up monitoring system...")

    # 1. Create collector
    collector = MetricsCollector()
    print("✓ MetricsCollector initialized")

    # 2. Create aggregator
    aggregator = AnalyticsAggregator(collector)
    await aggregator.start()
    print("✓ AnalyticsAggregator started")

    # 3. Create alert manager
    alert_manager = AlertManager(aggregator)

    # Add alert rules
    alert_manager.add_rule(
        metric_name="signature.resolution.latency",
        condition="threshold",
        threshold=100.0,  # Alert if p95 > 100ms
        window="1m",
        severity="warning",
    )

    alert_manager.add_rule(
        metric_name="agent.execution.latency",
        condition="threshold",
        threshold=120.0,  # Alert if p95 > 120ms
        window="1m",
        severity="critical",
    )

    print("✓ AlertManager configured with 2 rules")

    # Optional: Add notification channel (uncomment if you have a Slack webhook)
    # alert_manager.add_notification_channel(
    #     SlackNotificationChannel(webhook_url='https://hooks.slack.com/...')
    # )

    # 4. Create dashboard
    dashboard = PerformanceDashboard(aggregator)
    print("✓ PerformanceDashboard ready")

    # 5. Start alert evaluation (in background)
    asyncio.create_task(alert_manager.evaluate_rules())
    print("✓ Alert evaluation started")

    return collector, aggregator, alert_manager, dashboard


async def main():
    """Main function to run the monitoring example."""
    print("=" * 60)
    print("Kaizen Performance Monitoring Example")
    print("=" * 60)
    print()

    # Set up monitoring
    collector, aggregator, alert_manager, dashboard = await setup_monitoring()

    print()
    print("Starting metric collection simulation...")
    print("(Run for 30 seconds to generate enough data)")
    print()

    # Start simulations in parallel
    simulations = [
        simulate_agent_execution(),
        simulate_cache_operations(),
        simulate_signature_resolution(),
    ]

    # Run simulations for 30 seconds
    try:
        await asyncio.wait_for(asyncio.gather(*simulations), timeout=30.0)
    except asyncio.TimeoutError:
        pass

    print()
    print("Metric collection complete!")
    print()

    # Give aggregator time to process final metrics
    await asyncio.sleep(2)

    # Print statistics
    print("=" * 60)
    print("Performance Statistics (1-minute window)")
    print("=" * 60)
    print()

    # Signature resolution stats
    sig_stats = aggregator.get_stats("signature.resolution.latency", "1m")
    if sig_stats:
        print("Signature Resolution Latency:")
        print(f"  Count: {sig_stats['count']}")
        print(f"  Mean: {sig_stats['mean']:.2f}ms")
        print(f"  P50: {sig_stats['median']:.2f}ms")
        print(f"  P95: {sig_stats['p95']:.2f}ms")
        print(f"  P99: {sig_stats['p99']:.2f}ms")
        print()

    # Cache access stats
    cache_stats = aggregator.get_stats("cache.access.latency", "1m")
    if cache_stats:
        print("Cache Access Latency:")
        print(f"  Count: {cache_stats['count']}")
        print(f"  Mean: {cache_stats['mean']:.2f}ms")
        print(f"  P50: {cache_stats['median']:.2f}ms")
        print(f"  P95: {cache_stats['p95']:.2f}ms")
        print()

    # Agent execution stats
    agent_stats = aggregator.get_stats("agent.execution.latency", "1m")
    if agent_stats:
        print("Agent Execution Latency:")
        print(f"  Count: {agent_stats['count']}")
        print(f"  Mean: {agent_stats['mean']:.2f}ms")
        print(f"  P50: {agent_stats['median']:.2f}ms")
        print(f"  P95: {agent_stats['p95']:.2f}ms")
        print()

    # Alert history
    alert_history = alert_manager.get_alert_history(limit=10)
    if alert_history:
        print("=" * 60)
        print(f"Alerts Triggered: {len(alert_history)}")
        print("=" * 60)
        for alert in alert_history:
            print(f"  [{alert['severity'].upper()}] {alert['metric']}")
            print(f"    Condition: {alert['condition']}")
            print(f"    Threshold: {alert['threshold']}")
            print(f"    Current: {alert['current_value']:.2f}")
            print()
    else:
        print("No alerts triggered during simulation.")

    print()
    print("=" * 60)
    print("Dashboard Running")
    print("=" * 60)
    print()
    print("The performance dashboard is now available at:")
    print("  http://localhost:8000")
    print()
    print("Endpoints:")
    print("  GET  /         - Dashboard UI")
    print("  WS   /ws       - WebSocket real-time metrics")
    print("  GET  /metrics  - Prometheus metrics export")
    print("  GET  /health   - Health check")
    print()
    print("Press Ctrl+C to stop...")
    print()

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")

    # Cleanup
    aggregator._running = False
    await asyncio.sleep(0.5)

    print("Monitoring system stopped.")


if __name__ == "__main__":
    # Run with FastAPI server
    from threading import Thread

    import uvicorn

    # Start FastAPI server in background thread
    def run_server():
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()

    # Give server time to start
    time.sleep(2)

    # Run main monitoring simulation
    asyncio.run(main())
