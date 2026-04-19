# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Integration tests (Tier 2) for ``nexus.http_client.HttpClient``.

Uses ``pytest-httpserver`` to exercise every verb (GET/POST/PUT/DELETE/PATCH)
plus streaming against a real HTTP server listening on 127.0.0.1. The
``allow_loopback=True`` carve-out is exercised here — production callers
would not set it, but tests against a local stub must.

Contract exercised:

* Full end-to-end wiring: HttpClient -> SafeDnsTransport -> httpx ->
  pytest-httpserver -> response parsed and returned.
* request_id injected as X-Request-ID header on the outgoing request.
* Redirects NOT followed by default (SafeDnsTransport guard runs per hop
  when enabled).
* Body streaming returns chunks.
"""

from __future__ import annotations

import json

import pytest

from nexus.http_client import HttpClient, HttpClientConfig


@pytest.fixture
def loopback_client() -> HttpClient:
    """HttpClient with allow_loopback=True for loopback-only tests."""
    return HttpClient(
        HttpClientConfig(
            allow_loopback=True,
            timeout_seconds=5.0,
            connect_timeout_seconds=5.0,
        )
    )


@pytest.mark.integration
class TestHttpClientVerbs:
    """Every verb round-trips against a real HTTP server."""

    @pytest.mark.asyncio
    async def test_get_returns_body(
        self, httpserver, loopback_client: HttpClient
    ) -> None:
        httpserver.expect_request("/api").respond_with_json({"ok": True})
        try:
            resp = await loopback_client.get(httpserver.url_for("/api"))
            assert resp.status_code == 200
            assert json.loads(resp.body) == {"ok": True}
        finally:
            await loopback_client.aclose()

    @pytest.mark.asyncio
    async def test_post_sends_json_body(
        self, httpserver, loopback_client: HttpClient
    ) -> None:
        httpserver.expect_request("/users", method="POST").respond_with_json({"id": 42})
        try:
            resp = await loopback_client.post(
                httpserver.url_for("/users"),
                json={"name": "Alice"},
            )
            assert resp.status_code == 200
            assert json.loads(resp.body) == {"id": 42}
        finally:
            await loopback_client.aclose()

    @pytest.mark.asyncio
    async def test_put_updates_resource(
        self, httpserver, loopback_client: HttpClient
    ) -> None:
        httpserver.expect_request("/users/42", method="PUT").respond_with_json(
            {"updated": True}
        )
        try:
            resp = await loopback_client.put(
                httpserver.url_for("/users/42"),
                json={"name": "Bob"},
            )
            assert resp.status_code == 200
            assert json.loads(resp.body) == {"updated": True}
        finally:
            await loopback_client.aclose()

    @pytest.mark.asyncio
    async def test_delete_returns_204(
        self, httpserver, loopback_client: HttpClient
    ) -> None:
        httpserver.expect_request("/users/42", method="DELETE").respond_with_data(
            "", status=204
        )
        try:
            resp = await loopback_client.delete(httpserver.url_for("/users/42"))
            assert resp.status_code == 204
        finally:
            await loopback_client.aclose()

    @pytest.mark.asyncio
    async def test_patch_partial_update(
        self, httpserver, loopback_client: HttpClient
    ) -> None:
        httpserver.expect_request("/users/42", method="PATCH").respond_with_json(
            {"patched": True}
        )
        try:
            resp = await loopback_client.patch(
                httpserver.url_for("/users/42"),
                json={"name": "Charlie"},
            )
            assert resp.status_code == 200
            assert json.loads(resp.body) == {"patched": True}
        finally:
            await loopback_client.aclose()


@pytest.mark.integration
class TestHttpClientHeaders:
    """Header plumbing: correlation ID injection + per-call headers."""

    @pytest.mark.asyncio
    async def test_request_id_injected(
        self, httpserver, loopback_client: HttpClient
    ) -> None:
        from werkzeug.wrappers import Response

        received_headers: dict[str, str] = {}

        def handler(request) -> Response:
            received_headers.update(request.headers)
            return Response("", status=200)

        httpserver.expect_request("/x").respond_with_handler(handler)
        try:
            resp = await loopback_client.get(
                httpserver.url_for("/x"), request_id="test-abc-123"
            )
            assert resp.request_id == "test-abc-123"
            assert received_headers.get("X-Request-Id") == "test-abc-123"
        finally:
            await loopback_client.aclose()

    @pytest.mark.asyncio
    async def test_per_call_header_merged(
        self, httpserver, loopback_client: HttpClient
    ) -> None:
        from werkzeug.wrappers import Response

        received_headers: dict[str, str] = {}

        def handler(request) -> Response:
            received_headers.update(request.headers)
            return Response("", status=200)

        httpserver.expect_request("/x").respond_with_handler(handler)
        try:
            await loopback_client.get(
                httpserver.url_for("/x"),
                headers={"X-Custom": "value-42"},
            )
            assert received_headers.get("X-Custom") == "value-42"
        finally:
            await loopback_client.aclose()


@pytest.mark.integration
class TestHttpClientStreaming:
    @pytest.mark.asyncio
    async def test_stream_returns_chunks(
        self, httpserver, loopback_client: HttpClient
    ) -> None:
        payload = b"x" * 32768  # 32 KiB — exceeds default chunk size
        httpserver.expect_request("/big").respond_with_data(payload)
        try:
            stream = await loopback_client.stream(
                "GET", httpserver.url_for("/big"), chunk_size=4096
            )
            collected = b""
            async for chunk in stream:
                collected += chunk
            assert collected == payload
        finally:
            await loopback_client.aclose()


@pytest.mark.integration
class TestHttpClientRedirects:
    """Default follow_redirects=False — caller must opt in."""

    @pytest.mark.asyncio
    async def test_default_does_not_follow_redirect(
        self, httpserver, loopback_client: HttpClient
    ) -> None:
        httpserver.expect_request("/from").respond_with_data(
            "",
            status=302,
            headers={"Location": httpserver.url_for("/to")},
        )
        httpserver.expect_request("/to").respond_with_json({"ok": True})
        try:
            resp = await loopback_client.get(httpserver.url_for("/from"))
            # Redirect NOT followed by default.
            assert resp.status_code == 302
        finally:
            await loopback_client.aclose()


@pytest.mark.integration
class TestHttpClientSsrfAtConnect:
    """SafeDnsTransport runs at connect time — per-hop SSRF defence."""

    @pytest.mark.asyncio
    async def test_default_config_blocks_loopback(self, httpserver) -> None:
        """Without allow_loopback, default config rejects 127.0.0.1.

        Proves that the production default (allow_loopback=False) is
        SSRF-safe out of the box. Loopback hostname resolution at connect
        time is blocked even though the caller technically has access to
        a local HTTP server. This is the expected shape for production
        deployments where every HttpClient call targets external services.
        """
        client = HttpClient(HttpClientConfig())  # no allow_loopback
        try:
            from nexus.http_client import InvalidEndpointError

            with pytest.raises(InvalidEndpointError):
                await client.get(httpserver.url_for("/anything"))
        finally:
            await client.aclose()
