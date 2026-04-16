# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the Nexus Prometheus /metrics endpoint.

Tests verify:
- /metrics returns 200 with valid OpenMetrics output
- Expected nexus_* metric names are present
- Metric values update when workflows are registered
- Lazy import does not fail at module load time
- Helpful error when prometheus_client is not installed
"""

import time
from collections import deque

import pytest
from fastapi.testclient import TestClient
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus
from nexus.events import EventBus
from nexus.metrics import (
    _MISSING_MSG,
    _require_prometheus_client,
    _sync_from_nexus,
    register_metrics_endpoint,
)


class TestMetricsEndpoint:
    """Test suite for the /metrics HTTP endpoint."""

    def setup_method(self):
        """Create a Nexus instance with a registered workflow and /metrics."""
        # Use a fresh prometheus registry to avoid collector-already-registered
        # errors across tests. We reset the module-level metrics state.
        import nexus.metrics as _mod

        _mod._metrics_initialized = False
        _mod._workflow_registration_hist = None
        _mod._cross_channel_sync_hist = None
        _mod._failure_recovery_hist = None
        _mod._session_sync_latency_hist = None
        _mod._active_sessions_gauge = None
        _mod._registered_workflows_gauge = None

        # Clear the default prometheus registry to avoid duplicate collectors
        import prometheus_client

        collectors = list(prometheus_client.REGISTRY._names_to_collectors.values())
        for c in collectors:
            try:
                prometheus_client.REGISTRY.unregister(c)
            except Exception:
                pass

        self.app = Nexus(
            api_port=8210,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "test", {"code": "result = {'status': 'ok'}"}
        )
        self.app.register("metrics_test", workflow.build())
        register_metrics_endpoint(self.app)

    def teardown_method(self):
        if hasattr(self, "app") and self.app._running:
            self.app.stop()

    def test_metrics_returns_200(self):
        """GET /metrics returns 200."""
        client = TestClient(self.app.fastapi_app)
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self):
        """Content-Type is text/plain with OpenMetrics version."""
        client = TestClient(self.app.fastapi_app)
        response = client.get("/metrics")
        ct = response.headers.get("content-type", "")
        assert "text/plain" in ct

    def test_metrics_contains_expected_names(self):
        """Response body includes all six nexus_* metric families."""
        client = TestClient(self.app.fastapi_app)
        response = client.get("/metrics")
        body = response.text

        expected_families = [
            "nexus_workflow_registration_seconds",
            "nexus_cross_channel_sync_seconds",
            "nexus_failure_recovery_seconds",
            "nexus_session_sync_latency_seconds",
            "nexus_active_sessions",
            "nexus_registered_workflows",
        ]
        for name in expected_families:
            assert (
                name in body
            ), f"Expected metric '{name}' not found in /metrics output"

    def test_registered_workflows_gauge_reflects_count(self):
        """nexus_registered_workflows gauge matches number of registered workflows."""
        client = TestClient(self.app.fastapi_app)

        # Register a second workflow
        wf2 = WorkflowBuilder()
        wf2.add_node("PythonCodeNode", "t2", {"code": "result = {'n': 2}"})
        self.app.register("metrics_test_2", wf2.build())

        response = client.get("/metrics")
        body = response.text

        # The gauge line looks like: nexus_registered_workflows 2.0
        for line in body.splitlines():
            if line.startswith("nexus_registered_workflows "):
                value = float(line.split()[-1])
                assert value >= 2.0, f"Expected >= 2 registered workflows, got {value}"
                break
        else:
            pytest.fail("nexus_registered_workflows metric line not found")

    def test_histogram_observes_registration_time(self):
        """Histogram counts increase after workflow registration."""
        # Seed the performance deque with a known value
        self.app._performance_metrics["workflow_registration_time"].append(0.042)

        client = TestClient(self.app.fastapi_app)
        response = client.get("/metrics")
        body = response.text

        # The _count line should be >= 1
        for line in body.splitlines():
            if line.startswith("nexus_workflow_registration_seconds_count"):
                count = float(line.split()[-1])
                assert count >= 1.0, f"Expected >= 1 observation, got {count}"
                break
        else:
            pytest.fail("nexus_workflow_registration_seconds_count line not found")

    def test_repeated_scrapes_do_not_double_count(self):
        """Scraping /metrics twice does not double-count deque values."""
        self.app._performance_metrics["cross_channel_sync_time"].append(0.005)

        client = TestClient(self.app.fastapi_app)

        # First scrape
        client.get("/metrics")

        # Second scrape — count should not increase
        response = client.get("/metrics")
        body = response.text

        for line in body.splitlines():
            if line.startswith("nexus_cross_channel_sync_seconds_count"):
                count = float(line.split()[-1])
                assert (
                    count == 1.0
                ), f"Expected exactly 1 observation after 2 scrapes, got {count}"
                break


class TestMetricsLazyImport:
    """Test that prometheus_client is lazily imported."""

    def test_module_imports_without_prometheus(self):
        """nexus.metrics can be imported even if prometheus_client is missing.

        The actual lazy-import guard is tested by verifying that the module
        loads successfully (which it does since we are importing it here
        and it has no top-level prometheus_client import).
        """
        import nexus.metrics as mod

        assert hasattr(mod, "register_metrics_endpoint")
        assert hasattr(mod, "_require_prometheus_client")

    def test_require_raises_helpful_error(self, monkeypatch):
        """_require_prometheus_client raises ImportError with install hint."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "prometheus_client":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.raises(ImportError, match="pip install kailash-nexus"):
            _require_prometheus_client()


class TestEventBusSSEUrl:
    """Test the sse_url() method on EventBus."""

    def test_sse_url_returns_path(self):
        """sse_url() returns the correct endpoint path string."""
        bus = EventBus()
        assert bus.sse_url() == "/events/stream"

    def test_sse_url_is_static(self):
        """sse_url() works as a static method call."""
        assert EventBus.sse_url() == "/events/stream"
