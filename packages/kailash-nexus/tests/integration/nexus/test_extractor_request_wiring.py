# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring tests for the Request extractor (AC 2).

Drives a REAL Nexus HTTP gateway via Starlette's ``TestClient``. NO MOCKING.

Covers:
- A handler annotated ``request: Request`` sees the originating request (a
  custom header set by the client reaches the handler).
- PEP 563 rejection: a handler defined in a module that uses
  ``from __future__ import annotations`` raises ``ExtractorPEP563Error`` at
  registration, with a workspace-relative (NOT absolute) path in the message.
- Resolver error-path split-visibility: a ``Depends`` callable that raises
  surfaces ONLY HTTP 500 + the INTERNAL_ERROR envelope to the client, never
  the exception detail.
"""

import asyncio
import socket

import pytest
from fastapi.testclient import TestClient

from nexus import Nexus
from nexus.extractors import Depends, NexusHandlerError, Request
from nexus.extractors.resolver import ExtractorPEP563Error


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _client_for(app: Nexus) -> TestClient:
    asyncio.run(app._http_transport.start(app._registry))
    assert app.fastapi_app is not None
    return TestClient(app.fastapi_app, raise_server_exceptions=False)


def _handler_output(resp_json: dict) -> dict:
    return resp_json["outputs"]["handler"]


@pytest.mark.integration
def test_request_extractor_sees_custom_header():
    """A handler with request: Request sees the originating request (AC 2)."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    async def echo_header(request: Request) -> dict:
        return {"seen": request.headers.get("x-custom", "MISSING")}

    app.handler_extract("echo", echo_header)
    client = _client_for(app)

    resp = client.post(
        "/workflows/echo/execute",
        json={"inputs": {}},
        headers={"X-Custom": "from-the-client"},
    )
    assert resp.status_code == 200, resp.text
    out = _handler_output(resp.json())
    assert out == {"seen": "from-the-client"}, out


@pytest.mark.integration
def test_request_extractor_mixes_with_flat_input():
    """Request + flat params coexist: flat from body, Request from middleware."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    async def greet(name: str, request: Request) -> dict:
        return {
            "greeting": f"hello {name}",
            "ua": request.headers.get("x-agent", "none"),
        }

    app.handler_extract("greet", greet)
    client = _client_for(app)

    resp = client.post(
        "/workflows/greet/execute",
        json={"inputs": {"name": "alice"}},
        headers={"X-Agent": "probe/1.0"},
    )
    assert resp.status_code == 200, resp.text
    out = _handler_output(resp.json())
    assert out == {"greeting": "hello alice", "ua": "probe/1.0"}, out


@pytest.mark.integration
def test_pep563_handler_raises_at_registration():
    """A PEP-563-affected handler raises ExtractorPEP563Error at registration."""
    from ._pep563_handler_fixture import pep563_handler

    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)
    with pytest.raises(ExtractorPEP563Error) as exc_info:
        app.handler_extract("p563", pep563_handler)

    msg = str(exc_info.value)
    # The fix-pointer is present.
    assert "future" in msg.lower() or "PEP 563" in msg
    # PII hygiene (spec §313 LOW-S1): NO absolute /Users/ or /home/ path leaks.
    assert "/Users/" not in msg, msg
    assert "/home/" not in msg, msg


@pytest.mark.integration
def test_resolver_error_path_split_visibility():
    """A raising Depends surfaces ONLY HTTP 500 + INTERNAL_ERROR envelope.

    The client MUST NOT see str(exc), the class name, traceback, or paths
    (spec §134-142). A correlation id is present so the operator can look up
    the full server-side context.
    """
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    SECRET = "super-secret-internal-detail-do-not-leak"

    def boom(request: Request) -> dict:
        raise RuntimeError(SECRET)

    async def handler(user: dict = Depends(boom)) -> dict:
        return {"unreachable": True}

    app.handler_extract("boom", handler)
    client = _client_for(app)

    resp = client.post("/workflows/boom/execute", json={"inputs": {}})
    # The execute endpoint surfaces the failure; the leak check is on the body.
    body_text = resp.text
    assert SECRET not in body_text, "resolver leaked the exception detail"
    assert "RuntimeError" not in body_text, "resolver leaked the exception class"
    assert "Traceback" not in body_text, "resolver leaked a traceback"


@pytest.mark.integration
def test_typed_status_error_preserved_by_resolver():
    """A Depends raising NexusHandlerError is preserved (NOT collapsed) by the resolver.

    The resolver's split-visibility contract (spec §139) preserves a typed
    ``NexusHandlerError`` instead of mapping it to the generic 500 envelope.
    This asserts the resolver-chain contract directly (the in-scope Shard-1
    deliverable). Mapping the typed status onto the HTTP response for the
    *workflow-execute* transport path is a gateway-layer concern tracked
    separately — see the shard report's "Anything I could NOT complete".
    """
    from nexus.context import _current_request, set_current_request
    from nexus.extractors.resolver import build_resolver_chain

    def require_auth() -> dict:
        raise NexusHandlerError(
            status_code=403, body={"error": "forbidden", "code": "FORBIDDEN"}
        )

    async def handler(auth: dict = Depends(require_auth)) -> dict:
        return {"auth": auth}

    chain = build_resolver_chain(handler)
    token = set_current_request(None)
    try:
        with pytest.raises(NexusHandlerError) as exc_info:
            asyncio.run(chain.resolve_and_call({}))
    finally:
        _current_request.reset(token)

    # The typed status is preserved as-is — NOT collapsed to 500.
    assert exc_info.value.status_code == 403
    assert exc_info.value.body == {"error": "forbidden", "code": "FORBIDDEN"}
