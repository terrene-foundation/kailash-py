# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for CSRF middleware (S4-004).

Covers:
- Safe method bypass (GET, HEAD, OPTIONS)
- Unsafe method validation (POST, PUT, DELETE, PATCH)
- Origin header matching
- Referer header fallback
- Missing origin handling
- Exempt paths
- Case-insensitive origin matching
"""

from __future__ import annotations

import json

import pytest

from nexus.middleware.csrf import CSRFMiddleware, _extract_origin


class TestOriginExtraction:
    """Test _extract_origin helper."""

    def test_simple_origin(self):
        assert _extract_origin("https://example.com") == "https://example.com"

    def test_origin_with_port(self):
        assert (
            _extract_origin("https://example.com:8080") == "https://example.com:8080"
        )

    def test_full_url_extracts_origin(self):
        assert (
            _extract_origin("https://example.com/path?query=1")
            == "https://example.com"
        )

    def test_empty_string(self):
        assert _extract_origin("") is None

    def test_invalid_url(self):
        assert _extract_origin("not-a-url") is None

    def test_no_scheme(self):
        assert _extract_origin("example.com") is None


class TestCSRFSafeMethods:
    """Test that safe methods bypass CSRF validation."""

    @pytest.fixture
    def app_response(self):
        """Run a request through CSRF middleware and return status code."""

        async def run(method, path="/api/test", origin=None, referer=None):
            status_code = None
            body = None

            async def dummy_app(scope, receive, send):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [],
                    }
                )
                await send({"type": "http.response.body", "body": b"ok"})

            mw = CSRFMiddleware(
                dummy_app,
                allowed_origins=["https://app.example.com"],
            )

            headers = []
            if origin:
                headers.append((b"origin", origin.encode()))
            if referer:
                headers.append((b"referer", referer.encode()))

            scope = {
                "type": "http",
                "method": method,
                "path": path,
                "headers": headers,
            }

            sent = []

            async def mock_send(msg):
                sent.append(msg)

            async def mock_receive():
                return {"type": "http.request", "body": b""}

            await mw(scope, mock_receive, mock_send)

            for msg in sent:
                if msg["type"] == "http.response.start":
                    status_code = msg["status"]
                if msg["type"] == "http.response.body":
                    body = msg.get("body", b"")

            return status_code, body

        return run

    @pytest.mark.asyncio
    async def test_get_bypasses_csrf(self, app_response):
        status, _ = await app_response("GET")
        assert status == 200

    @pytest.mark.asyncio
    async def test_head_bypasses_csrf(self, app_response):
        status, _ = await app_response("HEAD")
        assert status == 200

    @pytest.mark.asyncio
    async def test_options_bypasses_csrf(self, app_response):
        status, _ = await app_response("OPTIONS")
        assert status == 200


class TestCSRFUnsafeMethods:
    """Test that unsafe methods require valid origin."""

    @pytest.fixture
    def csrf_check(self):
        """Run an unsafe request and return status code."""

        async def run(
            method="POST",
            origin=None,
            referer=None,
            allowed_origins=None,
            allow_missing_origin=False,
            path="/api/test",
            exempt_paths=None,
        ):
            status_code = None

            async def dummy_app(scope, receive, send):
                await send(
                    {"type": "http.response.start", "status": 200, "headers": []}
                )
                await send({"type": "http.response.body", "body": b"ok"})

            mw = CSRFMiddleware(
                dummy_app,
                allowed_origins=allowed_origins or ["https://app.example.com"],
                allow_missing_origin=allow_missing_origin,
                exempt_paths=exempt_paths,
            )

            headers = []
            if origin:
                headers.append((b"origin", origin.encode()))
            if referer:
                headers.append((b"referer", referer.encode()))

            scope = {
                "type": "http",
                "method": method,
                "path": path,
                "headers": headers,
            }

            sent = []

            async def mock_send(msg):
                sent.append(msg)

            async def mock_receive():
                return {"type": "http.request", "body": b""}

            await mw(scope, mock_receive, mock_send)

            for msg in sent:
                if msg["type"] == "http.response.start":
                    status_code = msg["status"]

            return status_code

        return run

    @pytest.mark.asyncio
    async def test_post_with_valid_origin(self, csrf_check):
        status = await csrf_check(method="POST", origin="https://app.example.com")
        assert status == 200

    @pytest.mark.asyncio
    async def test_post_with_invalid_origin(self, csrf_check):
        status = await csrf_check(method="POST", origin="https://evil.com")
        assert status == 403

    @pytest.mark.asyncio
    async def test_put_with_valid_origin(self, csrf_check):
        status = await csrf_check(method="PUT", origin="https://app.example.com")
        assert status == 200

    @pytest.mark.asyncio
    async def test_delete_with_invalid_origin(self, csrf_check):
        status = await csrf_check(method="DELETE", origin="https://attacker.com")
        assert status == 403

    @pytest.mark.asyncio
    async def test_patch_with_valid_origin(self, csrf_check):
        status = await csrf_check(method="PATCH", origin="https://app.example.com")
        assert status == 200

    @pytest.mark.asyncio
    async def test_missing_origin_rejected_by_default(self, csrf_check):
        status = await csrf_check(method="POST")
        assert status == 403

    @pytest.mark.asyncio
    async def test_missing_origin_allowed_when_configured(self, csrf_check):
        status = await csrf_check(method="POST", allow_missing_origin=True)
        assert status == 200

    @pytest.mark.asyncio
    async def test_referer_fallback(self, csrf_check):
        """When Origin is missing, Referer is used as fallback."""
        status = await csrf_check(
            method="POST", referer="https://app.example.com/page"
        )
        assert status == 200

    @pytest.mark.asyncio
    async def test_referer_invalid(self, csrf_check):
        status = await csrf_check(method="POST", referer="https://evil.com/page")
        assert status == 403

    @pytest.mark.asyncio
    async def test_origin_case_insensitive(self, csrf_check):
        status = await csrf_check(method="POST", origin="HTTPS://APP.EXAMPLE.COM")
        assert status == 200

    @pytest.mark.asyncio
    async def test_origin_trailing_slash_normalized(self, csrf_check):
        """Origins with trailing slashes should be handled."""
        status = await csrf_check(
            method="POST",
            origin="https://app.example.com",
            allowed_origins=["https://app.example.com/"],
        )
        assert status == 200

    @pytest.mark.asyncio
    async def test_exempt_path(self, csrf_check):
        """Exempt paths bypass CSRF validation."""
        status = await csrf_check(
            method="POST",
            path="/webhooks/stripe",
            exempt_paths=["/webhooks/stripe"],
        )
        assert status == 200

    @pytest.mark.asyncio
    async def test_non_exempt_path_still_validated(self, csrf_check):
        status = await csrf_check(
            method="POST",
            path="/api/test",
            origin="https://evil.com",
            exempt_paths=["/webhooks/stripe"],
        )
        assert status == 403


class TestCSRFNonHTTP:
    """Test CSRF middleware with non-HTTP scopes."""

    @pytest.mark.asyncio
    async def test_websocket_passthrough(self):
        call_count = 0

        async def dummy_app(scope, receive, send):
            nonlocal call_count
            call_count += 1

        mw = CSRFMiddleware(dummy_app, allowed_origins=["https://example.com"])
        scope = {"type": "websocket", "path": "/ws"}
        await mw(scope, None, None)
        assert call_count == 1


class TestCSRFResponseBody:
    """Test CSRF error response format."""

    @pytest.mark.asyncio
    async def test_error_response_is_json(self):
        async def dummy_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        mw = CSRFMiddleware(
            dummy_app, allowed_origins=["https://app.example.com"]
        )

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/test",
            "headers": [(b"origin", b"https://evil.com")],
        }

        sent = []

        async def mock_send(msg):
            sent.append(msg)

        async def mock_receive():
            return {"type": "http.request", "body": b""}

        await mw(scope, mock_receive, mock_send)

        body_msg = [m for m in sent if m["type"] == "http.response.body"][0]
        body = json.loads(body_msg["body"])
        assert "error" in body
        assert "CSRF" in body["error"]
