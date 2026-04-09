# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration test for PACTMiddleware wiring.

Exercises the full stack:
- Real kailash.trust.pact.GovernanceEngine built from a real OrgDefinition
- Real Nexus() instance with a real FastAPI gateway
- PACTMiddleware registered via nexus.add_middleware
- Real in-process HTTP requests via httpx.ASGITransport

Verifies:
1. A request with a valid role_address + envelope-approved action passes (200)
2. A request with a role_address whose envelope blocks the action is denied (403)
3. A request without a role_address is denied (403, "missing_role_address")
4. A request to an exempt path bypasses governance (200)
5. Correlation id is preserved end-to-end
6. The NexusEngine.builder().governance(engine).build() convenience path wires
   PACTMiddleware into the stack equivalently to direct add_middleware.
7. Audit trail / structured log output: the middleware logger emits
   pact_middleware.request.denied with action + level + reason

No mocking of the governance engine. No mocking of the Nexus gateway.
Per rules/testing.md Tier 2: real infrastructure.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

import httpx
import pytest
import pytest_asyncio
from fastapi import APIRouter

from kailash.trust.pact.compilation import RoleDefinition, compile_org
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    OperationalConstraintConfig,
    OrgDefinition,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from nexus import Nexus, NexusEngine
from nexus.middleware.governance import PACTMiddleware

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


CEO_ADDR = "R1"
ENG_ADDR = "R1-R1"


@pytest.fixture
def real_engine() -> GovernanceEngine:
    """Build a minimal 2-role org and attach an envelope to the engineering role.

    The engineering role (R1-R1) may do ``get:api`` and ``post:api`` but
    ``delete:api`` is blocked. This gives us a deterministic allow/deny
    matrix without a fake engine.
    """
    roles = [
        RoleDefinition(role_id="r-ceo", name="CEO", reports_to_role_id=None),
        RoleDefinition(
            role_id="r-eng-lead",
            name="Engineering Lead",
            reports_to_role_id="r-ceo",
        ),
    ]
    org = OrgDefinition(
        org_id="acme-test",
        name="Acme Test Org",
        roles=roles,
    )
    compiled = compile_org(org)
    engine = GovernanceEngine(compiled)

    env_cfg = ConstraintEnvelopeConfig(
        id="env-eng",
        description="engineering envelope",
        operational=OperationalConstraintConfig(
            allowed_actions=["get:api", "post:api"],
            blocked_actions=["delete:api"],
        ),
    )
    role_env = RoleEnvelope(
        id="re-eng",
        defining_role_address=CEO_ADDR,
        target_role_address=ENG_ADDR,
        envelope=env_cfg,
    )
    engine.set_role_envelope(role_env)
    return engine


