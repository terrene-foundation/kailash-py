# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for FabricIntegrityMiddleware (gh#369).

Tests cover:
- Route classification (four-way: fabric_required, direct_storage, exempt, neutral)
- Bypass detection (fabric_hits=0 on fabric_required route)
- Null body detection (fabric_hits>=1 but body is null/empty)
- Direct storage detection
- Exempt routes skip all checks
- ContextVar lifecycle (reset between requests, no leak)
- Enforcement stage logging
- Configuration composition (extra_* prefixes)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import ANY

import pytest

from dataflow.fabric.integrity import (
    FabricIntegrityConfig,
    FabricIntegrityMiddleware,
    RouteClassification,
    _is_null_body,
    classify_route,
    get_current_integrity_trace,
    get_fabric_hit_count,
    record_fabric_hit,
)

# ---------------------------------------------------------------------------
# Helpers — minimal ASGI app stubs
# ---------------------------------------------------------------------------


def _make_asgi_app(
    status: int = 200,
    body: bytes = b'{"data": [1, 2, 3]}',
    fabric_hits: int = 0,
) -> Callable:
    """Build a minimal ASGI app that returns a fixed response.

    Args:
        status: HTTP status code.
        body: Response body bytes.
        fabric_hits: Number of times to call ``record_fabric_hit()``
            during request handling (simulates the serving layer).
    """

    async def app(
        scope: Dict[str, Any],
        receive: Callable,
        send: Callable,
    ) -> None:
        # Simulate fabric hits
        for _ in range(fabric_hits):
            record_fabric_hit()

        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )

    return app


def _make_scope(
    path: str = "/fabric/dashboard",
    method: str = "GET",
) -> Dict[str, Any]:
    """Build a minimal ASGI HTTP scope."""
    return {
        "type": "http",
        "path": path,
        "method": method,
    }


async def _null_receive() -> Dict[str, Any]:
    return {"type": "http.request", "body": b""}


class _SendCollector:
    """Collects ASGI send messages for assertion."""

    def __init__(self) -> None:
        self.messages: List[Dict[str, Any]] = []

    async def __call__(self, message: Dict[str, Any]) -> None:
        self.messages.append(message)

    @property
    def status(self) -> Optional[int]:
        for m in self.messages:
            if m.get("type") == "http.response.start":
                return m.get("status")
        return None

    @property
    def body(self) -> bytes:
        chunks = []
        for m in self.messages:
            if m.get("type") == "http.response.body":
                chunks.append(m.get("body", b""))
        return b"".join(chunks)


# =========================================================================
# Route Classification Tests
# =========================================================================


