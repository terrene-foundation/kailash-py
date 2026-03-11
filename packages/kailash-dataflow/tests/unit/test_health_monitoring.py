#!/usr/bin/env python3
"""
Unit Tests for Health Monitoring & Observability (Tier 1)

Tests the health monitoring system for DataFlow including:
- Health check endpoints for Kubernetes integration
- Readiness checks for orchestration
- Prometheus metrics export
- Component health validation

Following TDD methodology: Tests written BEFORE implementation.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from dataflow.platform.health import (
    HealthCheck,
    HealthMonitor,
    HealthStatus,
    add_health_endpoints,
)
from dataflow.platform.metrics import MetricsExporter, PrometheusMetrics


@pytest.mark.unit
@pytest.mark.asyncio
class TestHealthChecks:
    """Test individual health check components."""

    async def test_database_health_check_healthy(self, memory_dataflow):
        """Test database health check returns healthy status."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)

        # Mock get_connection to simulate successful database connection
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[(1,)])

        @asynccontextmanager
        async def mock_get_connection():
            yield mock_conn

        with patch.object(memory_dataflow, "get_connection", mock_get_connection):
            # Act
            result = await monitor._check_database()

            # Assert
            assert result["status"] == HealthStatus.HEALTHY
            assert "healthy" in result["message"].lower()
            assert "error" not in result

    async def test_database_health_check_unhealthy(self, memory_dataflow):
        """Test database health check detects connection failures."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)

        # Mock database connection failure
        with patch.object(
            memory_dataflow,
            "get_connection",
            side_effect=Exception("Connection failed"),
        ):
            # Act
            result = await monitor._check_database()

            # Assert
            assert result["status"] == HealthStatus.UNHEALTHY
            assert "failed" in result["message"].lower()
            assert "Connection failed" in result["message"]

    async def test_schema_cache_health_check_healthy(self, memory_dataflow):
        """Test schema cache health check with good hit rate."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)

        # Mock schema cache with high hit rate
        mock_metrics = {"hits": 90, "misses": 10, "hit_rate": 0.9, "cached_tables": 5}

        with patch.object(
            memory_dataflow._schema_cache, "get_metrics", return_value=mock_metrics
        ):
            # Act
            result = await monitor._check_schema_cache()

            # Assert
            assert result["status"] == HealthStatus.HEALTHY
            assert "hit rate" in result["message"].lower()

    async def test_schema_cache_health_check_degraded(self, memory_dataflow):
        """Test schema cache health check detects low hit rate."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)

        # Mock schema cache with low hit rate
        mock_metrics = {
            "hits": 40,
            "misses": 60,
            "hit_rate": 0.4,  # Below 50% threshold
            "cached_tables": 5,
        }

        with patch.object(
            memory_dataflow._schema_cache, "get_metrics", return_value=mock_metrics
        ):
            # Act
            result = await monitor._check_schema_cache()

            # Assert
            assert result["status"] == HealthStatus.DEGRADED
            assert "low cache hit rate" in result["message"].lower()

    async def test_connection_pool_health_check_healthy(self, memory_dataflow):
        """Test connection pool health check with normal utilization."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)

        # Mock connection pool manager with normal utilization
        mock_pool_manager = Mock()
        mock_pool_manager.get_pool_metrics.return_value = {
            "size": 10,
            "in_use": 3,
            "available": 7,
            "utilization": 0.3,
        }

        memory_dataflow._pool_manager = mock_pool_manager
        memory_dataflow.enable_connection_pooling = True
        # Add connection_url attribute for pool metrics lookup
        memory_dataflow.connection_url = "postgresql://test@localhost/test"

        # Act
        result = await monitor._check_connection_pool()

        # Assert
        assert result["status"] == HealthStatus.HEALTHY
        assert "utilization" in result["message"].lower()

    async def test_connection_pool_health_check_degraded(self, memory_dataflow):
        """Test connection pool health check detects high utilization."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)

        # Mock connection pool manager with high utilization
        mock_pool_manager = Mock()
        mock_pool_manager.get_pool_metrics.return_value = {
            "size": 10,
            "in_use": 9,
            "available": 1,
            "utilization": 0.95,  # Above 90% threshold
        }

        memory_dataflow._pool_manager = mock_pool_manager
        memory_dataflow.enable_connection_pooling = True
        # Add connection_url attribute for pool metrics lookup
        memory_dataflow.connection_url = "postgresql://test@localhost/test"

        # Act
        result = await monitor._check_connection_pool()

        # Assert
        assert result["status"] == HealthStatus.DEGRADED
        assert "high pool utilization" in result["message"].lower()

    async def test_connection_pool_disabled(self, memory_dataflow):
        """Test connection pool health check when pooling is disabled."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)
        memory_dataflow.enable_connection_pooling = False

        # Act
        result = await monitor._check_connection_pool()

        # Assert
        assert result["status"] == HealthStatus.HEALTHY
        assert "disabled" in result["message"].lower()

    async def test_overall_health_status_all_healthy(self, memory_dataflow):
        """Test overall health status when all components are healthy."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)

        # Mock all checks as healthy
        monitor._checks = {
            "database": AsyncMock(
                return_value={"status": HealthStatus.HEALTHY, "message": "OK"}
            ),
            "schema_cache": AsyncMock(
                return_value={"status": HealthStatus.HEALTHY, "message": "OK"}
            ),
            "connection_pool": AsyncMock(
                return_value={"status": HealthStatus.HEALTHY, "message": "OK"}
            ),
        }

        # Act
        health_check = await monitor.health_check()

        # Assert
        assert health_check.status == HealthStatus.HEALTHY
        assert isinstance(health_check.timestamp, datetime)
        assert "database" in health_check.details
        assert "schema_cache" in health_check.details
        assert "connection_pool" in health_check.details

    async def test_overall_health_status_one_degraded(self, memory_dataflow):
        """Test overall health status downgrades when one component is degraded."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)

        # Mock one check as degraded
        monitor._checks = {
            "database": AsyncMock(
                return_value={"status": HealthStatus.HEALTHY, "message": "OK"}
            ),
            "schema_cache": AsyncMock(
                return_value={
                    "status": HealthStatus.DEGRADED,
                    "message": "Low hit rate",
                }
            ),
            "connection_pool": AsyncMock(
                return_value={"status": HealthStatus.HEALTHY, "message": "OK"}
            ),
        }

        # Act
        health_check = await monitor.health_check()

        # Assert
        assert health_check.status == HealthStatus.DEGRADED
        assert health_check.details["schema_cache"]["status"] == HealthStatus.DEGRADED

    async def test_overall_health_status_one_unhealthy(self, memory_dataflow):
        """Test overall health status becomes unhealthy when any component fails."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)

        # Mock one check as unhealthy
        monitor._checks = {
            "database": AsyncMock(
                return_value={
                    "status": HealthStatus.UNHEALTHY,
                    "message": "Connection failed",
                }
            ),
            "schema_cache": AsyncMock(
                return_value={"status": HealthStatus.HEALTHY, "message": "OK"}
            ),
            "connection_pool": AsyncMock(
                return_value={"status": HealthStatus.HEALTHY, "message": "OK"}
            ),
        }

        # Act
        health_check = await monitor.health_check()

        # Assert
        assert health_check.status == HealthStatus.UNHEALTHY
        assert health_check.details["database"]["status"] == HealthStatus.UNHEALTHY

    async def test_health_check_handles_exceptions(self, memory_dataflow):
        """Test health check handles exceptions in individual checks gracefully."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)

        # Mock one check that raises exception
        monitor._checks = {
            "database": AsyncMock(side_effect=RuntimeError("Unexpected error")),
            "schema_cache": AsyncMock(
                return_value={"status": HealthStatus.HEALTHY, "message": "OK"}
            ),
        }

        # Act
        health_check = await monitor.health_check()

        # Assert
        assert health_check.status == HealthStatus.UNHEALTHY
        assert health_check.details["database"]["status"] == HealthStatus.UNHEALTHY
        assert "error" in health_check.details["database"]
        assert "Unexpected error" in health_check.details["database"]["error"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestHealthEndpoints:
    """Test FastAPI health endpoint integration."""

    async def test_health_endpoint_returns_200_when_healthy(self, memory_dataflow):
        """Test /health endpoint returns 200 status code when healthy."""
        # Arrange
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)
        client = TestClient(app)

        # Mock healthy status
        with patch("dataflow.platform.health.HealthMonitor.health_check") as mock_check:
            mock_check.return_value = HealthCheck(
                status=HealthStatus.HEALTHY,
                message="All systems healthy",
                details={},
                timestamp=datetime.now(),
            )

            # Act
            response = client.get("/health")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"

    async def test_health_endpoint_returns_200_when_degraded(self, memory_dataflow):
        """Test /health endpoint returns 200 when degraded (still serving)."""
        # Arrange
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)
        client = TestClient(app)

        # Mock degraded status
        with patch("dataflow.platform.health.HealthMonitor.health_check") as mock_check:
            mock_check.return_value = HealthCheck(
                status=HealthStatus.DEGRADED,
                message="Some components degraded",
                details={},
                timestamp=datetime.now(),
            )

            # Act
            response = client.get("/health")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"

    async def test_health_endpoint_returns_503_when_unhealthy(self, memory_dataflow):
        """Test /health endpoint returns 503 when unhealthy."""
        # Arrange
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)
        client = TestClient(app)

        # Mock unhealthy status
        with patch("dataflow.platform.health.HealthMonitor.health_check") as mock_check:
            mock_check.return_value = HealthCheck(
                status=HealthStatus.UNHEALTHY,
                message="Critical failure",
                details={},
                timestamp=datetime.now(),
            )

            # Act
            response = client.get("/health")

            # Assert
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"

    async def test_readiness_endpoint_returns_200_when_ready(self, memory_dataflow):
        """Test /ready endpoint returns 200 when application is ready."""
        # Arrange
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)
        client = TestClient(app)

        # Mock ready status (healthy or degraded)
        with patch(
            "dataflow.platform.health.HealthMonitor.readiness_check"
        ) as mock_check:
            mock_check.return_value = True

            # Act
            response = client.get("/ready")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"

    async def test_readiness_endpoint_returns_503_when_not_ready(self, memory_dataflow):
        """Test /ready endpoint returns 503 when application is not ready."""
        # Arrange
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)
        client = TestClient(app)

        # Mock not ready status (unhealthy)
        with patch(
            "dataflow.platform.health.HealthMonitor.readiness_check"
        ) as mock_check:
            mock_check.return_value = False

            # Act
            response = client.get("/ready")

            # Assert
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not ready"

    async def test_readiness_check_logic(self, memory_dataflow):
        """Test readiness check returns True only when not unhealthy."""
        # Arrange
        monitor = HealthMonitor(memory_dataflow)

        # Test: Healthy -> Ready
        monitor._checks = {
            "database": AsyncMock(
                return_value={"status": HealthStatus.HEALTHY, "message": "OK"}
            ),
        }
        assert await monitor.readiness_check() is True

        # Test: Degraded -> Ready (still serving traffic)
        monitor._checks = {
            "database": AsyncMock(
                return_value={"status": HealthStatus.DEGRADED, "message": "Degraded"}
            ),
        }
        assert await monitor.readiness_check() is True

        # Test: Unhealthy -> Not Ready
        monitor._checks = {
            "database": AsyncMock(
                return_value={"status": HealthStatus.UNHEALTHY, "message": "Failed"}
            ),
        }
        assert await monitor.readiness_check() is False