def _free_port() -> int:
    """Pick a free port by asking the OS."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _attach_role_address_header_middleware(app: Any) -> None:
    """Install a tiny middleware that copies X-PACT-Role-Address header to scope state.

    In production this job is done by Nexus's authentication middleware:
    after JWT/session/RBAC validation, it sets scope['state']['pact_role_address']
    on behalf of the authenticated principal. For this integration test we
    simulate that step with a deterministic, structural header copy — NO
    content-based routing.
    """

    @app.middleware("http")
    async def _copy_role_address_header(request, call_next):
        hdr = request.headers.get("x-pact-role-address")
        if hdr:
            request.state.pact_role_address = hdr
        return await call_next(request)


def _attach_probe_endpoint(app: Any) -> None:
    """Register /api/workflows endpoints that return 200 with a known body.

    These let the test verify that a request that PASSES governance actually
    reaches the inner handler (not just that the middleware didn't deny).
    """
    router = APIRouter()

    @router.get("/api/workflows")
    async def list_workflows() -> dict:
        return {"ok": True, "op": "list"}

    @router.post("/api/workflows")
    async def create_workflow() -> dict:
        return {"ok": True, "op": "create"}

    @router.delete("/api/workflows/42")
    async def delete_workflow() -> dict:
        return {"ok": True, "op": "delete"}

    app.include_router(router)


@pytest.fixture
def nexus_with_pact(real_engine: GovernanceEngine) -> Iterator[Nexus]:
    """Build a Nexus, register PACTMiddleware + probe endpoints, yield."""
    nexus = Nexus(api_port=_free_port(), enable_auth=False)
    app = nexus._http_transport.app
    assert app is not None, "Nexus gateway must be initialized eagerly"

    # Install PACTMiddleware via the public add_middleware API.
    nexus.add_middleware(
        PACTMiddleware,
        governance_engine=real_engine,
        require_role_address=True,
    )

    # Install the simulated authN header-copy middleware.
    _attach_role_address_header_middleware(app)

    # Install probe endpoints.
    _attach_probe_endpoint(app)

    yield nexus

    # Cleanup
    if hasattr(nexus, "close"):
        nexus.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _client(nexus: Nexus) -> httpx.AsyncClient:
    """Build an in-process httpx client against Nexus's FastAPI app."""
    app = nexus._http_transport.app
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_valid_clearance_allowed_action_returns_200(
    nexus_with_pact: Nexus,
) -> None:
    """An engineering role performing an allowed action should reach the handler."""
    async with await _client(nexus_with_pact) as client:
        resp = await client.get(
            "/api/workflows",
            headers={"x-pact-role-address": ENG_ADDR},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["op"] == "list"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_valid_clearance_allowed_post_action_returns_200(
    nexus_with_pact: Nexus,
) -> None:
    """POST is in allowed_actions for the engineering envelope -> 200."""
    async with await _client(nexus_with_pact) as client:
        resp = await client.post(
            "/api/workflows",
            headers={"x-pact-role-address": ENG_ADDR},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["op"] == "create"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_blocked_action_returns_403(nexus_with_pact: Nexus) -> None:
    """DELETE is explicitly blocked for the engineering envelope -> 403."""
    async with await _client(nexus_with_pact) as client:
        resp = await client.delete(
            "/api/workflows/42",
            headers={"x-pact-role-address": ENG_ADDR},
        )

    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["error"] == "governance_denied"
    assert body["level"] == "blocked"
    assert "request_id" in body
    # The response must carry the correlation header for tracing.
    assert resp.headers.get("x-request-id") == body["request_id"]
    assert resp.headers.get("x-pact-verdict-level") == "blocked"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_role_address_returns_403_missing_role(
    nexus_with_pact: Nexus,
) -> None:
    """A request with no role_address and strict mode -> fail-closed 403."""
    async with await _client(nexus_with_pact) as client:
        resp = await client.get("/api/workflows")

    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["error"] == "governance_denied"
    assert body["reason"] == "missing_role_address"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exempt_health_path_bypasses_governance(
    real_engine: GovernanceEngine,
) -> None:
    """/health is in the default exempt set and must bypass PACTMiddleware.

    Nexus installs its own /health endpoint at gateway construction time
    (returning ``{"status": "healthy"}``). The fact that we can reach it
    with NO ``X-PACT-Role-Address`` header — which would otherwise be a
    fail-closed 403 in strict mode — is the proof that PACTMiddleware's
    exempt-path check short-circuited correctly.
    """
    nexus = Nexus(api_port=_free_port(), enable_auth=False)
    try:
        app = nexus._http_transport.app
        assert app is not None

        nexus.add_middleware(
            PACTMiddleware,
            governance_engine=real_engine,
            require_role_address=True,
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            # No role_address header — strict mode would normally deny.
            resp = await client.get("/health")

        # The key assertion is that we got 200, not a 403 "missing_role_address".
        # Nexus's built-in health body shape is implementation-detail of the gateway.
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "status" in body
        # Nexus returns {"status": "healthy"} — any non-denial response proves
        # the exempt-path bypass worked.
        assert body["status"] in ("ok", "healthy")
    finally:
        if hasattr(nexus, "close"):
            nexus.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_correlation_id_propagates_end_to_end(
    nexus_with_pact: Nexus,
) -> None:
    """A client-supplied X-Request-Id is echoed on the deny response."""
    async with await _client(nexus_with_pact) as client:
        resp = await client.delete(
            "/api/workflows/42",
            headers={
                "x-pact-role-address": ENG_ADDR,
                "x-request-id": "test-correlation-xyz-123",
            },
        )

    assert resp.status_code == 403
    assert resp.headers.get("x-request-id") == "test-correlation-xyz-123"
    assert resp.json()["request_id"] == "test-correlation-xyz-123"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nexus_engine_builder_governance_wires_middleware(
    real_engine: GovernanceEngine,
) -> None:
    """NexusEngine.builder().governance(engine).build() wires PACTMiddleware.

    This verifies the integration point: the NexusEngine builder's
    ``.governance()`` method places PACTMiddleware in the underlying Nexus
    middleware stack identically to a manual ``add_middleware`` call.
    """
    engine = (
        NexusEngine.builder()
        .bind("127.0.0.1:0")
        .governance(real_engine, require_role_address=True)
        .build()
    )
    try:
        # Governance engine is retained on the NexusEngine wrapper.
        assert engine.governance_engine is real_engine

        # PACTMiddleware is registered in the underlying Nexus middleware stack.
        middleware_classes = [info.middleware_class for info in engine.nexus.middleware]
        assert PACTMiddleware in middleware_classes, middleware_classes

        # Drive a real request through the wired-up FastAPI app.
        app = engine.nexus._http_transport.app
        assert app is not None

        _attach_role_address_header_middleware(app)
        _attach_probe_endpoint(app)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            # Allowed action -> 200
            ok = await client.get(
                "/api/workflows",
                headers={"x-pact-role-address": ENG_ADDR},
            )
            assert ok.status_code == 200, ok.text

            # Blocked action -> 403
            blocked = await client.delete(
                "/api/workflows/42",
                headers={"x-pact-role-address": ENG_ADDR},
            )
            assert blocked.status_code == 403, blocked.text
            assert blocked.json()["level"] == "blocked"
    finally:
        engine.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_structured_log_emitted_on_deny(
    nexus_with_pact: Nexus,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A denied request emits a WARN-level pact_middleware.request.denied log.

    Verifies rules/observability.md compliance: correlation id, action,
    role_address, level, reason are all present as structured fields.
    """
    caplog.set_level(logging.INFO, logger="nexus.middleware.governance")

    async with await _client(nexus_with_pact) as client:
        resp = await client.delete(
            "/api/workflows/42",
            headers={
                "x-pact-role-address": ENG_ADDR,
                "x-request-id": "test-log-correlation-789",
            },
        )

    assert resp.status_code == 403

    # Look for the structured deny log line.
    deny_records = [
        r
        for r in caplog.records
        if r.name == "nexus.middleware.governance"
        and r.getMessage() == "pact_middleware.request.denied"
    ]
    assert len(deny_records) >= 1, "No deny log emitted"
    rec = deny_records[0]
    assert rec.levelname == "WARNING"
    # Structured fields come through as record attributes via the extra=
    # mechanism used in the middleware.
    assert getattr(rec, "request_id", None) == "test-log-correlation-789"
    assert getattr(rec, "role_address", None) == ENG_ADDR
    assert getattr(rec, "action", None) == "delete:api"
    assert getattr(rec, "level", None) == "blocked"
    assert hasattr(rec, "reason")
    assert hasattr(rec, "latency_ms")
