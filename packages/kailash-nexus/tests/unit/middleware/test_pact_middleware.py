# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for PACTMiddleware.

These tests exercise the ASGI middleware class in isolation with a fake
GovernanceEngine that returns scripted verdicts. They verify:

- Construction fail-closed on missing engine / missing verify_action
- Exempt paths bypass governance entirely
- Missing role_address denies with 403 when require_role_address=True
- Missing role_address passes through when require_role_address=False
- verify_action returning a BLOCKED verdict produces a 403 response
- verify_action returning a HELD verdict produces a 429 response
- verify_action returning auto_approved forwards to the inner app
- Exception from verify_action is caught and converted to 403
- Correlation id is generated and echoed in the response
- Non-http ASGI scopes (websocket, lifespan) pass through unfiltered
- NaN/Inf cost in scope state does not reach the engine
- Structural action derivation: method + first path segment
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from nexus.middleware.governance import (
    PACTGovernanceError,
    PACTMiddleware,
    _derive_action,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeVerdict:
    """Stand-in for kailash.trust.pact.GovernanceVerdict."""

    def __init__(
        self,
        level: str,
        reason: str = "",
        *,
        allowed: Optional[bool] = None,
    ) -> None:
        self.level = level
        self.reason = reason
        if allowed is None:
            self.allowed = level in ("auto_approved", "flagged")
        else:
            self.allowed = allowed


class FakeEngine:
    """Fake GovernanceEngine that returns scripted verdicts.

    Records every verify_action call for assertion.
    """

    def __init__(
        self,
        verdict: Optional[FakeVerdict] = None,
        exc: Optional[Exception] = None,
    ) -> None:
        self._verdict = verdict or FakeVerdict("auto_approved")
        self._exc = exc
        self.calls: List[Dict[str, Any]] = []

    def verify_action(
        self,
        role_address: str,
        action: str,
        context: Dict[str, Any],
    ) -> FakeVerdict:
        self.calls.append(
            {
                "role_address": role_address,
                "action": action,
                "context": dict(context),
            }
        )
        if self._exc is not None:
            raise self._exc
        return self._verdict


class InnerApp:
    """Innermost ASGI app — records invocation and sends a 200 response."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        self.called = True
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {"type": "http.response.body", "body": b'{"ok":true}', "more_body": False}
        )


class SendRecorder:
    """Collect ASGI messages emitted by the middleware (or the inner app)."""

    def __init__(self) -> None:
        self.messages: List[Dict[str, Any]] = []

    async def __call__(self, message: Dict[str, Any]) -> None:
        self.messages.append(message)

    @property
    def status(self) -> Optional[int]:
        for m in self.messages:
            if m.get("type") == "http.response.start":
                return int(m.get("status", 0))
        return None

    @property
    def body(self) -> bytes:
        out = b""
        for m in self.messages:
            if m.get("type") == "http.response.body":
                out += m.get("body", b"")
        return out

    @property
    def response_headers(self) -> Dict[bytes, bytes]:
        for m in self.messages:
            if m.get("type") == "http.response.start":
                return dict(m.get("headers", []))
        return {}


def _scope(
    *,
    path: str = "/api/workflows",
    method: str = "POST",
    headers: Optional[List[tuple[bytes, bytes]]] = None,
    state: Optional[Dict[str, Any]] = None,
    type_: str = "http",
) -> Dict[str, Any]:
    return {
        "type": type_,
        "method": method,
        "path": path,
        "headers": headers or [],
        "state": state or {},
    }


async def _drain_receive() -> Dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_missing_engine_raises(self) -> None:
        with pytest.raises(PACTGovernanceError):
            PACTMiddleware(app=InnerApp(), governance_engine=None)

    def test_non_engine_object_raises(self) -> None:
        class NotAnEngine:
            pass

        with pytest.raises(PACTGovernanceError):
            PACTMiddleware(app=InnerApp(), governance_engine=NotAnEngine())

    def test_valid_engine_constructs(self) -> None:
        mw = PACTMiddleware(app=InnerApp(), governance_engine=FakeEngine())
        assert mw is not None

    def test_default_exempt_paths_has_health(self) -> None:
        mw = PACTMiddleware(app=InnerApp(), governance_engine=FakeEngine())
        assert "/health" in mw._exempt_paths
        assert "/metrics" in mw._exempt_paths
        assert "/openapi.json" in mw._exempt_paths

    def test_custom_exempt_paths_replace_defaults(self) -> None:
        mw = PACTMiddleware(
            app=InnerApp(),
            governance_engine=FakeEngine(),
            exempt_paths={"/ping"},
        )
        assert "/ping" in mw._exempt_paths
        assert "/health" not in mw._exempt_paths


# ---------------------------------------------------------------------------
# Action derivation
# ---------------------------------------------------------------------------


class TestActionDerivation:
    def test_root_path(self) -> None:
        assert _derive_action("GET", "/") == "get"

    def test_single_segment(self) -> None:
        assert _derive_action("POST", "/api") == "post:api"

    def test_multi_segment_uses_first_only(self) -> None:
        assert _derive_action("DELETE", "/api/users/42") == "delete:api"

    def test_method_lowercased(self) -> None:
        assert _derive_action("PUT", "/workflows/deploy") == "put:workflows"


# ---------------------------------------------------------------------------
# Scope type gating
# ---------------------------------------------------------------------------


class TestScopeTypeGating:
    @pytest.mark.asyncio
    async def test_websocket_scope_passes_through(self) -> None:
        engine = FakeEngine()
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(type_="websocket", path="/ws/chat", method="GET"),
            _drain_receive,
            send,
        )

        assert inner.called is True
        assert engine.calls == []

    @pytest.mark.asyncio
    async def test_lifespan_scope_passes_through(self) -> None:
        engine = FakeEngine()
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(type_="lifespan", path="", method=""),
            _drain_receive,
            send,
        )

        assert inner.called is True
        assert engine.calls == []


# ---------------------------------------------------------------------------
# Exempt path bypass
# ---------------------------------------------------------------------------


class TestExemptPaths:
    @pytest.mark.asyncio
    async def test_health_path_bypasses_engine(self) -> None:
        engine = FakeEngine()
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(_scope(path="/health", method="GET"), _drain_receive, send)

        assert inner.called is True
        assert engine.calls == []
        assert send.status == 200

    @pytest.mark.asyncio
    async def test_openapi_json_bypasses_engine(self) -> None:
        engine = FakeEngine()
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(_scope(path="/openapi.json", method="GET"), _drain_receive, send)

        assert inner.called is True
        assert engine.calls == []


# ---------------------------------------------------------------------------
# Role-address extraction + fail-closed
# ---------------------------------------------------------------------------


class TestRoleAddressResolution:
    @pytest.mark.asyncio
    async def test_missing_role_address_denies_403(self) -> None:
        engine = FakeEngine()
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(_scope(path="/api/workflows"), _drain_receive, send)

        assert inner.called is False
        assert engine.calls == []
        assert send.status == 403
        assert b"missing_role_address" in send.body

    @pytest.mark.asyncio
    async def test_missing_role_address_non_strict_passes_through(self) -> None:
        engine = FakeEngine()
        inner = InnerApp()
        mw = PACTMiddleware(
            app=inner, governance_engine=engine, require_role_address=False
        )
        send = SendRecorder()

        await mw(_scope(path="/api/workflows"), _drain_receive, send)

        assert inner.called is True
        assert engine.calls == []

    @pytest.mark.asyncio
    async def test_role_address_from_scope_state(self) -> None:
        engine = FakeEngine()
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(
                path="/api/workflows",
                state={"pact_role_address": "D1-R1-T1-R1"},
            ),
            _drain_receive,
            send,
        )

        assert inner.called is True
        assert len(engine.calls) == 1
        assert engine.calls[0]["role_address"] == "D1-R1-T1-R1"
        assert engine.calls[0]["action"] == "post:api"

    @pytest.mark.asyncio
    async def test_role_address_from_header_fallback(self) -> None:
        engine = FakeEngine()
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(
                path="/api/workflows",
                headers=[(b"x-pact-role-address", b"D1-R1-T1-R1")],
            ),
            _drain_receive,
            send,
        )

        assert inner.called is True
        assert engine.calls[0]["role_address"] == "D1-R1-T1-R1"

    @pytest.mark.asyncio
    async def test_state_key_takes_precedence_over_header(self) -> None:
        engine = FakeEngine()
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(
                path="/api/workflows",
                headers=[(b"x-pact-role-address", b"D9-R9")],
                state={"pact_role_address": "D1-R1-T1-R1"},
            ),
            _drain_receive,
            send,
        )

        assert engine.calls[0]["role_address"] == "D1-R1-T1-R1"


# ---------------------------------------------------------------------------
# Verdict handling
# ---------------------------------------------------------------------------


class TestVerdictHandling:
    @pytest.mark.asyncio
    async def test_auto_approved_forwards_to_inner_app(self) -> None:
        engine = FakeEngine(FakeVerdict("auto_approved"))
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(path="/api/workflows", state={"pact_role_address": "D1-R1"}),
            _drain_receive,
            send,
        )

        assert inner.called is True
        assert send.status == 200

    @pytest.mark.asyncio
    async def test_flagged_still_allows_with_warn_log(self) -> None:
        engine = FakeEngine(FakeVerdict("flagged", reason="near_budget_limit"))
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(path="/api/workflows", state={"pact_role_address": "D1-R1"}),
            _drain_receive,
            send,
        )

        assert inner.called is True
        assert send.status == 200

    @pytest.mark.asyncio
    async def test_blocked_returns_403(self) -> None:
        engine = FakeEngine(FakeVerdict("blocked", reason="envelope_exceeded"))
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(path="/api/workflows", state={"pact_role_address": "D1-R1"}),
            _drain_receive,
            send,
        )

        assert inner.called is False
        assert send.status == 403
        assert b"envelope_exceeded" in send.body
        assert b"blocked" in send.body

    @pytest.mark.asyncio
    async def test_held_returns_429(self) -> None:
        engine = FakeEngine(FakeVerdict("held", reason="needs_human_approval"))
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(path="/api/workflows", state={"pact_role_address": "D1-R1"}),
            _drain_receive,
            send,
        )

        assert inner.called is False
        assert send.status == 429
        assert b"held" in send.body


# ---------------------------------------------------------------------------
# Fail-closed on engine exception
# ---------------------------------------------------------------------------


class TestFailClosedOnException:
    @pytest.mark.asyncio
    async def test_engine_raises_returns_403(self) -> None:
        engine = FakeEngine(exc=RuntimeError("engine exploded"))
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(path="/api/workflows", state={"pact_role_address": "D1-R1"}),
            _drain_receive,
            send,
        )

        assert inner.called is False
        assert send.status == 403
        assert b"internal_governance_error" in send.body


# ---------------------------------------------------------------------------
# Correlation id
# ---------------------------------------------------------------------------


class TestCorrelationId:
    @pytest.mark.asyncio
    async def test_correlation_id_echoed_in_deny_response(self) -> None:
        engine = FakeEngine(FakeVerdict("blocked", reason="denied"))
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(
                path="/api/workflows",
                headers=[(b"x-request-id", b"test-correlation-abc")],
                state={"pact_role_address": "D1-R1"},
            ),
            _drain_receive,
            send,
        )

        assert send.status == 403
        assert send.response_headers.get(b"x-request-id") == b"test-correlation-abc"
        assert send.response_headers.get(b"x-pact-verdict-level") == b"blocked"

    @pytest.mark.asyncio
    async def test_correlation_id_generated_when_missing(self) -> None:
        engine = FakeEngine(FakeVerdict("blocked", reason="denied"))
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(path="/api/workflows", state={"pact_role_address": "D1-R1"}),
            _drain_receive,
            send,
        )

        assert send.status == 403
        generated = send.response_headers.get(b"x-request-id")
        assert generated is not None
        # Hex uuid is 32 chars.
        assert len(generated) == 32


# ---------------------------------------------------------------------------
# NaN/Inf cost defense (rules/pact-governance.md Rule 6)
# ---------------------------------------------------------------------------


class TestCostContextSanitization:
    @pytest.mark.asyncio
    async def test_finite_cost_propagates_to_engine(self) -> None:
        engine = FakeEngine(FakeVerdict("auto_approved"))
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(
                path="/api/workflows",
                state={"pact_role_address": "D1-R1", "pact_cost_usd": 12.5},
            ),
            _drain_receive,
            send,
        )

        assert engine.calls[0]["context"] == {"cost": 12.5}

    @pytest.mark.asyncio
    async def test_nan_cost_is_dropped_not_passed_to_engine(self) -> None:
        engine = FakeEngine(FakeVerdict("auto_approved"))
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(
                path="/api/workflows",
                state={
                    "pact_role_address": "D1-R1",
                    "pact_cost_usd": float("nan"),
                },
            ),
            _drain_receive,
            send,
        )

        assert "cost" not in engine.calls[0]["context"]

    @pytest.mark.asyncio
    async def test_inf_cost_is_dropped(self) -> None:
        engine = FakeEngine(FakeVerdict("auto_approved"))
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(
                path="/api/workflows",
                state={
                    "pact_role_address": "D1-R1",
                    "pact_cost_usd": float("inf"),
                },
            ),
            _drain_receive,
            send,
        )

        assert "cost" not in engine.calls[0]["context"]

    @pytest.mark.asyncio
    async def test_negative_cost_is_dropped(self) -> None:
        engine = FakeEngine(FakeVerdict("auto_approved"))
        inner = InnerApp()
        mw = PACTMiddleware(app=inner, governance_engine=engine)
        send = SendRecorder()

        await mw(
            _scope(
                path="/api/workflows",
                state={
                    "pact_role_address": "D1-R1",
                    "pact_cost_usd": -1.0,
                },
            ),
            _drain_receive,
            send,
        )

        assert "cost" not in engine.calls[0]["context"]
