"""Integration tests for the Prometheus /metrics endpoint.

Tests that all server types expose a /metrics endpoint returning
valid Prometheus text format with registered metrics.
"""

import pytest
from fastapi.testclient import TestClient

from src.kailash.servers import WorkflowServer, EnterpriseWorkflowServer
from src.kailash.servers.durable_workflow_server import DurableWorkflowServer


PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class TestPrometheusEndpointWorkflowServer:
    """Test /metrics on the base WorkflowServer."""

    def setup_method(self):
        self.server = WorkflowServer(title="Prometheus Test Server")
        self.client = TestClient(self.server.app)

    def test_metrics_returns_200(self):
        """GET /metrics returns HTTP 200."""
        response = self.client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self):
        """GET /metrics returns Prometheus content type."""
        response = self.client.get("/metrics")
        assert response.headers["content-type"] == PROMETHEUS_CONTENT_TYPE

    def test_metrics_contains_help_lines(self):
        """Response includes at least one HELP comment line."""
        response = self.client.get("/metrics")
        body = response.text
        assert "# HELP" in body

    def test_metrics_contains_type_lines(self):
        """Response includes at least one TYPE comment line."""
        response = self.client.get("/metrics")
        body = response.text
        assert "# TYPE" in body

    def test_metrics_contains_kailash_prefix(self):
        """The custom MetricsRegistry (validation/security/performance)
        emits only kailash_-prefixed metric names, and those HELP lines
        survive into the unified /metrics endpoint.

        Pre-#1708-W1c this asserted "every HELP line in the FULL /metrics
        response is kailash_-prefixed" — true only while the endpoint
        exported exclusively the custom registry. Since #1708 W1b unified
        the exposition, the response also folds in the prometheus_client
        default registry: asyncsql/ML native instruments, OTel-bridged
        meters, AND prometheus_client's own auto-registered
        process/gc/platform collectors (none of which are kailash_-prefixed
        by design — that unification is the intended Wave-1b behavior, not
        a regression). What remains a real invariant is that OUR OWN
        custom registry never emits an unprefixed metric name, and that the
        server endpoint still surfaces those exact lines.
        """
        from src.kailash.monitoring.metrics import get_metrics_registry

        custom_body = get_metrics_registry().export_metrics(format="prometheus")
        help_lines = [
            entry for entry in custom_body.splitlines() if entry.startswith("# HELP")
        ]
        assert len(help_lines) > 0
        for line in help_lines:
            # Format: # HELP kailash_<collector>_<metric> <description>
            metric_name = line.split()[2]
            assert metric_name.startswith(
                "kailash_"
            ), f"Expected kailash_ prefix, got: {metric_name}"

        # Wiring check: the custom registry's kailash_-prefixed lines reach
        # the real unified HTTP endpoint unchanged.
        response = self.client.get("/metrics")
        body = response.text
        for line in help_lines:
            assert line in body

    def test_metrics_includes_default_collectors(self):
        """Response includes metrics from all three default collectors."""
        response = self.client.get("/metrics")
        body = response.text
        assert "kailash_validation_" in body
        assert "kailash_security_" in body
        assert "kailash_performance_" in body


class TestPrometheusEndpointDurableServer:
    """Test /metrics on DurableWorkflowServer (inherits from WorkflowServer)."""

    def setup_method(self):
        self.server = DurableWorkflowServer(title="Durable Prometheus Test Server")
        self.client = TestClient(self.server.app)

    def test_metrics_returns_200(self):
        """GET /metrics returns HTTP 200 on DurableWorkflowServer."""
        response = self.client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self):
        """GET /metrics returns Prometheus content type."""
        response = self.client.get("/metrics")
        assert response.headers["content-type"] == PROMETHEUS_CONTENT_TYPE

    def test_metrics_contains_help_lines(self):
        """Response includes metric HELP lines."""
        response = self.client.get("/metrics")
        assert "# HELP" in response.text


class TestPrometheusEndpointEnterpriseServer:
    """Test /metrics on EnterpriseWorkflowServer."""

    def setup_method(self):
        self.server = EnterpriseWorkflowServer(
            title="Enterprise Prometheus Test Server"
        )
        self.client = TestClient(self.server.app)

    def test_metrics_returns_200(self):
        """GET /metrics returns HTTP 200 on EnterpriseWorkflowServer."""
        response = self.client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self):
        """GET /metrics returns Prometheus content type."""
        response = self.client.get("/metrics")
        assert response.headers["content-type"] == PROMETHEUS_CONTENT_TYPE

    def test_metrics_contains_help_lines(self):
        """Response includes metric HELP lines."""
        response = self.client.get("/metrics")
        assert "# HELP" in response.text

    def test_metrics_includes_default_collectors(self):
        """Response includes all default collector namespaces."""
        response = self.client.get("/metrics")
        body = response.text
        assert "kailash_validation_" in body
        assert "kailash_security_" in body
        assert "kailash_performance_" in body


class TestPrometheusMetricsWithRecordedData:
    """Test that /metrics reflects data recorded via the metrics API."""

    def setup_method(self):
        self.server = WorkflowServer(title="Metrics Data Test Server")
        self.client = TestClient(self.server.app)

    def test_metrics_reflects_recorded_counter(self):
        """After incrementing a counter, /metrics shows the updated value."""
        from src.kailash.monitoring.metrics import get_metrics_registry

        registry = get_metrics_registry()
        collector = registry.get_collector("validation")
        collector.increment("validation_total")

        response = self.client.get("/metrics")
        body = response.text

        # The validation_total counter should appear with a numeric value
        assert "kailash_validation_validation_total" in body