class TestClassifyRoute:
    """Tests for the pure classify_route function."""

    def test_default_fabric_routes(self) -> None:
        assert classify_route("/fabric/dashboard", "GET") == "fabric_required"
        assert classify_route("/fabric/users", "GET") == "fabric_required"
        assert classify_route("/fabric/_batch", "GET") == "fabric_required"

    def test_default_exempt_routes(self) -> None:
        assert classify_route("/health", "GET") == "exempt"
        assert classify_route("/healthcheck", "GET") == "exempt"
        assert classify_route("/fabric/_health", "GET") == "exempt"
        assert classify_route("/fabric/_trace/dashboard", "GET") == "exempt"
        assert classify_route("/fabric/metrics", "GET") == "exempt"
        assert classify_route("/docs", "GET") == "exempt"
        assert classify_route("/docs/api", "GET") == "exempt"
        assert classify_route("/openapi.json", "GET") == "exempt"
        assert classify_route("/redoc", "GET") == "exempt"
        assert classify_route("/auth/login", "POST") == "exempt"
        assert classify_route("/oauth/callback", "GET") == "exempt"
        assert classify_route("/.well-known/openid-configuration", "GET") == "exempt"
        assert classify_route("/favicon.ico", "GET") == "exempt"

    def test_options_always_exempt(self) -> None:
        assert classify_route("/fabric/dashboard", "OPTIONS") == "exempt"
        assert classify_route("/api/anything", "OPTIONS") == "exempt"
        assert classify_route("/unknown", "OPTIONS") == "exempt"

    def test_neutral_default(self) -> None:
        assert classify_route("/api/users", "GET") == "neutral"
        assert classify_route("/", "GET") == "neutral"
        assert classify_route("/some/random/path", "POST") == "neutral"

    def test_direct_storage_patterns(self) -> None:
        config = FabricIntegrityConfig(
            direct_storage_patterns=("/api/legacy/",),
        )
        assert classify_route("/api/legacy/users", "GET", config) == "direct_storage"
        assert classify_route("/api/legacy/", "GET", config) == "direct_storage"

    def test_extra_exempt_prefixes(self) -> None:
        config = FabricIntegrityConfig(
            extra_exempt_prefixes=("/api/webhook/",),
        )
        assert classify_route("/api/webhook/stripe", "POST", config) == "exempt"
        # Default exempt still works
        assert classify_route("/health", "GET", config) == "exempt"

    def test_extra_fabric_required_prefixes(self) -> None:
        config = FabricIntegrityConfig(
            extra_fabric_required_prefixes=("/api/products/",),
        )
        assert classify_route("/api/products/list", "GET", config) == "fabric_required"
        # Default fabric_required still works
        assert classify_route("/fabric/dashboard", "GET", config) == "fabric_required"

    def test_extra_direct_storage_patterns(self) -> None:
        config = FabricIntegrityConfig(
            extra_direct_storage_patterns=("/api/cache/",),
        )
        assert classify_route("/api/cache/users", "GET", config) == "direct_storage"

    def test_priority_exempt_over_fabric_required(self) -> None:
        """Exempt prefixes take priority over fabric-required."""
        # /fabric/_health starts with both /fabric/ (required) and
        # /fabric/_health (exempt). Exempt wins.
        assert classify_route("/fabric/_health", "GET") == "exempt"

    def test_priority_exempt_over_direct_storage(self) -> None:
        """Exempt prefixes take priority over direct-storage."""
        config = FabricIntegrityConfig(
            direct_storage_patterns=("/health",),
        )
        # /health matches both exempt and direct_storage. Exempt wins.
        assert classify_route("/health", "GET", config) == "exempt"

    def test_case_insensitive_method(self) -> None:
        assert classify_route("/fabric/dashboard", "options") == "exempt"
        assert classify_route("/fabric/dashboard", "Options") == "exempt"

    def test_empty_config_prefixes(self) -> None:
        """When all prefix tuples are empty, everything is neutral."""
        config = FabricIntegrityConfig(
            fabric_required_prefixes=(),
            direct_storage_patterns=(),
            exempt_prefixes=(),
            exempt_methods=(),
        )
        assert classify_route("/fabric/dashboard", "GET", config) == "neutral"
        assert classify_route("/health", "GET", config) == "neutral"
        assert classify_route("/api/legacy/users", "GET", config) == "neutral"


# =========================================================================
# Null Body Detection Tests
# =========================================================================


class TestIsNullBody:
    """Tests for _is_null_body response inspection."""

    def test_empty_bytes(self) -> None:
        assert _is_null_body(b"") is True

    def test_whitespace_only(self) -> None:
        assert _is_null_body(b"   ") is True
        assert _is_null_body(b"\n\t") is True

    def test_literal_null(self) -> None:
        assert _is_null_body(b"null") is True
        assert _is_null_body(b"  null  ") is True

    def test_literal_none(self) -> None:
        assert _is_null_body(b"None") is True

    def test_empty_object(self) -> None:
        assert _is_null_body(b"{}") is True

    def test_empty_array(self) -> None:
        assert _is_null_body(b"[]") is True

    def test_data_null_wrapper(self) -> None:
        assert _is_null_body(b'{"data": null}') is True
        assert _is_null_body(b'{"data":null}') is True

    def test_data_empty_object_wrapper(self) -> None:
        assert _is_null_body(b'{"data": {}}') is True
        assert _is_null_body(b'{"data":{}}') is True

    def test_data_empty_array_wrapper(self) -> None:
        assert _is_null_body(b'{"data": []}') is True
        assert _is_null_body(b'{"data":[]}') is True

    def test_real_data_not_null(self) -> None:
        assert _is_null_body(b'{"data": [1, 2, 3]}') is False
        assert _is_null_body(b'{"data": {"name": "Alice"}}') is False
        assert _is_null_body(b'{"users": []}') is False
        assert _is_null_body(b"Hello, world!") is False

    def test_non_empty_array(self) -> None:
        assert _is_null_body(b"[1]") is False

    def test_non_empty_object(self) -> None:
        assert _is_null_body(b'{"key": "value"}') is False


