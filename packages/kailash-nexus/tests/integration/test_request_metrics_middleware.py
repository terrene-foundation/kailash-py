# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for RequestMetricsMiddleware (Tier 2 — real Nexus).

Exercises the middleware end-to-end through a real Nexus instance + a
registered workflow + the real /metrics endpoint via fastapi TestClient:

- Counter nexus_http_requests_total increments + appears in /metrics, with
  method / route-template / status labels.
- Histogram nexus_http_request_duration_seconds appears after a request.
- The matched-route TEMPLATE is recorded (cardinality control) — never a
  raw concrete path.
- The excluded /metrics path itself records no route sample.

Mirrors test_metrics.py's setup idiom: resets the metrics module globals
(including the new request-metric globals) and clears the prometheus default
registry in setup_method to avoid "Duplicated timeseries in CollectorRegistry".
"""

import pytest
from fastapi.testclient import TestClient

from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus, RequestMetricsMiddleware
from nexus.metrics import register_metrics_endpoint


@pytest.mark.integration
class TestRequestMetricsMiddleware:
    """Tier 2 suite for the per-request HTTP metrics middleware."""

    def setup_method(self):
        """Reset metrics module state + prometheus registry, build a Nexus app."""
        import nexus.metrics as _mod

        # Deque-synced metric globals (mirror test_metrics.py).
        _mod._metrics_initialized = False
        _mod._workflow_registration_hist = None
        _mod._cross_channel_sync_hist = None
        _mod._failure_recovery_hist = None
        _mod._session_sync_latency_hist = None
        _mod._active_sessions_gauge = None
        _mod._registered_workflows_gauge = None

        # New per-request metric globals — reset so _init_request_metrics
        # re-creates fresh collectors against the cleared registry below.
        _mod._request_metrics_initialized = False
        _mod._http_requests_total = None
        _mod._http_request_duration_hist = None

        import prometheus_client

        collectors = list(prometheus_client.REGISTRY._names_to_collectors.values())
        for c in collectors:
            try:
                prometheus_client.REGISTRY.unregister(c)
            except Exception:
                pass

        self.app = Nexus(
            api_port=8233,
            enable_durability=False,
            enable_auth=False,
            enable_monitoring=False,
        )

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "t", {"code": "result = {'status': 'ok'}"})
        self.app.register("metrics_mw_test", workflow.build())
        self.app.add_middleware(RequestMetricsMiddleware)
        register_metrics_endpoint(self.app)

        self.client = TestClient(self.app.fastapi_app)

    def teardown_method(self):
        if hasattr(self, "app") and self.app._running:
            self.app.stop()

    # A simple registered GET route the middleware can wrap. The workflow
    # health route is registered by Nexus at registration time.
    _PROBE_PATH = "/workflows/metrics_mw_test/health"

    def test_counter_increments_and_appears_in_metrics(self):
        """Hitting a registered route emits nexus_http_requests_total with labels."""
        resp = self.client.get(self._PROBE_PATH)
        assert resp.status_code == 200

        body = self.client.get("/metrics").text
        assert "nexus_http_requests_total" in body

        # A labelled sample for our GET 200 request must be present.
        sample_lines = [
            ln
            for ln in body.splitlines()
            if ln.startswith("nexus_http_requests_total{")
        ]
        assert sample_lines, "no nexus_http_requests_total sample emitted"

        get_200 = [
            ln for ln in sample_lines if 'method="GET"' in ln and 'status="200"' in ln
        ]
        assert get_200, f"no GET/200 counter sample found in: {sample_lines}"
        # The sample carries a route label (cardinality control — a template).
        assert any('route="' in ln for ln in get_200)

    def test_histogram_present_after_request(self):
        """nexus_http_request_duration_seconds appears in /metrics after a request."""
        self.client.get(self._PROBE_PATH)
        body = self.client.get("/metrics").text
        assert "nexus_http_request_duration_seconds" in body
        assert any(
            ln.startswith("nexus_http_request_duration_seconds_count{")
            for ln in body.splitlines()
        )

    def test_route_label_is_template_not_concrete_path(self):
        """The route label is a bounded matched-route template, not a raw path.

        Cardinality control: the recorded route label MUST be a route the
        application registered (a template / mounted sub-path), never the
        verbatim request path with a workflow-id embedded. We assert the
        label set is bounded — every emitted route label is a non-empty
        string and none equals the full concrete probe path (which would
        signal raw-path labelling).
        """
        self.client.get(self._PROBE_PATH)
        body = self.client.get("/metrics").text

        route_labels = set()
        for ln in body.splitlines():
            if ln.startswith("nexus_http_requests_total{"):
                # extract route="..."
                start = ln.find('route="')
                if start != -1:
                    start += len('route="')
                    end = ln.find('"', start)
                    route_labels.add(ln[start:end])

        assert route_labels, "no route labels recorded"
        # No label is the full concrete request path (that would be raw-path
        # labelling). The matched-route template is recorded instead.
        assert self._PROBE_PATH not in route_labels
        # Every recorded route label is a non-empty bounded template string.
        assert all(isinstance(r, str) and r for r in route_labels)

    def test_metrics_path_itself_records_no_route_sample(self):
        """The excluded /metrics path does not appear as a recorded route label."""
        # First request to a real route so the metric families exist.
        self.client.get(self._PROBE_PATH)
        # Scrape twice; the scrape path is in exclude_paths.
        self.client.get("/metrics")
        body = self.client.get("/metrics").text

        for ln in body.splitlines():
            if ln.startswith("nexus_http_requests_total{"):
                assert (
                    'route="/metrics"' not in ln
                ), f"/metrics scrape path was recorded as a route label: {ln}"
