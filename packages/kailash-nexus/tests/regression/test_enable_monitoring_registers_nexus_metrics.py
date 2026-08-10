# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: ``Nexus.enable_monitoring()`` MUST expose the ``nexus_*`` series.

Surfaced by ``tests/e2e/test_production_scenarios.py::TestProductionReliability::
test_plugin_failure_isolation``, which calls ``n.enable_monitoring()`` and then
asserts ``"nexus" in requests.get("/metrics").text``. It failed because
``enable_monitoring()`` delegated to ``MonitoringPlugin.apply()``, which only set
``_monitoring_enabled`` / ``_metrics`` (neither read by any production code path)
and never called :func:`nexus.metrics.register_metrics_endpoint`. ``/metrics``
therefore rendered only the Core SDK's ``kailash_*`` collectors -- the
``nexus_*`` series the ``nexus.metrics`` module defines were never initialised
into the default registry, so the documented "metrics collection" capability of
the monitoring plugin was a no-op at the public facade.

The pre-existing ``tests/integration/test_metrics.py`` could not catch this: it
calls ``register_metrics_endpoint(self.app)`` **directly**, exercising the
primitive rather than the ``enable_monitoring()`` facade users actually call.
This test drives the facade.
"""

import pytest
from fastapi.testclient import TestClient

from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus

prometheus_client = pytest.importorskip(
    "prometheus_client",
    reason="nexus_* series require the optional [metrics] extra",
)


@pytest.fixture
def clean_metrics_state():
    """Reset the module-level metric singletons and the default registry.

    ``nexus.metrics`` memoises its collectors in module globals and registers
    them in ``prometheus_client.REGISTRY`` (a process-wide singleton), so a
    sibling test that already initialised them would otherwise make this test
    pass without ``enable_monitoring()`` having done anything.
    """
    import nexus.metrics as metrics_mod

    def _reset():
        metrics_mod._metrics_initialized = False
        metrics_mod._workflow_registration_hist = None
        metrics_mod._cross_channel_sync_hist = None
        metrics_mod._failure_recovery_hist = None
        metrics_mod._session_sync_latency_hist = None
        metrics_mod._active_sessions_gauge = None
        metrics_mod._registered_workflows_gauge = None

        for collector in list(prometheus_client.REGISTRY._names_to_collectors.values()):
            try:
                prometheus_client.REGISTRY.unregister(collector)
            except KeyError:
                # Already unregistered via an alias name in the same sweep.
                pass

    _reset()
    yield
    _reset()


# `clean_metrics_state` is requested via usefixtures, not as a parameter: it is
# SIDE-EFFECT-ONLY (it resets the module-level metric singletons and the
# process-wide prometheus registry) and yields no value to assert on. Declaring
# it here rather than as an unused argument makes that explicit.
@pytest.mark.regression
@pytest.mark.usefixtures("clean_metrics_state")
def test_enable_monitoring_exposes_nexus_metrics():
    """``enable_monitoring()`` alone MUST make ``nexus_*`` series scrapeable.

    Before the fix this asserted-on body contained only ``kailash_*`` and
    ``python_info`` collectors, so every ``nexus_`` lookup below failed.
    """
    app = Nexus(
        api_port=8231,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "probe", {"code": "result = {'status': 'ok'}"})
    app.register("monitoring_probe", workflow.build())

    try:
        # The facade under test -- no direct register_metrics_endpoint() call.
        app.enable_monitoring()

        # `fastapi_app` is None until the enterprise gateway is lazily
        # initialised (issue #712); the register() above triggers that. Assert
        # it explicitly so a regression in gateway init fails here with a clear
        # message instead of inside TestClient on a None app.
        fastapi_app = app.fastapi_app
        assert fastapi_app is not None, (
            "Nexus.fastapi_app is None -- the enterprise gateway was not "
            "initialised by register(), so /metrics cannot be exercised."
        )

        response = TestClient(fastapi_app).get("/metrics")
        assert response.status_code == 200, response.text

        body = response.text
        assert "nexus_registered_workflows" in body, (
            "enable_monitoring() did not register the nexus_* collectors; "
            f"/metrics body was: {body[:500]}"
        )
        # The gauge must reflect real Nexus state, not just exist: one workflow
        # was registered above, so a scrape-time sync MUST report it.
        assert "nexus_registered_workflows 1.0" in body, (
            "nexus_registered_workflows was not synced from the Nexus instance; "
            f"/metrics body was: {body[:500]}"
        )
    finally:
        if app._running:
            app.stop()
