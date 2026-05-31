# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring tests for the Depends extractor (AC 1).

Drives a REAL Nexus HTTP gateway via Starlette's ``TestClient`` — the full
ASGI stack (request-capture middleware → workflow route → HandlerNode →
resolver chain → handler) executes end to end. NO MOCKING.

Covers:
- A handler with ``Depends(get_user)`` receives the resolved user.
- Recursive resolution: ``Depends(A)`` where ``A`` itself takes
  ``Depends(B)``.
- Per-invocation memoisation: the same ``Depends`` callable referenced by two
  parameters resolves exactly once.
"""

import asyncio
import socket

import pytest
from fastapi.testclient import TestClient

from nexus import Nexus
from nexus.extractors import Depends, Request


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _client_for(app: Nexus) -> TestClient:
    """Register handler routes on the live gateway and return a TestClient."""
    # HTTPTransport.start registers the handler workflows as gateway routes.
    asyncio.run(app._http_transport.start(app._registry))
    assert app.fastapi_app is not None
    return TestClient(app.fastapi_app, raise_server_exceptions=False)


def _handler_output(resp_json: dict) -> dict:
    """Extract the handler node output from the WorkflowAPI execute response.

    The execute response is ``{"outputs": {"handler": <result>}, ...}``.
    """
    return resp_json["outputs"]["handler"]


@pytest.mark.integration
def test_depends_resolves_and_reaches_handler():
    """A Depends(get_user) value reaches the handler (AC 1)."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    def get_user(request: Request) -> dict:
        return {"id": request.headers.get("x-user-id", "anonymous")}

    async def me(user: dict = Depends(get_user)) -> dict:
        return {"resolved_user": user}

    app.handler_extract("me", me)
    client = _client_for(app)

    resp = client.post(
        "/workflows/me/execute",
        json={"inputs": {}},
        headers={"X-User-Id": "u-42"},
    )
    assert resp.status_code == 200, resp.text
    out = _handler_output(resp.json())
    assert out == {"resolved_user": {"id": "u-42"}}, out


@pytest.mark.integration
def test_depends_recursive_resolution():
    """Depends(A) where A takes Depends(B) resolves the full chain (AC 1)."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    def get_tenant(request: Request) -> str:
        return request.headers.get("x-tenant", "default-tenant")

    def get_scoped_user(request: Request, tenant: str = Depends(get_tenant)) -> dict:
        return {
            "id": request.headers.get("x-user-id", "anonymous"),
            "tenant": tenant,
        }

    async def me(user: dict = Depends(get_scoped_user)) -> dict:
        return {"resolved_user": user}

    app.handler_extract("me", me)
    client = _client_for(app)

    resp = client.post(
        "/workflows/me/execute",
        json={"inputs": {}},
        headers={"X-User-Id": "u-7", "X-Tenant": "acme"},
    )
    assert resp.status_code == 200, resp.text
    out = _handler_output(resp.json())
    assert out == {"resolved_user": {"id": "u-7", "tenant": "acme"}}, out


@pytest.mark.integration
def test_depends_memoised_once_per_invocation():
    """The same Depends callable referenced twice resolves exactly once."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)
    call_count = {"n": 0}

    def get_user(request: Request) -> dict:
        call_count["n"] += 1
        return {"id": request.headers.get("x-user-id", "anonymous")}

    async def handler(
        user_a: dict = Depends(get_user), user_b: dict = Depends(get_user)
    ) -> dict:
        return {"same_object": user_a is user_b}

    app.handler_extract("dup", handler)
    client = _client_for(app)

    resp = client.post(
        "/workflows/dup/execute",
        json={"inputs": {}},
        headers={"X-User-Id": "u-99"},
    )
    assert resp.status_code == 200, resp.text
    out = _handler_output(resp.json())
    # Both params got the SAME memoised object.
    assert out["same_object"] is True, out
    # And the dependency callable ran exactly once for this invocation.
    assert call_count["n"] == 1, call_count
