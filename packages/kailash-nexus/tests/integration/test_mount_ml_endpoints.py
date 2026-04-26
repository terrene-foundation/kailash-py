# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""W6-009 — Canonical-entry Tier-2 test for ``nexus.ml.mount_ml_endpoints``.

This file pins the canonical public-API shape declared in
`specs/nexus-ml-integration.md` §5.2 + §10 + §12 after the W5-C
finding F-C-26 spec/code reconciliation. The companion file
`test_nexus_ml_endpoints_wiring.py` exercises the mounted REST + MCP
routes end-to-end; this file's job is the *structural-invariant*
regression that locks the public surface so a future refactor cannot
silently re-introduce the legacy ``register_service`` /
``InferenceServer.as_nexus_service`` names without flipping a loud
test.

Per `rules/orphan-detection.md` §3 (Removed = Deleted, Not Deprecated),
the prior draft spec mentioned two surfaces that were never shipped:
``Nexus.register_service(...)`` and ``InferenceServer.as_nexus_service()``.
The shipped path is exclusively ``nexus.ml.mount_ml_endpoints`` per
`packages/kailash-nexus/src/nexus/ml/__init__.py:222`. This test
locks that fact:

  1. ``mount_ml_endpoints`` is importable from ``nexus.ml``.
  2. Its signature is exactly ``(nexus, serve_handle, *, prefix="/ml")``.
  3. The absent legacy names are NOT attributes of ``Nexus`` /
     ``InferenceServer`` (when ml is installed) — guarded so the test
     does not require kailash-ml to be installed in every CI shard.
  4. Mounted endpoints reach the predictor end-to-end against a real
     Nexus + JWT + Protocol-satisfying ``ServeHandle`` (per
     `rules/testing.md` § Tier 2 "Protocol-Satisfying Deterministic
     Adapters").

The Tier-2 test uses a real Nexus instance + real FastAPI TestClient +
real JWT middleware — no ``unittest.mock`` (per `rules/testing.md`
§ "Tier 2 (Integration): NO mocking").
"""

from __future__ import annotations

import inspect
import socket
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from nexus import Nexus
from nexus.auth.jwt import JWTConfig, JWTMiddleware
from nexus.ml import mount_ml_endpoints

JWT_TEST_SECRET = "test-secret-key-minimum-32-bytes!"


def _free_port(start: int = 18600) -> int:
    for port in range(start, start + 200):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.bind(("", port))
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                return port
            except OSError:
                continue
    raise RuntimeError("no free port")


def _make_token(sub: str, tenant_id: Optional[str] = None) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=1)).timestamp()),
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    return pyjwt.encode(payload, JWT_TEST_SECRET, algorithm="HS256")


class DeterministicServeHandle:
    """Protocol-satisfying ``ServeHandle`` adapter for Tier-2 testing.

    Per `rules/testing.md` Tier 2 exception: a class that satisfies a
    structural Protocol at runtime AND produces deterministic output is
    NOT a mock. This adapter records every ``predict`` call so the test
    can assert the propagated tenant/actor reached the predictor.
    """

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def predict(
        self,
        inputs: Any,
        *,
        tenant_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.calls.append(
            {"inputs": inputs, "tenant_id": tenant_id, "actor_id": actor_id}
        )
        score = float(inputs.get("x", 0)) if isinstance(inputs, dict) else 0.0
        return {"score": score, "seen_tenant": tenant_id, "seen_actor": actor_id}

    def describe(self) -> Dict[str, Any]:
        return {"model": "w6-009-canonical-entry", "version": "1.0.0"}


@pytest.fixture
def nexus_with_ml():
    """Real Nexus + JWT middleware + mounted ml endpoints.

    Yields ``(client, handle)``. No mocks: real Nexus, real FastAPI
    TestClient, real JWT validation, real Protocol-satisfying handle.
    """
    port = _free_port()
    app = Nexus(api_port=port, auto_discovery=False)
    # Narrow `Optional[FastAPI]` → `FastAPI` for the type checker AND
    # assert the gateway built successfully. Per `rules/zero-tolerance.md`
    # § 3a (Typed Delegate Guards For None Backing Objects).
    fastapi_app = app.fastapi_app
    assert fastapi_app is not None, (
        "Nexus.fastapi_app is None — the HTTP transport gateway did not build. "
        "Construct Nexus with default api_port + auto_discovery=False before mounting."
    )
    fastapi_app.add_middleware(
        JWTMiddleware,
        config=JWTConfig(
            secret=JWT_TEST_SECRET,
            algorithm="HS256",
            exempt_paths=["/ml/healthz", "/health"],
        ),
    )
    handle = DeterministicServeHandle()
    mount_ml_endpoints(app, handle, prefix="/ml")
    client = TestClient(fastapi_app)
    try:
        yield client, handle
    finally:
        try:
            app.stop()
        except Exception:  # noqa: BLE001 — fixture teardown best-effort
            pass


# --------------------------------------------------------------------------
# Structural invariant tests — lock the public-API shape that F-C-26 fixed.
# --------------------------------------------------------------------------


class TestMountMlEndpointsSignature:
    """Spec §5.2 — ``mount_ml_endpoints`` is the canonical mount entry."""

    def test_mount_ml_endpoints_is_importable_from_nexus_ml(self) -> None:
        """The canonical entry MUST be reachable as ``nexus.ml.mount_ml_endpoints``."""
        from nexus.ml import mount_ml_endpoints as imported

        assert callable(imported), "mount_ml_endpoints must be a callable"

    def test_mount_ml_endpoints_signature_is_locked(self) -> None:
        """Locks ``mount_ml_endpoints(nexus, serve_handle, *, prefix='/ml') -> None``.

        If the signature drifts, the test fails loudly and the
        cross-spec contract (`specs/nexus-ml-integration.md` §5.2) MUST
        be re-derived per `rules/specs-authority.md` §5b.
        """
        sig = inspect.signature(mount_ml_endpoints)
        params = list(sig.parameters.values())
        # Positional: nexus, serve_handle
        assert params[0].name == "nexus"
        assert params[1].name == "serve_handle"
        # Keyword-only: prefix with default "/ml"
        assert params[2].name == "prefix"
        assert params[2].kind is inspect.Parameter.KEYWORD_ONLY
        assert params[2].default == "/ml"

    def test_nexus_class_does_not_expose_register_service(self) -> None:
        """Spec §10 retraction — ``Nexus.register_service`` does NOT exist.

        Per `rules/orphan-detection.md` §3 (Removed = Deleted, Not
        Deprecated): the legacy ``register_service`` overload was never
        shipped; if a future refactor reintroduces it, the test forces
        a re-audit of the cross-SDK contract per
        `rules/cross-sdk-inspection.md` §3a.
        """
        assert not hasattr(Nexus, "register_service"), (
            "Nexus.register_service was retracted per F-C-26 / spec §10. "
            "If this attribute is reintroduced, re-derive "
            "specs/nexus-ml-integration.md §5.1 + §10 + §12 per "
            "rules/specs-authority.md §5b."
        )

    def test_inference_server_does_not_expose_as_nexus_service(self) -> None:
        """Spec §5.1 retraction — ``InferenceServer.as_nexus_service`` does NOT exist.

        The test imports kailash-ml lazily so the file passes when the
        ``[ml]`` extra is absent. When ml IS installed the assertion
        runs and locks the absent surface.
        """
        try:
            from kailash_ml.serving.server import InferenceServer
        except ImportError:
            pytest.skip("kailash-ml not installed; absent-surface check skipped")
        assert not hasattr(InferenceServer, "as_nexus_service"), (
            "InferenceServer.as_nexus_service was retracted per F-C-26 / "
            "spec §5.1. If reintroduced, re-derive "
            "specs/nexus-ml-integration.md §5 + §12 per "
            "rules/specs-authority.md §5b."
        )


# --------------------------------------------------------------------------
# Tier-2 end-to-end mount path test (real Nexus + real ServeHandle).
# --------------------------------------------------------------------------


class TestMountMlEndpointsEndToEnd:
    """Spec §5.1 — every request hitting ``POST /ml/predict`` reaches the
    predictor with ambient tenant/actor propagated from the JWT claims."""

    def test_canonical_mount_propagates_jwt_claims_to_predict(
        self, nexus_with_ml
    ) -> None:
        client, handle = nexus_with_ml
        token = _make_token(sub="user-w6-009", tenant_id="tenant-canonical")
        resp = client.post(
            "/ml/predict",
            json={"x": 7},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Predictor saw the JWT-derived tenant + actor.
        assert body["seen_tenant"] == "tenant-canonical"
        assert body["seen_actor"] == "user-w6-009"
        # Read-back verification per rules/testing.md § State Persistence:
        assert len(handle.calls) == 1
        assert handle.calls[0]["tenant_id"] == "tenant-canonical"
        assert handle.calls[0]["actor_id"] == "user-w6-009"
        assert handle.calls[0]["inputs"] == {"x": 7}

    def test_canonical_mount_describe_returns_handle_metadata(
        self, nexus_with_ml
    ) -> None:
        client, _ = nexus_with_ml
        token = _make_token(sub="meta-reader")
        resp = client.get(
            "/ml/describe",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["model"] == "w6-009-canonical-entry"
        assert body["version"] == "1.0.0"

    def test_canonical_mount_healthz_is_unauthenticated(self, nexus_with_ml) -> None:
        """Spec §5.2 — healthz is exempt from auth (liveness probe)."""
        client, _ = nexus_with_ml
        resp = client.get("/ml/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
