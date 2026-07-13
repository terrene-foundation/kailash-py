# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: HTTP RED histogram covers core-gateway entry points (#1708 W5).

Nexus's ``RequestMetricsMiddleware`` (nexus/middleware/request_metrics.py) is
attached to the SAME FastAPI app the Core SDK's enterprise gateway
(``kailash.servers.gateway.create_gateway`` -> ``EnterpriseWorkflowServer`` /
``WorkflowServer``) builds. Direct gateway routes registered via
``@self.app.get(...)`` (e.g. ``/health``, ``/workflows``, ``/``,
``/enterprise/health``) were already correctly labelled -- Starlette/FastAPI
populate ``scope["route"]`` for those.

The gap: ``WorkflowServer.register_workflow`` -- the mechanism BOTH
``Nexus.register()`` AND ``@Nexus.handler()`` funnel every registered
workflow through -- mounts a FRESH per-workflow ``WorkflowAPI`` FastAPI
sub-app at a LITERAL path (``/workflows/<name>``), not a route template.
Starlette's ``Mount.matches()`` never sets ``scope["route"]``; only the
sub-app's OWN router does once IT matches (``/execute``, ``/health``,
``/status/{id}``, ``/workflow/info``). Before the fix, the middleware's
route label was therefore the sub-app's BARE relative template
(``/execute``, ``/health``) with the mount prefix silently discarded:

  * every registered workflow's ``/execute`` call collapsed to the SAME
    label ``/execute`` -- indistinguishable from one another, and
  * a per-workflow ``/health`` sub-route COLLIDED with the top-level
    gateway's OWN ``/health`` liveness-probe series -- two semantically
    different endpoints recorded under one indistinguishable time series.

The fix templates the Mount's ``root_path`` (``/workflows/<name>`` ->
``/workflows/{name}``) and prepends it to the sub-app's matched route
template, so per-workflow calls aggregate under
``/workflows/{name}/execute`` / ``/workflows/{name}/health`` -- distinct
from the top-level ``/execute`` (n/a) and ``/health`` labels, and still
bounded (a fixed template string, not the concrete workflow name).

