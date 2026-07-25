# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: #1959 BUG-2 — ``register(wf); start(blocking=False)`` emits no
spurious "Failed to register" ERROR.

The enterprise gateway is built once at construction, so the documented
``register(wf); start()`` flow (patterns.md) eagerly registers the workflow
with the gateway. ``HTTPTransport.start`` then re-registered EVERY registry
workflow, driving ``gateway.register_workflow`` into its duplicate-name
``ValueError`` — caught and logged at ERROR as
``Failed to register workflow '<name>' with HTTP: ... already registered``.
Functionally benign (already registered) but a false "Failed to register"
ERROR on the happy path (observability Rule 5 / zero-tolerance Rule 1).

The 16 e2e tests missed this because their fixture starts an EMPTY registry
then registers AFTER start; the documented register-FIRST flow was never
walked for ``blocking=False``. This test walks it (a real ``Nexus`` + the real
gateway) per rules/testing.md Tier 2 (no mocking).
"""

import logging

import pytest

from nexus import Nexus


def _workflow():
    """Build a trivial real workflow (no mocking)."""
    from kailash.workflow.builder import WorkflowBuilder

    wf = WorkflowBuilder()
    wf.add_node("PythonCodeNode", "n", {"code": "result = {'ok': True}"})
    return wf.build()


@pytest.mark.regression
def test_register_first_then_start_nonblocking_no_failed_to_register_error(caplog):
    """The documented ``register(wf); start(blocking=False)`` flow emits NO
    ERROR-level "Failed to register", and the workflow is registered with the
    gateway exactly once."""
    app = Nexus(auto_discovery=False)
    app.register("demo", _workflow())  # eager register with the gateway

    with caplog.at_level(logging.ERROR):
        app.start(blocking=False)
    try:
        failed = [
            r.getMessage()
            for r in caplog.records
            if r.levelno >= logging.ERROR and "Failed to register" in r.getMessage()
        ]
        assert not failed, (
            "register-first + start(blocking=False) must not log a spurious "
            f"'Failed to register' ERROR on the happy path; got: {failed}"
        )

        # Registered exactly once (no duplicate, no silent drop).
        gateway = app._http_transport.gateway
        names = list(gateway.workflows.keys())
        assert names.count("demo") == 1, (
            f"workflow 'demo' must be registered with the gateway exactly once; "
            f"got {names}"
        )
    finally:
        app.stop()