# =========================================================================
# ContextVar Lifecycle Tests
# =========================================================================


class TestContextVarLifecycle:
    """Tests for ContextVar-based hit counter and trace ID."""

    def test_default_hit_count_is_zero(self) -> None:
        assert get_fabric_hit_count() == 0

    def test_record_increments(self) -> None:
        from contextvars import copy_context

        ctx = copy_context()

        def _inner() -> int:
            record_fabric_hit()
            record_fabric_hit()
            record_fabric_hit()
            return get_fabric_hit_count()

        result = ctx.run(_inner)
        assert result == 3
        # Original context is unaffected
        assert get_fabric_hit_count() == 0

    def test_trace_id_default_none(self) -> None:
        assert get_current_integrity_trace() is None

    @pytest.mark.asyncio
    async def test_concurrent_requests_isolated(self) -> None:
        """ContextVars are per-task, so concurrent requests don't leak."""
        results: Dict[str, int] = {}

        async def simulate_request(name: str, hits: int) -> None:
            from contextvars import Token

            token: Token[int] = __import__(
                "dataflow.fabric.integrity", fromlist=["_fabric_hit_count"]
            )._fabric_hit_count.set(0)
            try:
                for _ in range(hits):
                    record_fabric_hit()
                # Yield to let other tasks run
                await asyncio.sleep(0)
                results[name] = get_fabric_hit_count()
            finally:
                __import__(
                    "dataflow.fabric.integrity", fromlist=["_fabric_hit_count"]
                )._fabric_hit_count.reset(token)

        await asyncio.gather(
            simulate_request("req_a", 2),
            simulate_request("req_b", 5),
            simulate_request("req_c", 0),
        )

        assert results["req_a"] == 2
        assert results["req_b"] == 5
        assert results["req_c"] == 0


# =========================================================================
# Middleware Integration Tests
# =========================================================================


