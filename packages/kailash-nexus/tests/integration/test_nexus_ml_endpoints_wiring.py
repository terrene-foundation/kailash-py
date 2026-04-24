# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring tests: ``nexus.ml.mount_ml_endpoints`` exposes REST + MCP.

Per `rules/testing.md` Tier 2 + `rules/facade-manager-detection.md` §2:
    - Real Nexus instance + real FastAPI TestClient (no MagicMock).
    - A **Protocol-satisfying deterministic adapter** stands in for the
      kailash-ml ``ServeHandle`` — it's a real object implementing the
      ``predict``/``describe`` interface, not a mock. (`rules/testing.md`
      Tier 2 "Exception: Protocol-Satisfying Deterministic Adapters".)
    - Hit each mounted route, assert status + body.
"""

from __future__ import annotations

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


def _free_port(start: int = 18400) -> int:
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
    """Real implementation of the kailash-ml ``ServeHandle`` contract.

    Per `rules/testing.md` Tier 2 exception: "A class that satisfies a
    typing.Protocol at runtime AND produces deterministic output from its
    inputs is NOT a mock." This handle records every call so tests can
    assert the propagated tenant_id / actor_id reached the predictor.
    """

    model_name: str = "deterministic-test-model"
    model_version: str = "1.0.0"

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
        score = float(inputs.get("x", 0)) * 2.0 if isinstance(inputs, dict) else 0.0
        return {
            "score": score,
            "model": self.model_name,
            "version": self.model_version,
            "seen_tenant": tenant_id,
            "seen_actor": actor_id,
        }

    def describe(self) -> Dict[str, Any]:
        return {
            "model": self.model_name,
            "version": self.model_version,
            "inputs": ["x"],
            "outputs": ["score"],
        }


@pytest.fixture
def nexus_with_ml():
    """Real Nexus + JWT + mounted ml endpoints. Yields (client, handle)."""
    port = _free_port()
    app = Nexus(api_port=port, auto_discovery=False)
    app.fastapi_app.add_middleware(
        JWTMiddleware,
        config=JWTConfig(
            secret=JWT_TEST_SECRET,
            algorithm="HS256",
            exempt_paths=["/ml/healthz", "/health"],
        ),
    )
    handle = DeterministicServeHandle()
    mount_ml_endpoints(app, handle, prefix="/ml")

    client = TestClient(app.fastapi_app)
    try:
        yield client, handle
    finally:
        try:
            app.stop()
        except Exception:
            pass


class TestMountedRestEndpoints:
    """Spec §5: REST predict + describe + healthz routes registered."""

    def test_predict_endpoint_propagates_tenant(self, nexus_with_ml):
        client, handle = nexus_with_ml
        token = _make_token(sub="alice", tenant_id="acme-corp")
        resp = client.post(
            "/ml/predict",
            json={"x": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["score"] == 10.0
        assert body["seen_tenant"] == "acme-corp"
        assert body["seen_actor"] == "alice"
        assert len(handle.calls) == 1
        assert handle.calls[0]["tenant_id"] == "acme-corp"
        assert handle.calls[0]["actor_id"] == "alice"

    def test_predict_requires_auth(self, nexus_with_ml):
        client, _ = nexus_with_ml
        resp = client.post("/ml/predict", json={"x": 1})
        assert resp.status_code == 401

    def test_describe_endpoint_returns_metadata(self, nexus_with_ml):
        client, _ = nexus_with_ml
        token = _make_token(sub="alice", tenant_id="acme")
        resp = client.get(
            "/ml/describe",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["model"] == "deterministic-test-model"
        assert body["version"] == "1.0.0"
        assert "inputs" in body

    def test_healthz_endpoint_is_unauthenticated(self, nexus_with_ml):
        """Spec §5.1 — healthz is an exempt path (liveness probe)."""
        client, _ = nexus_with_ml
        resp = client.get("/ml/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestMountedMcpEndpoint:
    """Spec §5: MCP-compatible predict endpoint."""

    def test_mcp_predict_unwraps_tool_envelope(self, nexus_with_ml):
        client, handle = nexus_with_ml
        token = _make_token(sub="mcp-agent", tenant_id="tenant-mcp")
        resp = client.post(
            "/ml/mcp/predict",
            json={"tool": "predict", "arguments": {"x": 3}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tool"] == "predict"
        assert body["result"]["score"] == 6.0
        assert body["result"]["seen_tenant"] == "tenant-mcp"
        assert body["result"]["seen_actor"] == "mcp-agent"


class TestPerRequestIsolation:
    """Spec §7.3 — two sequential requests with different JWTs land on the
    predictor with the correct per-request tenant/actor."""

    def test_two_requests_different_tenants(self, nexus_with_ml):
        client, handle = nexus_with_ml
        token_a = _make_token(sub="alice", tenant_id="tenant-A")
        token_b = _make_token(sub="bob", tenant_id="tenant-B")

        resp_a = client.post(
            "/ml/predict",
            json={"x": 1},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        resp_b = client.post(
            "/ml/predict",
            json={"x": 2},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_a.json()["seen_tenant"] == "tenant-A"
        assert resp_a.json()["seen_actor"] == "alice"
        assert resp_b.json()["seen_tenant"] == "tenant-B"
        assert resp_b.json()["seen_actor"] == "bob"
        assert len(handle.calls) == 2
