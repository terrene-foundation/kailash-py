"""Unit tests for TODO-030: Edge Location real HTTP health check."""

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.edge.location import (
    EdgeCapabilities,
    EdgeLocation,
    EdgeMetrics,
    EdgeRegion,
    EdgeStatus,
    GeographicCoordinates,
)


@pytest.fixture
def edge_location():
    """Create an edge location for testing."""
    return EdgeLocation(
        location_id="test-1",
        name="Test Edge",
        region=EdgeRegion.US_EAST,
        coordinates=GeographicCoordinates(39.0, -77.5),
        capabilities=EdgeCapabilities(
            cpu_cores=8,
            memory_gb=32,
            storage_gb=500,
        ),
        endpoint_url="http://test-edge.local:8080",
    )


class _FakeResponse:
    """Minimal aiohttp response mock."""

    def __init__(self, status, json_data=None):
        self.status = status
        self._json_data = json_data

    async def json(self):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeSession:
    """Fake aiohttp.ClientSession for unit tests."""

    def __init__(self, response):
        self._response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class TestEdgeHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_success_updates_metrics(self, edge_location):
        """Successful health check should update metrics and reset failures."""
        edge_location.health_check_failures = 2
        response = _FakeResponse(
            200,
            {
                "cpu_utilization": 0.45,
                "memory_utilization": 0.60,
                "error_rate": 0.01,
                "uptime_percentage": 99.9,
            },
        )
        session = _FakeSession(response)

        with patch("aiohttp.ClientSession", return_value=session):
            result = await edge_location.health_check()

        assert result is True
        assert edge_location.health_check_failures == 0
        assert edge_location.metrics.cpu_utilization == 0.45
        assert edge_location.metrics.memory_utilization == 0.60
        assert edge_location.metrics.error_rate == 0.01
        assert edge_location.metrics.uptime_percentage == 99.9
        assert edge_location.metrics.collected_at is not None

    @pytest.mark.asyncio
    async def test_health_check_non_200(self, edge_location):
        """Non-200 response should increment failure counter."""
        edge_location.health_check_failures = 0
        response = _FakeResponse(503, None)
        session = _FakeSession(response)

        with patch("aiohttp.ClientSession", return_value=session):
            result = await edge_location.health_check()

        assert result is False
        assert edge_location.health_check_failures == 1

    @pytest.mark.asyncio
    async def test_health_check_degrades_after_failures(self, edge_location):
        """Status degrades to DEGRADED after >3 consecutive failures."""
        edge_location.health_check_failures = 3
        response = _FakeResponse(500)
        session = _FakeSession(response)

        with patch("aiohttp.ClientSession", return_value=session):
            result = await edge_location.health_check()

        assert result is False
        assert edge_location.health_check_failures == 4
        assert edge_location.status == EdgeStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_health_check_exception_increments_failure(self, edge_location):
        """Network exception should increment failure counter."""
        edge_location.health_check_failures = 0

        with patch(
            "aiohttp.ClientSession",
            side_effect=Exception("Connection refused"),
        ):
            result = await edge_location.health_check()

        assert result is False
        assert edge_location.health_check_failures == 1

    @pytest.mark.asyncio
    async def test_health_check_configurable_timeout(self, edge_location):
        """Timeout parameter should be passed to aiohttp."""
        response = _FakeResponse(200, {})

        with (
            patch("aiohttp.ClientTimeout") as mock_timeout,
            patch(
                "aiohttp.ClientSession",
                return_value=_FakeSession(response),
            ),
        ):
            await edge_location.health_check(timeout=2.0)
            mock_timeout.assert_called_once_with(total=2.0)

    @pytest.mark.asyncio
    async def test_health_check_correct_url(self, edge_location):
        """Should hit /health at the endpoint URL."""
        response = _FakeResponse(200, {})
        session = _FakeSession(response)

        with patch("aiohttp.ClientSession", return_value=session):
            await edge_location.health_check()

        assert len(session.calls) == 1
        assert session.calls[0][1] == "http://test-edge.local:8080/health"

    @pytest.mark.asyncio
    async def test_health_check_partial_metrics(self, edge_location):
        """Only metrics present in response should be updated."""
        edge_location.metrics.cpu_utilization = 0.5
        edge_location.metrics.memory_utilization = 0.5

        response = _FakeResponse(200, {"cpu_utilization": 0.75})
        session = _FakeSession(response)

        with patch("aiohttp.ClientSession", return_value=session):
            await edge_location.health_check()

        assert edge_location.metrics.cpu_utilization == 0.75
        # Memory should remain unchanged since not in response
        assert edge_location.metrics.memory_utilization == 0.5

    @pytest.mark.asyncio
    async def test_health_check_resets_failure_on_success(self, edge_location):
        """Successful check should reset failure counter even if it was high."""
        edge_location.health_check_failures = 5
        edge_location.status = EdgeStatus.DEGRADED  # Already degraded

        response = _FakeResponse(200, {})
        session = _FakeSession(response)

        with patch("aiohttp.ClientSession", return_value=session):
            result = await edge_location.health_check()

        assert result is True
        assert edge_location.health_check_failures == 0
        # Note: status doesn't auto-recover from health_check alone
        # (that's handled by update_metrics)

    @pytest.mark.asyncio
    async def test_health_check_fallback_without_aiohttp(self, edge_location):
        """Should fall back gracefully if aiohttp is not importable."""
        # Simulate aiohttp not being available
        with patch.dict("sys.modules", {"aiohttp": None}):
            with patch("builtins.__import__", side_effect=ImportError("no aiohttp")):
                # The method catches ImportError internally
                result = await edge_location.health_check()

        # Should gracefully handle and return True as a fallback
        assert result is True
        assert edge_location.health_check_failures == 0
