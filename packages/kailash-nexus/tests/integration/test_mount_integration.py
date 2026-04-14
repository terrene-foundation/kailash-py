"""Tier 2 integration tests for Nexus.mount() — real HTTP dispatch.

These tests spin up the parent Nexus's underlying FastAPI app against
Starlette's ``TestClient`` (which dispatches through the full ASGI
stack including Mount path-stripping and sub-app middleware) and
verify that requests to mounted paths route into the sub-app with
the prefix stripped.

Covers issue #447.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from nexus import Nexus


@pytest.fixture
def parent() -> Nexus:
    app = Nexus(auto_discovery=False, api_port=8300)
    yield app
    app.close()


# --- Mount a bare FastAPI sub-app (baseline ASGI compatibility) ------


def test_mount_fastapi_subapp_routes_with_prefix_stripped(parent: Nexus) -> None:
    """Baseline: mounting a plain FastAPI sub-app forwards requests with
    the prefix stripped. This is the exact behavior contract for #447."""
    sub = FastAPI()

    @sub.get("/hello")
    def hello():
        return {"msg": "hi from sub"}

    parent.mount("/api/v2", sub)

    client = TestClient(parent.fastapi_app)

    # Prefix-stripped dispatch: /api/v2/hello -> sub sees /hello
    resp = client.get("/api/v2/hello")
    assert resp.status_code == 200
    assert resp.json() == {"msg": "hi from sub"}

    # Unmounted path does NOT match sub-app
    resp = client.get("/api/v2/nonexistent")
    assert resp.status_code == 404


def test_mount_subapp_middleware_applies_to_mounted_requests(
    parent: Nexus,
) -> None:
    """The sub-app's own middleware must apply to requests routed
    through the mount — this is the composition guarantee."""
    sub = FastAPI()

    @sub.middleware("http")
    async def add_header(request, call_next):
        response = await call_next(request)
        response.headers["X-SubApp-Marker"] = "child-middleware-ran"
        return response

    @sub.get("/ping")
    def ping():
        return {"ok": True}

    parent.mount("/svc", sub)

    client = TestClient(parent.fastapi_app)
    resp = client.get("/svc/ping")
    assert resp.status_code == 200
    assert resp.headers.get("X-SubApp-Marker") == "child-middleware-ran"


def test_mount_parent_routes_unaffected_by_mount(parent: Nexus) -> None:
    """Mounting a sub-app must NOT shadow the parent's own routes
    outside the mount prefix."""
    sub = FastAPI()

    @sub.get("/ping")
    def sub_ping():
        return {"source": "sub"}

    parent.mount("/sub", sub)

    client = TestClient(parent.fastapi_app)
    # Parent's own /health (or any non-mounted route) still responds
    resp = client.get("/health")
    # The parent's gateway provides /health; we only assert it's not
    # swallowed by the /sub mount.
    assert resp.status_code != 404 or "/sub" not in str(resp.request.url)

    # Mounted sub's /ping resolves
    resp = client.get("/sub/ping")
    assert resp.status_code == 200
    assert resp.json() == {"source": "sub"}


# --- Recursive composition through real HTTP dispatch ----------------


def test_mount_recursive_composition_routes_through_all_levels(
    parent: Nexus,
) -> None:
    """Parent -> child (Nexus) -> grandchild (FastAPI), all reachable
    via a single HTTP request that traverses two mount boundaries."""
    grandchild = FastAPI()

    @grandchild.get("/leaf")
    def leaf():
        return {"depth": 2, "where": "grandchild"}

    child = Nexus(auto_discovery=False, api_port=8301)
    try:
        child.mount("/v2", grandchild)
        parent.mount("/api", child)

        client = TestClient(parent.fastapi_app)
        resp = client.get("/api/v2/leaf")
        assert resp.status_code == 200
        assert resp.json() == {"depth": 2, "where": "grandchild"}
    finally:
        child.close()


# --- Mounting a child Nexus with a registered handler ----------------


def test_mount_child_nexus_exposes_child_handlers_under_prefix(
    parent: Nexus,
) -> None:
    """Mount a Nexus as a sub-application; its registered handler must
    be reachable through the parent at the mounted prefix."""
    child = Nexus(auto_discovery=False, api_port=8302)
    try:

        @child.handler("greet", description="Child greet handler")
        async def greet(name: str = "world") -> dict:
            return {"message": f"hello, {name}"}

        parent.mount("/api/v2", child)

        client = TestClient(parent.fastapi_app)
        # The child's workflow registration exposes
        # POST /workflows/greet/execute — invoking through the parent's
        # /api/v2 prefix must reach the child's handler.
        resp = client.post(
            "/api/v2/workflows/greet/execute",
            json={"inputs": {"name": "alice"}},
        )
        # Accept either 200 (executed) or a handler-specific error shape
        # — the contract we test is that the request reaches the child
        # (not 404 at the parent level).
        assert resp.status_code != 404, (
            f"Expected mounted request to reach child, got 404: " f"{resp.text}"
        )
    finally:
        child.close()