Drives REAL HTTP requests through a real Nexus instance (TestClient over the
real ASGI app) at BOTH surfaces -- a direct core-gateway route and a
mounted per-workflow route -- and asserts against the REAL Prometheus
scrape body, per rules/testing.md Tier 2 (no mocking) and
rules/user-flow-validation.md (the literal request/response/scrape path).
"""

import pytest
from fastapi.testclient import TestClient

from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus
from nexus.metrics import register_metrics_endpoint
from nexus.presets import NexusConfig, apply_preset


def _reset_prometheus_state():
    """Clear nexus.metrics module globals + the prometheus default registry.

    Mirrors the setup idiom in test_metrics.py / test_request_metrics_middleware.py
    so repeated Nexus instantiations across tests don't hit "Duplicated
    timeseries in CollectorRegistry".
    """
    import nexus.metrics as _mod

    _mod._metrics_initialized = False
    _mod._workflow_registration_hist = None
    _mod._cross_channel_sync_hist = None
    _mod._failure_recovery_hist = None
    _mod._session_sync_latency_hist = None
    _mod._active_sessions_gauge = None
    _mod._registered_workflows_gauge = None
    _mod._request_metrics_initialized = False
    _mod._http_requests_total = None
    _mod._http_request_duration_hist = None

    import prometheus_client

    for c in list(prometheus_client.REGISTRY._names_to_collectors.values()):
        try:
            prometheus_client.REGISTRY.unregister(c)
        except Exception:
            pass


def _duration_count_samples(metrics_body: str) -> list[str]:
    return [
        ln
        for ln in metrics_body.splitlines()
        if ln.startswith("nexus_http_request_duration_seconds_count{")
    ]


def _route_label(sample_line: str) -> str:
    start = sample_line.find('route="')
    assert start != -1, f"no route label in sample: {sample_line}"
    start += len('route="')
    end = sample_line.find('"', start)
    return sample_line[start:end]


@pytest.fixture
def metrics_app():
    """A real Nexus instance with the metrics-enabled 'standard' preset applied.

    ``metrics_enabled`` defaults False (nexus/presets.py NexusConfig) --
    RequestMetricsMiddleware is opt-in. Applying the preset directly (rather
    than passing ``preset=`` to the constructor) lets the fixture set
    ``metrics_enabled=True`` explicitly without depending on constructor
    kwarg plumbing that is out of scope for this regression.
    """
    _reset_prometheus_state()

    app = Nexus(
        api_port=18700,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )
    config = NexusConfig(metrics_enabled=True)
    apply_preset(app, "standard", config)
    app._active_preset = "standard"
    app._nexus_config = config
    register_metrics_endpoint(app)

    yield app

    if app._running:
        app.stop()


@pytest.mark.regression
class TestCoreGatewayRouteLabelCoverage:
    """HTTP RED histogram MUST cover core-gateway entry points with bounded labels."""

    def test_direct_core_gateway_route_recorded_with_own_template(self, metrics_app):
        """A direct gateway route (not Nexus-registered, not mounted) is recorded.

        ``/health`` is registered directly on the Core SDK gateway's FastAPI
        app (kailash.servers.enterprise_workflow_server /
        kailash.servers.workflow_server ``@self.app.get("/health")``) --
        this is the archetypal "core-gateway HTTP entry point that bypasses
        the Nexus wrapper" the audit named. It must reach the real scrape
        with its own literal template, untouched by the Mount-prefix fix.
        """
        client = TestClient(metrics_app.fastapi_app)

        resp = client.get("/health")
        assert resp.status_code == 200

        body = client.get("/metrics").text
        samples = _duration_count_samples(body)
        health_samples = [ln for ln in samples if 'route="/health"' in ln]
        assert health_samples, (
            "core-gateway direct route /health produced no "
            f"nexus_http_request_duration_seconds_count sample; got: {samples}"
        )
        assert 'method="GET"' in health_samples[0]
        assert 'status="200"' in health_samples[0]

    def test_mounted_per_workflow_route_recorded_with_templated_mount_prefix(
        self, metrics_app
    ):
        """A workflow-execution entry point (mounted sub-app) records a BOUNDED,
        templated route label that is DISTINCT from the top-level gateway route
        of the same relative name.

        ``Nexus.register()`` -> ``HTTPTransport.register_workflow`` ->
        ``WorkflowServer.register_workflow`` mounts a per-workflow FastAPI
        sub-app (``WorkflowAPI``) at the literal path
        ``/workflows/<name>``. Before the fix this collapsed to the bare
        sub-app route (``/execute``); after the fix it must be
        ``/workflows/{name}/execute`` -- a template, never the concrete
        workflow name, and never colliding with an unrelated top-level route.
        """
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "n1", {"code": "result = {'status': 'ok'}"})
        metrics_app.register("w5_core_gateway_probe", workflow.build())

        client = TestClient(metrics_app.fastapi_app)

        resp = client.post(
            "/workflows/w5_core_gateway_probe/execute", json={"inputs": {}}
        )
        assert resp.status_code == 200

        body = client.get("/metrics").text
        samples = _duration_count_samples(body)

        # The mounted route MUST be recorded (not silently dropped).
        execute_samples = [ln for ln in samples if "/execute" in _route_label(ln)]
        assert execute_samples, (
            "mounted core-gateway workflow-execute route produced no "
            f"duration-histogram sample; got: {samples}"
        )

        label = _route_label(execute_samples[0])
        # Bounded/templated: the concrete workflow name MUST NOT leak into
        # the label (cardinality control -- security.md "route as a bounded
        # template", not the raw path).
        assert (
            "w5_core_gateway_probe" not in label
        ), f"route label leaked the concrete workflow name: {label!r}"
        # Correctly templated, distinguishable from the bare sub-app route.
        assert (
            label == "/workflows/{name}/execute"
        ), f"expected the mount-prefix-templated label, got: {label!r}"

    def test_per_workflow_health_route_does_not_collide_with_gateway_health(
        self, metrics_app
    ):
        """A per-workflow /health sub-route and the gateway's own /health probe
        MUST record as DISTINCT Prometheus series.

        This is the concrete metric-corruption failure mode the fix closes:
        pre-fix, both requests recorded under the identical bare label
        ``route="/health"``, merging two semantically unrelated signals
        (gateway liveness vs one workflow's health check) into a single
        indistinguishable time series.
        """
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "n1", {"code": "result = {'status': 'ok'}"})
        metrics_app.register("w5_health_collision_probe", workflow.build())

        client = TestClient(metrics_app.fastapi_app)

        # Top-level gateway liveness probe.
        r1 = client.get("/health")
        assert r1.status_code == 200
        # Per-workflow health sub-route (WorkflowAPI's own /health, mounted
        # at /workflows/<name>).
        r2 = client.get("/workflows/w5_health_collision_probe/health")
        assert r2.status_code == 200

        body = client.get("/metrics").text
        samples = _duration_count_samples(body)
        labels = {_route_label(ln) for ln in samples if "GET" in ln}

        assert "/health" in labels, f"top-level /health missing from labels: {labels}"
        assert (
            "/workflows/{name}/health" in labels
        ), f"per-workflow health route missing templated label: {labels}"
        # The defining assertion: they are NOT the same series.
        assert "/health" != "/workflows/{name}/health"

    def test_metrics_scrape_path_itself_excluded_from_route_labels(self, metrics_app):
        """The /metrics scrape path (also a core-gateway-adjacent route, replacing
        the gateway's own /metrics route -- see register_metrics_endpoint) does
        not pollute route labels with its own requests (existing exclude_paths
        contract, re-asserted here alongside the new mount-prefix behavior).
        """
        client = TestClient(metrics_app.fastapi_app)
        client.get("/health")
        client.get("/metrics")
        body = client.get("/metrics").text

        for ln in _duration_count_samples(body):
            assert (
                'route="/metrics"' not in ln
            ), f"/metrics scrape path leaked into route labels: {ln}"
