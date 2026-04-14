"""Unit tests for Nexus.mount() — sub-application composition.

Tier 1 tests: validation, queueing behavior, introspection, recursive
composition. These tests construct real Nexus instances (mocking the
gateway would defeat the purpose of testing the mount wiring) but do
not start the server — they assert on the FastAPI app's route table.

Covers issue #447: subapp mounting / sub-application composition.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from nexus import MountInfo, Nexus

# --- Fixtures ---------------------------------------------------------


@pytest.fixture
def parent() -> Nexus:
    """Fresh parent Nexus — gateway initialized, no handlers."""
    app = Nexus(auto_discovery=False)
    yield app
    app.close()


@pytest.fixture
def child() -> Nexus:
    """Fresh child Nexus with one handler registered."""
    app = Nexus(auto_discovery=False, api_port=8001)

    @app.handler("child_ping", description="Child ping handler")
    async def child_ping(name: str = "world") -> dict:
        return {"message": f"child says hi, {name}"}

    yield app
    app.close()


# --- Validation: path argument ---------------------------------------


def test_mount_rejects_non_string_path(parent: Nexus, child: Nexus) -> None:
    with pytest.raises(TypeError, match="path must be str"):
        parent.mount(123, child)  # type: ignore[arg-type]


def test_mount_rejects_empty_path(parent: Nexus, child: Nexus) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        parent.mount("", child)


def test_mount_rejects_path_without_leading_slash(parent: Nexus, child: Nexus) -> None:
    with pytest.raises(ValueError, match=r"must start with '/'"):
        parent.mount("api/v2", child)


def test_mount_rejects_duplicate_path(parent: Nexus, child: Nexus) -> None:
    parent.mount("/api/v2", child)
    another_child = Nexus(auto_discovery=False, api_port=8002)
    try:
        with pytest.raises(ValueError, match="already mounted"):
            parent.mount("/api/v2", another_child)
    finally:
        another_child.close()


def test_mount_normalizes_trailing_slash(parent: Nexus, child: Nexus) -> None:
    parent.mount("/api/v2/", child)
    assert len(parent._mounts) == 1
    assert parent._mounts[0].path == "/api/v2"


def test_mount_preserves_root_slash(parent: Nexus) -> None:
    """A single '/' must not be stripped to the empty string."""

    # Use a plain ASGI app — mounting a Nexus at '/' would mask the parent's
    # own routes.
    async def asgi_app(scope, receive, send):  # pragma: no cover - not invoked
        pass

    parent.mount("/", asgi_app)
    assert parent._mounts[0].path == "/"


# --- Validation: subapp argument --------------------------------------


def test_mount_rejects_none_subapp(parent: Nexus) -> None:
    with pytest.raises(TypeError, match="subapp must not be None"):
        parent.mount("/api/v2", None)


def test_mount_accepts_bare_asgi_app(parent: Nexus) -> None:
    async def asgi_app(scope, receive, send):  # pragma: no cover
        pass

    parent.mount("/ext", asgi_app)
    assert parent._mounts[0].subapp is asgi_app


def test_mount_accepts_fastapi_app(parent: Nexus) -> None:
    from fastapi import FastAPI

    sub = FastAPI()
    parent.mount("/fastapi-sub", sub)
    assert parent._mounts[0].subapp is sub


# --- Introspection ----------------------------------------------------


def test_mount_records_mount_info(parent: Nexus, child: Nexus) -> None:
    parent.mount("/api/v2", child, name="v2-api")
    assert len(parent._mounts) == 1
    info = parent._mounts[0]
    assert isinstance(info, MountInfo)
    assert info.path == "/api/v2"
    assert info.subapp is child
    assert info.name == "v2-api"
    assert info.added_at is not None


def test_mount_returns_self_for_chaining(parent: Nexus, child: Nexus) -> None:
    result = parent.mount("/api/v2", child)
    assert result is parent


# --- FastAPI route-table effects --------------------------------------


def test_mount_adds_route_to_parent_fastapi_app(parent: Nexus, child: Nexus) -> None:
    """The parent's FastAPI app must gain a route rooted at the mount path."""
    parent.mount("/api/v2", child)
    mount_paths = [
        getattr(r, "path", None)
        for r in parent.fastapi_app.routes
        if getattr(r, "path", None) == "/api/v2"
    ]
    assert "/api/v2" in mount_paths


def test_mount_resolves_nexus_subapp_to_its_fastapi_app(
    parent: Nexus, child: Nexus
) -> None:
    """When a Nexus is mounted, the underlying route MUST delegate to the
    child's FastAPI app so the child's full middleware/handler stack
    applies to mounted requests."""
    parent.mount("/api/v2", child)
    mount_route = next(
        r for r in parent.fastapi_app.routes if getattr(r, "path", None) == "/api/v2"
    )
    # Starlette Mount stores the ASGI app under .app
    assert mount_route.app is child.fastapi_app


# --- Recursive composition --------------------------------------------


def test_mount_supports_recursive_composition(parent: Nexus, child: Nexus) -> None:
    """A mounted Nexus must itself be able to mount further sub-apps —
    the composition is recursive to arbitrary depth."""
    grandchild = Nexus(auto_discovery=False, api_port=8002)
    try:

        @grandchild.handler("deep", description="Grandchild handler")
        async def deep(x: int = 0) -> dict:
            return {"depth": 2, "x": x}

        parent.mount("/api", child)
        child.mount("/v2", grandchild)

        # Each level records its own mount
        assert [m.path for m in parent._mounts] == ["/api"]
        assert [m.path for m in child._mounts] == ["/v2"]

        # Recursive wiring reaches grandchild.fastapi_app via child
        parent_mount = next(
            r for r in parent.fastapi_app.routes if getattr(r, "path", None) == "/api"
        )
        assert parent_mount.app is child.fastapi_app

        child_mount = next(
            r for r in child.fastapi_app.routes if getattr(r, "path", None) == "/v2"
        )
        assert child_mount.app is grandchild.fastapi_app
    finally:
        grandchild.close()


# --- Queueing (pre-gateway mounts) ------------------------------------


def test_mount_queues_when_gateway_not_ready() -> None:
    """Construct a Nexus, null out the gateway to simulate pre-init, then
    assert the mount is queued rather than applied eagerly."""
    app = Nexus(auto_discovery=False)
    try:
        # Simulate gateway not ready by clearing the transport's gateway
        app._http_transport._gateway = None

        sub = Nexus(auto_discovery=False, api_port=8099)
        try:
            app.mount("/deferred", sub)

            assert len(app._mount_queue) == 1
            qpath, qsubapp, qname = app._mount_queue[0]
            assert qpath == "/deferred"
            assert qsubapp is sub
            assert qname is None

            # Still recorded in _mounts for introspection
            assert [m.path for m in app._mounts] == ["/deferred"]
        finally:
            sub.close()
    finally:
        app.close()