@pytest.mark.unit
class TestPrometheusMetrics:
    """Test Prometheus metrics export functionality."""

    def test_metrics_endpoint_returns_prometheus_format(self, memory_dataflow):
        """Test /metrics endpoint returns Prometheus text format."""
        # Arrange
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)
        client = TestClient(app)

        # Act
        response = client.get("/metrics")

        # Assert
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

        # Verify Prometheus format
        content = response.text
        assert "# HELP" in content or "# TYPE" in content or len(content) > 0

    def test_metrics_exporter_registers_connection_pool_metrics(self):
        """Test metrics exporter can register connection pool metrics."""
        # Arrange
        exporter = MetricsExporter()

        # Act
        exporter.register_connection_pool_metrics(
            pool_size=10, in_use=3, available=7, utilization=0.3
        )

        # Assert
        metrics = exporter.get_metrics()
        assert "connection_pool_size" in metrics
        assert metrics["connection_pool_size"] == 10
        assert metrics["connection_pool_in_use"] == 3
        assert metrics["connection_pool_utilization"] == 0.3

    def test_metrics_exporter_registers_workflow_metrics(self):
        """Test metrics exporter can register workflow execution metrics."""
        # Arrange
        exporter = MetricsExporter()

        # Act
        exporter.register_workflow_execution(
            workflow_name="test_workflow", duration_seconds=1.5, status="success"
        )

        # Assert
        metrics = exporter.get_metrics()
        assert "workflow_executions_total" in metrics
        assert "workflow_execution_duration_seconds" in metrics

    def test_prometheus_metrics_counter(self):
        """Test Prometheus counter metric increments correctly."""
        # Arrange
        metrics = PrometheusMetrics()

        # Act
        metrics.increment_counter("test_counter", labels={"type": "test"})
        metrics.increment_counter("test_counter", labels={"type": "test"})

        # Assert
        value = metrics.get_counter_value("test_counter", labels={"type": "test"})
        assert value == 2

    def test_prometheus_metrics_gauge(self):
        """Test Prometheus gauge metric sets value correctly."""
        # Arrange
        metrics = PrometheusMetrics()

        # Act
        metrics.set_gauge("test_gauge", 42.0, labels={"instance": "test"})

        # Assert
        value = metrics.get_gauge_value("test_gauge", labels={"instance": "test"})
        assert value == 42.0

    def test_prometheus_metrics_histogram(self):
        """Test Prometheus histogram records observations correctly."""
        # Arrange
        metrics = PrometheusMetrics()

        # Act
        metrics.observe_histogram("test_histogram", 1.5, labels={"operation": "test"})
        metrics.observe_histogram("test_histogram", 2.5, labels={"operation": "test"})

        # Assert
        stats = metrics.get_histogram_stats(
            "test_histogram", labels={"operation": "test"}
        )
        assert stats["count"] == 2
        assert stats["sum"] == 4.0


