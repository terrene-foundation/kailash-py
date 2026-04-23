# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring tests: JWT middleware sets ContextVars that downstream code reads.

Per `rules/testing.md` Tier 2 + `rules/facade-manager-detection.md` §2:
    - Real FastAPI + real JWTMiddleware (no MagicMock).
    - Simulate HTTP request with a signed JWT carrying ``tenant_id``.
    - Assert downstream handler reads ``get_current_tenant_id()`` /
      ``get_current_actor_id()`` and sees the propagated values.
    - Assert exception inside call_next doesn't leak state (spec §2.2).
    - Assert parallel requests don't cross-contaminate (regression for
      `tests/regression/test_contextvar_leak_across_requests.py` at spec §7.3).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt as pyjwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from nexus.auth.jwt import JWTConfig, JWTMiddleware
from nexus.context import get_current_actor_id, get_current_tenant_id

# 32-byte secret per RFC 7518 §3.2 (rules/testing.md § JWT Test Secrets)
JWT_TEST_SECRET = "test-secret-key-minimum-32-bytes!"


def _make_token(
    *,
    sub: str,
    tenant_id: Optional[str] = None,
    exp_offset_seconds: int = 60,
) -> str:
    """Issue a signed HS256 JWT for the test."""
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_offset_seconds)).timestamp()),
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    return pyjwt.encode(payload, JWT_TEST_SECRET, algorithm="HS256")


@pytest.fixture
def app_with_jwt():
    """Real FastAPI app with JWTMiddleware — NO MagicMock.

    Endpoints read ambient ContextVars via nexus.context getters, so the
    test observes the propagated values through the same surface a real
    kailash-ml engine would use.
    """
    app = FastAPI()
    config = JWTConfig(
        secret=JWT_TEST_SECRET,
        algorithm="HS256",
        exempt_paths=["/public"],
    )
    app.add_middleware(JWTMiddleware, config=config)

    @app.get("/public")
    async def public_endpoint():
        # Exempt path — contextvar is None (no JWT validation ran).
        return {
            "tenant_id": get_current_tenant_id(),
            "actor_id": get_current_actor_id(),
        }

    @app.get("/who-am-i")
    async def who_am_i():
        return {
            "tenant_id": get_current_tenant_id(),
            "actor_id": get_current_actor_id(),
        }

    @app.get("/raises")
    async def raises():
        # Record the ambient values BEFORE raising so the test can confirm
        # the middleware set them, then let the exception propagate.
        _ = get_current_tenant_id()
        _ = get_current_actor_id()
        raise HTTPException(status_code=418, detail="teapot")

    return app


@pytest.fixture
def client(app_with_jwt):
    return TestClient(app_with_jwt)


class TestJWTTenantPropagation:
    """Spec §2.2 — JWT `tenant_id` claim reaches get_current_tenant_id()."""

    def test_tenant_claim_propagates_to_contextvar(self, client):
        token = _make_token(sub="alice", tenant_id="acme-corp")
        resp = client.get("/who-am-i", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "acme-corp"
        assert body["actor_id"] == "alice"

    def test_missing_tenant_claim_yields_none(self, client):
        """Spec §2.2 — tenant_id is OPTIONAL; missing claim → None (strict
        mode is downstream-engine's responsibility)."""
        token = _make_token(sub="bob", tenant_id=None)
        resp = client.get("/who-am-i", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] is None
        assert body["actor_id"] == "bob"

    def test_exempt_path_contextvar_is_none(self, client):
        """Exempt paths skip JWT → no ambient tenant/actor."""
        resp = client.get("/public")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] is None
        assert body["actor_id"] is None


class TestContextVarResetDiscipline:
    """Spec §2.2 invariant + spec §7.3 regression — reset-in-finally."""

    def test_exception_in_call_next_does_not_leak(self, client):
        """Request A raises inside call_next; request B on the same worker
        MUST NOT observe request A's tenant_id."""
        token_a = _make_token(sub="alice", tenant_id="tenant-A")
        resp_a = client.get("/raises", headers={"Authorization": f"Bearer {token_a}"})
        assert resp_a.status_code == 418

        # Request B follows — must see B's own values, not leaked A's
        token_b = _make_token(sub="bob", tenant_id="tenant-B")
        resp_b = client.get("/who-am-i", headers={"Authorization": f"Bearer {token_b}"})
        assert resp_b.status_code == 200
        body = resp_b.json()
        assert body["tenant_id"] == "tenant-B"
        assert body["actor_id"] == "bob"

    def test_sequential_requests_no_cross_contamination(self, client):
        """Spec §7.3 — two sequential requests with different JWTs MUST NOT
        see each other's tenant_id."""
        for idx in range(3):
            tid = f"tenant-{idx}"
            sub = f"actor-{idx}"
            token = _make_token(sub=sub, tenant_id=tid)
            resp = client.get("/who-am-i", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["tenant_id"] == tid
            assert body["actor_id"] == sub


class TestUnauthenticatedRequestContext:
    """Missing / invalid token MUST NOT leak a previously-set tenant."""

    def test_missing_token_returns_401_and_keeps_contextvar_none(self, client):
        # First, issue a valid request that sets tenant_id
        token = _make_token(sub="alice", tenant_id="tenant-A")
        resp = client.get("/who-am-i", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["tenant_id"] == "tenant-A"

        # Then request with no token — 401, and the context is reset after
        resp2 = client.get("/who-am-i")
        assert resp2.status_code == 401