class TestFabricIntegrityMiddleware:
    """Tests for the ASGI middleware end-to-end."""

    @pytest.mark.asyncio
    async def test_non_http_scope_passes_through(self) -> None:
        """Non-HTTP scopes (websocket, lifespan) pass through unchanged."""
        app = _make_asgi_app()
        middleware = FabricIntegrityMiddleware(app)
        calls: List[str] = []

        async def tracking_app(scope: Any, receive: Any, send: Any) -> None:
            calls.append("called")

        middleware_with_tracking = FabricIntegrityMiddleware(tracking_app)
        await middleware_with_tracking(
            {"type": "websocket"}, _null_receive, _SendCollector()
        )
        assert calls == ["called"]

    @pytest.mark.asyncio
    async def test_exempt_route_skips_checks(self) -> None:
        """Exempt routes pass through without ContextVar setup."""
        app = _make_asgi_app(status=200, body=b"ok")
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        await middleware(_make_scope(path="/health"), _null_receive, send)

        assert send.status == 200
        assert send.body == b"ok"

    @pytest.mark.asyncio
    async def test_neutral_route_skips_checks(self) -> None:
        """Neutral routes pass through without ContextVar setup."""
        app = _make_asgi_app(status=200, body=b"ok")
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        await middleware(_make_scope(path="/api/users"), _null_receive, send)

        assert send.status == 200

    @pytest.mark.asyncio
    async def test_bypass_detection(self, caplog: pytest.LogCaptureFixture) -> None:
        """fabric_required route with 0 fabric hits emits bypass WARN."""
        app = _make_asgi_app(status=200, body=b'{"data": "ok"}', fabric_hits=0)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        assert send.status == 200
        assert any("fabric.integrity.bypass" in r.message for r in caplog.records)
        # Verify structured fields
        bypass_record = next(
            r for r in caplog.records if "fabric.integrity.bypass" in r.message
        )
        assert bypass_record.route == "/fabric/dashboard"
        assert bypass_record.fabric_hits == 0
        assert bypass_record.trace_id is not None

    @pytest.mark.asyncio
    async def test_null_body_detection(self, caplog: pytest.LogCaptureFixture) -> None:
        """fabric_required route with fabric hits but null body emits null_body WARN."""
        app = _make_asgi_app(status=200, body=b'{"data": null}', fabric_hits=1)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        assert send.status == 200
        assert any("fabric.integrity.null_body" in r.message for r in caplog.records)
        null_record = next(
            r for r in caplog.records if "fabric.integrity.null_body" in r.message
        )
        assert null_record.fabric_hits == 1

    @pytest.mark.asyncio
    async def test_ok_detection(self, caplog: pytest.LogCaptureFixture) -> None:
        """fabric_required route with fabric hits and real data emits ok DEBUG."""
        app = _make_asgi_app(status=200, body=b'{"data": [1, 2, 3]}', fabric_hits=1)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.DEBUG, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        assert send.status == 200
        assert any("fabric.integrity.ok" in r.message for r in caplog.records)
        ok_record = next(
            r for r in caplog.records if "fabric.integrity.ok" in r.message
        )
        assert ok_record.fabric_hits == 1

    @pytest.mark.asyncio
    async def test_direct_storage_detection(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """direct_storage route with 2xx emits direct_storage WARN."""
        config = FabricIntegrityConfig(
            direct_storage_patterns=("/api/legacy/",),
        )
        app = _make_asgi_app(status=200, body=b'{"users": []}')
        middleware = FabricIntegrityMiddleware(app, config=config)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/api/legacy/users"), _null_receive, send)

        assert send.status == 200
        assert any(
            "fabric.integrity.direct_storage" in r.message for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_non_2xx_skips_checks(self, caplog: pytest.LogCaptureFixture) -> None:
        """Non-2xx responses on fabric_required routes do not trigger WARNs."""
        app = _make_asgi_app(status=404, body=b"Not found", fabric_hits=0)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/missing"), _null_receive, send)

        assert send.status == 404
        # No bypass/null_body WARNs for non-2xx
        assert not any("fabric.integrity.bypass" in r.message for r in caplog.records)
        assert not any(
            "fabric.integrity.null_body" in r.message for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_500_response_skips_checks(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Server errors skip integrity checks."""
        app = _make_asgi_app(status=500, body=b"Internal error", fabric_hits=0)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        assert not any("fabric.integrity.bypass" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_contextvar_reset_after_request(self) -> None:
        """ContextVars are reset to defaults after the middleware runs."""
        app = _make_asgi_app(status=200, body=b'{"data": "ok"}', fabric_hits=3)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        # After the request completes, ContextVars should be back to defaults
        assert get_fabric_hit_count() == 0
        assert get_current_integrity_trace() is None

    @pytest.mark.asyncio
    async def test_trace_id_is_12_hex_chars(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Trace IDs are 12-character hex strings."""
        app = _make_asgi_app(status=200, body=b'{"data": "ok"}', fabric_hits=1)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.DEBUG, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        ok_record = next(
            r for r in caplog.records if "fabric.integrity.ok" in r.message
        )
        trace_id = ok_record.trace_id
        assert isinstance(trace_id, str)
        assert len(trace_id) == 12
        # Hex characters only
        int(trace_id, 16)

    @pytest.mark.asyncio
    async def test_empty_body_chunks(self, caplog: pytest.LogCaptureFixture) -> None:
        """A response with no body bytes triggers null_body when fabric_required."""
        app = _make_asgi_app(status=200, body=b"", fabric_hits=1)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        assert any("fabric.integrity.null_body" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_multiple_fabric_hits(self, caplog: pytest.LogCaptureFixture) -> None:
        """Multiple fabric hits are counted correctly."""
        app = _make_asgi_app(status=200, body=b'{"data": "ok"}', fabric_hits=5)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.DEBUG, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        ok_record = next(
            r for r in caplog.records if "fabric.integrity.ok" in r.message
        )
        assert ok_record.fabric_hits == 5


# =========================================================================
# Enforcement Stage Tests
# =========================================================================


class TestEnforcementStages:
    """Tests for the three enforcement stages."""

    @pytest.mark.asyncio
    async def test_observation_no_enforcement(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Observation mode logs but does not emit enforcement events."""
        config = FabricIntegrityConfig(enforcement_stage="observation")
        app = _make_asgi_app(status=200, body=b'{"data": "ok"}', fabric_hits=0)
        middleware = FabricIntegrityMiddleware(app, config=config)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        assert any("fabric.integrity.bypass" in r.message for r in caplog.records)
        assert not any(
            "fabric.integrity.enforcement" in r.message for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_per_prefix_enforces_bypass(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """per_prefix mode emits enforcement event on bypass."""
        config = FabricIntegrityConfig(enforcement_stage="per_prefix")
        app = _make_asgi_app(status=200, body=b'{"data": "ok"}', fabric_hits=0)
        middleware = FabricIntegrityMiddleware(app, config=config)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        assert any("fabric.integrity.bypass" in r.message for r in caplog.records)
        assert any("fabric.integrity.enforcement" in r.message for r in caplog.records)
        enforcement_record = next(
            r for r in caplog.records if "fabric.integrity.enforcement" in r.message
        )
        assert enforcement_record.enforcement_stage == "per_prefix"
        assert enforcement_record.action == "would_block"

    @pytest.mark.asyncio
    async def test_per_prefix_does_not_enforce_null_body(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """per_prefix mode does NOT enforce null_body (only fail_closed does)."""
        config = FabricIntegrityConfig(enforcement_stage="per_prefix")
        app = _make_asgi_app(status=200, body=b'{"data": null}', fabric_hits=1)
        middleware = FabricIntegrityMiddleware(app, config=config)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        assert any("fabric.integrity.null_body" in r.message for r in caplog.records)
        assert not any(
            "fabric.integrity.enforcement" in r.message for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_fail_closed_enforces_null_body(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """fail_closed mode enforces null_body."""
        config = FabricIntegrityConfig(enforcement_stage="fail_closed")
        app = _make_asgi_app(status=200, body=b'{"data": null}', fabric_hits=1)
        middleware = FabricIntegrityMiddleware(app, config=config)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        assert any("fabric.integrity.null_body" in r.message for r in caplog.records)
        assert any("fabric.integrity.enforcement" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_fail_closed_enforces_direct_storage(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """fail_closed mode enforces direct_storage."""
        config = FabricIntegrityConfig(
            enforcement_stage="fail_closed",
            direct_storage_patterns=("/api/legacy/",),
        )
        app = _make_asgi_app(status=200, body=b'{"users": []}')
        middleware = FabricIntegrityMiddleware(app, config=config)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/api/legacy/users"), _null_receive, send)

        assert any(
            "fabric.integrity.direct_storage" in r.message for r in caplog.records
        )
        assert any("fabric.integrity.enforcement" in r.message for r in caplog.records)


# =========================================================================
# Configuration Tests
# =========================================================================


class TestFabricIntegrityConfig:
    """Tests for FabricIntegrityConfig composition."""

    def test_default_config(self) -> None:
        config = FabricIntegrityConfig()
        assert config.enforcement_stage == "observation"
        assert "/health" in config.exempt_prefixes
        assert "/fabric/" in config.fabric_required_prefixes
        assert config.direct_storage_patterns == ()

    def test_all_exempt_prefixes_combines(self) -> None:
        config = FabricIntegrityConfig(
            extra_exempt_prefixes=("/custom/",),
        )
        all_exempt = config.all_exempt_prefixes
        assert "/health" in all_exempt
        assert "/custom/" in all_exempt

    def test_all_fabric_required_combines(self) -> None:
        config = FabricIntegrityConfig(
            extra_fabric_required_prefixes=("/api/v2/products/",),
        )
        all_required = config.all_fabric_required_prefixes
        assert "/fabric/" in all_required
        assert "/api/v2/products/" in all_required

    def test_all_direct_storage_combines(self) -> None:
        config = FabricIntegrityConfig(
            direct_storage_patterns=("/old/",),
            extra_direct_storage_patterns=("/legacy/",),
        )
        all_direct = config.all_direct_storage_patterns
        assert "/old/" in all_direct
        assert "/legacy/" in all_direct

    def test_frozen_config(self) -> None:
        """Config is immutable (frozen dataclass)."""
        config = FabricIntegrityConfig()
        with pytest.raises(AttributeError):
            config.enforcement_stage = "fail_closed"  # type: ignore[misc]

    def test_custom_exempt_methods(self) -> None:
        config = FabricIntegrityConfig(exempt_methods=("OPTIONS", "HEAD"))
        assert classify_route("/fabric/dashboard", "HEAD", config) == "exempt"
        assert classify_route("/fabric/dashboard", "GET", config) == "fabric_required"


# =========================================================================
# Edge Cases
# =========================================================================


class TestEdgeCases:
    """Edge case and regression tests."""

    @pytest.mark.asyncio
    async def test_app_raises_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        """ContextVars are cleaned up even when the app raises."""

        async def failing_app(scope: Any, receive: Any, send: Any) -> None:
            record_fabric_hit()
            raise ValueError("handler failed")

        middleware = FabricIntegrityMiddleware(failing_app)
        send = _SendCollector()

        with pytest.raises(ValueError, match="handler failed"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        # ContextVars must still be cleaned up
        assert get_fabric_hit_count() == 0
        assert get_current_integrity_trace() is None

    @pytest.mark.asyncio
    async def test_post_method_on_fabric_route(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """POST on a fabric_required route is also checked."""
        app = _make_asgi_app(status=200, body=b'{"data": "ok"}', fabric_hits=0)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(
                _make_scope(path="/fabric/users/write", method="POST"),
                _null_receive,
                send,
            )

        assert any("fabric.integrity.bypass" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_204_no_content_not_treated_as_null_body(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """204 No Content with empty body and fabric_hits should be ok, not null_body."""
        # 204 is 2xx but typically has no body by spec.
        # The middleware should still check, as empty body on a fabric
        # route that hit fabric suggests the product returned nothing.
        app = _make_asgi_app(status=204, body=b"", fabric_hits=1)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        # 204 is still 2xx, so null_body check fires
        assert any("fabric.integrity.null_body" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_301_redirect_skips_checks(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """3xx responses skip integrity checks (not 2xx)."""
        app = _make_asgi_app(status=301, body=b"", fabric_hits=0)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.WARNING, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        assert not any("fabric.integrity.bypass" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_elapsed_ms_in_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """Log records include elapsed_ms field."""
        app = _make_asgi_app(status=200, body=b'{"data": "ok"}', fabric_hits=1)
        middleware = FabricIntegrityMiddleware(app)
        send = _SendCollector()

        with caplog.at_level(logging.DEBUG, logger="dataflow.fabric.integrity"):
            await middleware(_make_scope(path="/fabric/dashboard"), _null_receive, send)

        ok_record = next(
            r for r in caplog.records if "fabric.integrity.ok" in r.message
        )
        assert hasattr(ok_record, "elapsed_ms")
        assert isinstance(ok_record.elapsed_ms, float)
        assert ok_record.elapsed_ms >= 0
