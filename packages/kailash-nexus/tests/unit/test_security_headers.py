# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for security headers middleware (S4-003).

Covers:
- SecurityHeadersConfig default values
- Header pair generation
- Custom configuration
- ASGI middleware behavior
- Path exclusions
- Frozen config immutability
"""

from __future__ import annotations

import pytest

from nexus.middleware.security_headers import SecurityHeadersConfig, SecurityHeadersMiddleware


class TestSecurityHeadersConfig:
    """Test SecurityHeadersConfig defaults and customization."""

    def test_default_csp(self):
        config = SecurityHeadersConfig()
        assert "default-src 'self'" in config.csp
        assert "frame-ancestors 'none'" in config.csp

    def test_default_hsts(self):
        config = SecurityHeadersConfig()
        assert config.hsts_max_age == 31536000  # 1 year
        assert config.hsts_include_subdomains is True
        assert config.hsts_preload is False

    def test_default_content_type_options(self):
        config = SecurityHeadersConfig()
        assert config.content_type_options == "nosniff"

    def test_default_frame_options(self):
        config = SecurityHeadersConfig()
        assert config.frame_options == "DENY"

    def test_default_xss_protection(self):
        config = SecurityHeadersConfig()
        assert config.xss_protection == "1; mode=block"

    def test_default_referrer_policy(self):
        config = SecurityHeadersConfig()
        assert config.referrer_policy == "strict-origin-when-cross-origin"

    def test_default_permissions_policy(self):
        config = SecurityHeadersConfig()
        assert "camera=()" in config.permissions_policy

    def test_frozen_immutability(self):
        config = SecurityHeadersConfig()
        with pytest.raises(AttributeError):
            config.csp = "new-policy"

    def test_custom_frame_options(self):
        config = SecurityHeadersConfig(frame_options="SAMEORIGIN")
        assert config.frame_options == "SAMEORIGIN"

    def test_custom_hsts_preload(self):
        config = SecurityHeadersConfig(hsts_preload=True)
        assert config.hsts_preload is True


class TestHeaderPairGeneration:
    """Test to_header_pairs() output."""

    def test_default_header_count(self):
        config = SecurityHeadersConfig()
        pairs = config.to_header_pairs()
        # CSP, HSTS, X-Content-Type-Options, X-Frame-Options,
        # X-XSS-Protection, Referrer-Policy, Permissions-Policy
        assert len(pairs) == 7

    def test_csp_header_present(self):
        config = SecurityHeadersConfig()
        pairs = dict(config.to_header_pairs())
        assert "content-security-policy" in pairs
        assert "default-src 'self'" in pairs["content-security-policy"]

    def test_hsts_header_format(self):
        config = SecurityHeadersConfig()
        pairs = dict(config.to_header_pairs())
        hsts = pairs["strict-transport-security"]
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" not in hsts

    def test_hsts_with_preload(self):
        config = SecurityHeadersConfig(hsts_preload=True)
        pairs = dict(config.to_header_pairs())
        hsts = pairs["strict-transport-security"]
        assert "preload" in hsts

    def test_hsts_without_subdomains(self):
        config = SecurityHeadersConfig(hsts_include_subdomains=False)
        pairs = dict(config.to_header_pairs())
        hsts = pairs["strict-transport-security"]
        assert "includeSubDomains" not in hsts

    def test_all_expected_headers(self):
        config = SecurityHeadersConfig()
        pairs = dict(config.to_header_pairs())
        expected_headers = {
            "content-security-policy",
            "strict-transport-security",
            "x-content-type-options",
            "x-frame-options",
            "x-xss-protection",
            "referrer-policy",
            "permissions-policy",
        }
        assert set(pairs.keys()) == expected_headers

    def test_empty_csp_omits_header(self):
        config = SecurityHeadersConfig(csp="")
        pairs = dict(config.to_header_pairs())
        assert "content-security-policy" not in pairs

    def test_empty_frame_options_omits_header(self):
        config = SecurityHeadersConfig(frame_options="")
        pairs = dict(config.to_header_pairs())
        assert "x-frame-options" not in pairs


class TestSecurityHeadersMiddleware:
    """Test ASGI middleware behavior."""

    @pytest.fixture
    def captured_headers(self):
        """Fixture that captures response headers from middleware."""
        captured = {}

        async def dummy_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": b"{}"})

        async def run(scope, middleware_cls, **kwargs):
            mw = middleware_cls(dummy_app, **kwargs)
            sent_messages = []

            async def mock_send(msg):
                sent_messages.append(msg)

            async def mock_receive():
                return {"type": "http.request", "body": b""}

            await mw(scope, mock_receive, mock_send)

            for msg in sent_messages:
                if msg["type"] == "http.response.start":
                    for name, value in msg.get("headers", []):
                        if isinstance(name, bytes):
                            name = name.decode()
                        if isinstance(value, bytes):
                            value = value.decode()
                        captured[name] = value

            return captured

        return run

    @pytest.mark.asyncio
    async def test_injects_security_headers(self, captured_headers):
        scope = {"type": "http", "method": "GET", "path": "/api/test"}
        headers = await captured_headers(scope, SecurityHeadersMiddleware)
        assert "x-content-type-options" in headers
        assert headers["x-content-type-options"] == "nosniff"
        assert "x-frame-options" in headers

    @pytest.mark.asyncio
    async def test_preserves_existing_headers(self, captured_headers):
        scope = {"type": "http", "method": "GET", "path": "/api/test"}
        headers = await captured_headers(scope, SecurityHeadersMiddleware)
        assert "content-type" in headers

    @pytest.mark.asyncio
    async def test_path_exclusion(self, captured_headers):
        config = SecurityHeadersConfig(exclude_paths=("/healthz",))
        scope = {"type": "http", "method": "GET", "path": "/healthz"}
        headers = await captured_headers(
            scope, SecurityHeadersMiddleware, config=config
        )
        # Security headers should NOT be present on excluded paths
        assert "x-frame-options" not in headers

    @pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        """Non-HTTP scopes should pass through without modification."""
        call_count = 0

        async def dummy_app(scope, receive, send):
            nonlocal call_count
            call_count += 1

        mw = SecurityHeadersMiddleware(dummy_app)
        scope = {"type": "websocket", "path": "/ws"}

        await mw(scope, None, None)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_custom_config(self, captured_headers):
        config = SecurityHeadersConfig(
            frame_options="SAMEORIGIN",
            referrer_policy="no-referrer",
        )
        scope = {"type": "http", "method": "GET", "path": "/test"}
        headers = await captured_headers(
            scope, SecurityHeadersMiddleware, config=config
        )
        assert headers["x-frame-options"] == "SAMEORIGIN"
        assert headers["referrer-policy"] == "no-referrer"
