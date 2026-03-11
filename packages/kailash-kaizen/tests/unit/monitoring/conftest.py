"""Test fixtures for monitoring tests."""

import asyncio

import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def reset_metrics_collector():
    """Reset MetricsCollector singleton between tests."""
    # Clean up before test
    from kaizen.monitoring.metrics_collector import MetricsCollector

    # Reset singleton instance
    MetricsCollector._instance = None

    # Give async tasks time to clean up
    await asyncio.sleep(0.01)

    # Run test
    yield

    # Clean up after test
    MetricsCollector._instance = None
    await asyncio.sleep(0.01)


@pytest_asyncio.fixture
async def fresh_collector():
    """Provide a fresh MetricsCollector for each test."""
    from kaizen.monitoring.metrics_collector import MetricsCollector

    # Reset singleton
    MetricsCollector._instance = None

    # Create fresh collector
    collector = MetricsCollector()

    yield collector

    # Clean up
    MetricsCollector._instance = None
    await asyncio.sleep(0.01)


@pytest_asyncio.fixture
async def fresh_aggregator(fresh_collector):
    """Provide a fresh AnalyticsAggregator for each test."""
    from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator

    aggregator = AnalyticsAggregator(fresh_collector)

    yield aggregator

    # Stop aggregator if running
    if aggregator._running:
        aggregator._running = False
        if aggregator._worker_task:
            try:
                await asyncio.wait_for(aggregator._worker_task, timeout=1.0)
            except asyncio.TimeoutError:
                pass

    await asyncio.sleep(0.01)


@pytest_asyncio.fixture
async def fresh_alert_manager(fresh_aggregator):
    """Provide a fresh AlertManager for each test."""
    from kaizen.monitoring.alert_manager import AlertManager

    alert_manager = AlertManager(fresh_aggregator)

    yield alert_manager

    await asyncio.sleep(0.01)