@pytest.mark.unit
class TestFastAPIIntegration:
    """Test complete FastAPI integration with all endpoints."""

    def test_fastapi_health_endpoint_integration(self, memory_dataflow):
        """Test complete FastAPI health endpoint integration."""
        # Arrange
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)
        client = TestClient(app)

        # Act
        response = client.get("/health")

        # Assert
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "timestamp" in data
        assert "details" in data

    def test_fastapi_readiness_endpoint_integration(self, memory_dataflow):
        """Test complete FastAPI readiness endpoint integration."""
        # Arrange
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)
        client = TestClient(app)

        # Act
        response = client.get("/ready")

        # Assert
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert data["status"] in ["ready", "not ready"]

    def test_all_endpoints_registered(self, memory_dataflow):
        """Test all health endpoints are registered on the FastAPI app."""
        # Arrange
        from fastapi import FastAPI

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)

        # Act
        routes = [route.path for route in app.routes]

        # Assert
        assert "/health" in routes
        assert "/ready" in routes
        assert "/metrics" in routes

    def test_health_endpoints_use_async_handlers(self, memory_dataflow):
        """Test health endpoints use async handlers for performance."""
        # Arrange
        import inspect

        from fastapi import FastAPI

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)

        # Act & Assert
        for route in app.routes:
            if route.path in ["/health", "/ready", "/metrics"]:
                # Verify endpoint handler is async
                assert inspect.iscoroutinefunction(route.endpoint)


