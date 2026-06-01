# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring tests for typed HTTP status on /workflows/{name}/execute (#1218).

Drives a REAL Nexus HTTP gateway via Starlette's ``TestClient`` — the full
ASGI stack (route → mounted WorkflowAPI sub-app → AsyncLocalRuntime →
node execution → exception propagation → HTTP response) executes end to end.
NO MOCKING.

Issue #1218: ``nexus.extractors.NexusHandlerError(status_code=..., body=...)``
carries a typed HTTP status that the extractor dispatch path honors, but the
``POST /workflows/{name}/execute`` gateway path collapsed every workflow
exception to a generic HTTP 500 — discarding the typed status + body and
misdirecting operator triage (a typed 4xx looks like an internal 5xx bug).

The actual route handler for ``/workflows/{name}/execute`` is the Core SDK
``WorkflowAPI`` (``src/kailash/api/workflow_api.py``) mounted by the gateway
under ``/workflows/{name}``. The runtime wraps a node-raised exception in
``WorkflowExecutionError(...) from e``, so the typed ``NexusHandlerError`` is
reachable via the ``__cause__`` chain — the fix walks that chain.

Covers the issue acceptance criteria:
- a workflow raising ``NexusHandlerError(422, {...})`` over the execute path
  yields HTTP 422 + the typed body (NOT a generic 500).
- a genuine internal error (plain ``RuntimeError``) still yields HTTP 500 with
  the canonical generic body — no behavior change for real internal failures.
"""

import asyncio
import socket

import pytest
from fastapi.testclient import TestClient

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus
from nexus.extractors import NexusHandlerError


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _client_for(app: Nexus) -> TestClient:
    """Start the HTTP transport (flushing registered workflows) + client."""
    asyncio.run(app._http_transport.start(app._registry))
    assert app.fastapi_app is not None
    return TestClient(app.fastapi_app, raise_server_exceptions=False)


@register_node()
class TypedStatusRaisingNode(Node):
    """A node that raises NexusHandlerError(422, {...}) during execution.

    Mirrors a real handler-side typed-status rejection routed through a
    workflow node on the gateway-execute path.
    """

    def get_parameters(self) -> dict:
        return {
            "value": NodeParameter(name="value", type=str, required=False, default=""),
        }

    def run(self, **kwargs) -> dict:
        raise NexusHandlerError(
            status_code=422,
            body={"error": "validation failed", "code": "UNPROCESSABLE"},
        )


@register_node()
class GenuineInternalErrorNode(Node):
    """A node that raises a plain RuntimeError (no typed status).

    Represents a real internal failure — MUST still collapse to 500.
    """

    def get_parameters(self) -> dict:
        return {
            "value": NodeParameter(name="value", type=str, required=False, default=""),
        }

    def run(self, **kwargs) -> dict:
        raise RuntimeError("database connection pool exhausted")


@pytest.mark.integration
def test_workflow_execute_honors_nexus_handler_error_typed_status():
    """A workflow raising NexusHandlerError(422, body) → HTTP 422 + typed body.

    Issue #1218 acceptance: the execute gateway path maps status_code + body
    from the typed error, matching the extractor-handler path — not 500.
    """
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    workflow = WorkflowBuilder()
    workflow.add_node("TypedStatusRaisingNode", "raise_typed", {})
    app.register("typed_status_wf", workflow.build())

    client = _client_for(app)
    resp = client.post("/workflows/typed_status_wf/execute", json={"inputs": {}})

    assert resp.status_code == 422, (resp.status_code, resp.text)
    body = resp.json()
    # The typed body the handler designed is returned verbatim.
    assert body == {"error": "validation failed", "code": "UNPROCESSABLE"}, body


@pytest.mark.integration
def test_workflow_execute_genuine_internal_error_still_500():
    """A workflow raising a plain RuntimeError → HTTP 500 + canonical body.

    Issue #1218 acceptance: no behavior change for genuine internal errors —
    the raw error is logged server-side and never echoed to the client.
    """
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    workflow = WorkflowBuilder()
    workflow.add_node("GenuineInternalErrorNode", "raise_internal", {})
    app.register("internal_error_wf", workflow.build())

    client = _client_for(app)
    resp = client.post("/workflows/internal_error_wf/execute", json={"inputs": {}})

    assert resp.status_code == 500, (resp.status_code, resp.text)
    body = resp.json()
    # Canonical generic 500 body — the raw error string MUST NOT leak.
    assert "database connection pool exhausted" not in resp.text
    assert body.get("detail") == "Internal server error", body
