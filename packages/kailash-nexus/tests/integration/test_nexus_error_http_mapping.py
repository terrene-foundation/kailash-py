# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Integration (Tier 2) — NexusError -> HTTP status/body mapping.

Regression for the gap discovered during #937 analysis: ``nexus/errors.py``
documents that "the HTTP transport catches NexusError subclasses and returns
the appropriate JSON response", but no exception handler was ever installed —
raising a typed error from a route produced a 500 instead of the declared
status. This exercises the handler now installed in
``HTTPTransport._install_exception_handlers`` (wired from
``_initialize_gateway`` so it is present on the TestClient path).

Real Nexus app + real FastAPI TestClient (no mocks).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexus import Nexus
from nexus.errors import ConflictError, NexusError, NotFoundError, ValidationError


def _free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def client_with_error_routes():
    """Real Nexus app with routes that raise typed + untyped errors."""
    app = Nexus(api_port=_free_port(), auto_discovery=False)

    async def raise_not_found():
        raise NotFoundError("schedule 'sched-x' not found")

    async def raise_validation():
        raise ValidationError("invalid cron: '99 99 * * *'")

    async def raise_conflict():
        raise ConflictError("already exists")

    async def raise_server_error():
        raise NexusError("secret internal detail that must not leak")

    async def raise_plain():
        raise RuntimeError("uncaught plain error")

    app.register_endpoint("/err/notfound", ["GET"], raise_not_found)
    app.register_endpoint("/err/validation", ["GET"], raise_validation)
    app.register_endpoint("/err/conflict", ["GET"], raise_conflict)
    app.register_endpoint("/err/server", ["GET"], raise_server_error)
    app.register_endpoint("/err/plain", ["GET"], raise_plain)

    assert app.fastapi_app is not None  # eager gateway init guarantees this
    client = TestClient(app.fastapi_app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        try:
            app.stop()
        except Exception:
            pass


@pytest.mark.integration
class TestNexusErrorHttpMapping:
    """Typed NexusError subclasses map to their declared status + body shape."""

    def test_not_found_maps_to_404(self, client_with_error_routes):
        resp = client_with_error_routes.get("/err/notfound")
        assert resp.status_code == 404
        body = resp.json()
        assert body == {
            "error": "not_found",
            "detail": "schedule 'sched-x' not found",
        }

    def test_validation_maps_to_400(self, client_with_error_routes):
        resp = client_with_error_routes.get("/err/validation")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "validation_error"
        assert "invalid cron" in body["detail"]

    def test_conflict_maps_to_409(self, client_with_error_routes):
        resp = client_with_error_routes.get("/err/conflict")
        assert resp.status_code == 409
        assert resp.json()["error"] == "conflict"

    def test_5xx_does_not_leak_detail(self, client_with_error_routes):
        """A 5xx NexusError returns the error_code but a generic detail."""
        resp = client_with_error_routes.get("/err/server")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"] == "internal_error"
        # The developer-set detail MUST NOT reach the client on 5xx.
        assert "secret internal detail" not in body["detail"]
        assert body["detail"] == "internal server error"

    def test_plain_exception_unaffected(self, client_with_error_routes):
        """Non-NexusError exceptions are not swallowed by the handler."""
        resp = client_with_error_routes.get("/err/plain")
        assert resp.status_code == 500
