# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Integration tests (Tier 2) for ``nexus.service_client.ServiceClient``.

Exercises every typed JSON verb + every raw variant against a real HTTP
server. Typed variants auto-deserialise 2xx responses and raise
``ServiceClientHttpStatusError`` on non-2xx. Raw variants return the full
``HttpResponse`` without status checking.

These tests double as orphan-detection coverage per
``rules/facade-manager-detection.md`` — ServiceClient is exercised through
its public surface against a real server, proving the wiring is live.
"""

from __future__ import annotations

import pytest

from nexus.service_client import (
    ServiceClient,
    ServiceClientHttpStatusError,
)


@pytest.fixture
def service(httpserver) -> "ServiceClient":
    """ServiceClient pointing at the pytest-httpserver root.

    Uses ``allow_loopback=True`` because the test server binds 127.0.0.1.
    Production callers must never set this.
    """
    base = f"http://{httpserver.host}:{httpserver.port}"
    return ServiceClient(
        base,
        bearer_token="test-token-xyz",
        allow_loopback=True,
        timeout_secs=5.0,
    )


@pytest.mark.integration
class TestServiceClientTypedVerbs:
    """Typed variants — JSON in, JSON out, 2xx asserted."""

    @pytest.mark.asyncio
    async def test_typed_get(self, httpserver, service: ServiceClient) -> None:
        httpserver.expect_request("/users/42").respond_with_json(
            {"id": 42, "name": "Alice"}
        )
        try:
            result = await service.get("/users/42")
            assert result == {"id": 42, "name": "Alice"}
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_typed_post(self, httpserver, service: ServiceClient) -> None:
        httpserver.expect_request("/users", method="POST").respond_with_json(
            {"id": 1, "created": True}
        )
        try:
            result = await service.post(
                "/users", {"name": "Alice", "email": "a@example.com"}
            )
            assert result == {"id": 1, "created": True}
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_typed_put(self, httpserver, service: ServiceClient) -> None:
        httpserver.expect_request("/users/42", method="PUT").respond_with_json(
            {"updated": True}
        )
        try:
            result = await service.put("/users/42", {"name": "Alice Updated"})
            assert result == {"updated": True}
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_typed_delete(self, httpserver, service: ServiceClient) -> None:
        httpserver.expect_request("/users/42", method="DELETE").respond_with_json(
            {"deleted": True}
        )
        try:
            result = await service.delete("/users/42")
            assert result == {"deleted": True}
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_typed_delete_204_returns_none(
        self, httpserver, service: ServiceClient
    ) -> None:
        httpserver.expect_request("/users/42", method="DELETE").respond_with_data(
            "", status=204
        )
        try:
            result = await service.delete("/users/42")
            assert result is None
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_typed_non_2xx_raises_status_error(
        self, httpserver, service: ServiceClient
    ) -> None:
        httpserver.expect_request("/missing").respond_with_data(
            "not found here", status=404
        )
        try:
            with pytest.raises(ServiceClientHttpStatusError) as exc_info:
                await service.get("/missing")
            assert exc_info.value.status_code == 404
            assert b"not found here" in exc_info.value.body
        finally:
            await service.aclose()


@pytest.mark.integration
class TestServiceClientRawVerbs:
    """Raw variants — return HttpResponse, no status check."""

    @pytest.mark.asyncio
    async def test_get_raw_non_2xx_does_not_raise(
        self, httpserver, service: ServiceClient
    ) -> None:
        httpserver.expect_request("/missing").respond_with_data("{}", status=404)
        try:
            resp = await service.get_raw("/missing")
            assert resp.status_code == 404
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_post_raw(self, httpserver, service: ServiceClient) -> None:
        httpserver.expect_request("/webhook", method="POST").respond_with_json(
            {"received": True}
        )
        try:
            resp = await service.post_raw("/webhook", {"event": "x"})
            assert resp.status_code == 200
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_put_raw(self, httpserver, service: ServiceClient) -> None:
        httpserver.expect_request("/users/42", method="PUT").respond_with_json(
            {"updated": True}
        )
        try:
            resp = await service.put_raw("/users/42", {"name": "Alice"})
            assert resp.status_code == 200
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_delete_raw(self, httpserver, service: ServiceClient) -> None:
        httpserver.expect_request("/users/42", method="DELETE").respond_with_data(
            "", status=204
        )
        try:
            resp = await service.delete_raw("/users/42")
            assert resp.status_code == 204
        finally:
            await service.aclose()


@pytest.mark.integration
class TestServiceClientAuthHeader:
    """Bearer token stored at construction must appear on every request."""

    @pytest.mark.asyncio
    async def test_bearer_token_sent_on_request(
        self, httpserver, service: ServiceClient
    ) -> None:
        from werkzeug.wrappers import Response

        received_headers: dict[str, str] = {}

        def handler(request) -> Response:
            received_headers.update(request.headers)
            return Response(
                '{"ok": true}',
                status=200,
                content_type="application/json",
            )

        httpserver.expect_request("/auth-check").respond_with_handler(handler)
        try:
            await service.get("/auth-check")
            assert received_headers.get("Authorization") == "Bearer test-token-xyz"
        finally:
            await service.aclose()

    @pytest.mark.asyncio
    async def test_no_bearer_means_no_auth_header(self, httpserver) -> None:
        from werkzeug.wrappers import Response

        base = f"http://{httpserver.host}:{httpserver.port}"
        client = ServiceClient(base, bearer_token=None, allow_loopback=True)
        received_headers: dict[str, str] = {}

        def handler(request) -> Response:
            received_headers.update(request.headers)
            return Response("{}", status=200, content_type="application/json")

        httpserver.expect_request("/x").respond_with_handler(handler)
        try:
            await client.get_raw("/x")
            assert "Authorization" not in received_headers
        finally:
            await client.aclose()


@pytest.mark.integration
class TestServiceClientAllowlistOrdering:
    """Issue #473 NN1: allowlisted private IP STILL blocked."""

    @pytest.mark.asyncio
    async def test_allowlisted_loopback_still_blocked_without_allow_loopback(
        self, httpserver
    ) -> None:
        """The caller allowlists 127.0.0.1 but does NOT set allow_loopback.

        Expected: the SSRF guard rejects first, before the allowlist is
        consulted. No request reaches the server.
        """
        base = f"http://{httpserver.host}:{httpserver.port}"
        client = ServiceClient(
            base,
            allowed_hosts=["127.0.0.1", httpserver.host],
            allow_loopback=False,  # explicit — no carve-out
        )
        try:
            from nexus.service_client import ServiceClientHttpError

            with pytest.raises(ServiceClientHttpError):
                await client.get_raw("/any")
        finally:
            await client.aclose()