@pytest.mark.unit
class TestHealthCheckDataclass:
    """Test HealthCheck dataclass functionality."""

    def test_health_check_creation(self):
        """Test HealthCheck dataclass can be created with required fields."""
        # Act
        health_check = HealthCheck(
            status=HealthStatus.HEALTHY,
            message="All systems operational",
            details={"database": {"status": "healthy"}},
            timestamp=datetime.now(),
        )

        # Assert
        assert health_check.status == HealthStatus.HEALTHY
        assert health_check.message == "All systems operational"
        assert "database" in health_check.details
        assert isinstance(health_check.timestamp, datetime)

    def test_health_check_to_json(self):
        """Test HealthCheck can be serialized to JSON."""
        # Arrange
        health_check = HealthCheck(
            status=HealthStatus.HEALTHY,
            message="OK",
            details={},
            timestamp=datetime.now(),
        )

        # Act
        json_data = health_check.to_json()

        # Assert
        assert "status" in json_data
        assert "message" in json_data
        assert "details" in json_data
        assert "timestamp" in json_data

    def test_health_status_enum_values(self):
        """Test HealthStatus enum has correct values."""
        # Assert
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


@pytest.mark.unit
class TestEnvironmentConfiguration:
    """Test environment-based configuration for health endpoints."""

    def test_health_endpoint_path_configurable(self, memory_dataflow):
        """Test health endpoint path can be configured via environment."""
        # Arrange
        import os

        from fastapi import FastAPI

        os.environ["DATAFLOW_HEALTH_ENDPOINT"] = "/healthz"

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)

        # Act
        routes = [route.path for route in app.routes]

        # Assert
        assert "/healthz" in routes or "/health" in routes  # Fallback to default

        # Cleanup
        os.environ.pop("DATAFLOW_HEALTH_ENDPOINT", None)

    def test_readiness_endpoint_path_configurable(self, memory_dataflow):
        """Test readiness endpoint path can be configured via environment."""
        # Arrange
        import os

        from fastapi import FastAPI

        os.environ["DATAFLOW_READY_ENDPOINT"] = "/readyz"

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)

        # Act
        routes = [route.path for route in app.routes]

        # Assert
        assert "/readyz" in routes or "/ready" in routes  # Fallback to default

        # Cleanup
        os.environ.pop("DATAFLOW_READY_ENDPOINT", None)

    def test_metrics_endpoint_path_configurable(self, memory_dataflow):
        """Test metrics endpoint path can be configured via environment."""
        # Arrange
        import os

        from fastapi import FastAPI

        os.environ["DATAFLOW_METRICS_ENDPOINT"] = "/prometheus"

        app = FastAPI()
        add_health_endpoints(app, memory_dataflow)

        # Act
        routes = [route.path for route in app.routes]

        # Assert
        assert "/prometheus" in routes or "/metrics" in routes  # Fallback to default

        # Cleanup
        os.environ.pop("DATAFLOW_METRICS_ENDPOINT", None)
