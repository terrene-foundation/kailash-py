# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 test: serve() tenant scope enforced on bound endpoint.

Per specs/ml-engines.md §5.1 MUST 3, a REST/MCP endpoint bound by an
MLEngine with tenant_id='acme' MUST reject an invocation whose tenant
does not match. This closes the multi-tenancy loop: engine construction
propagates tenant_id through serve() into the endpoint's auth context.
"""
from __future__ import annotations

import pickle

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import MLEngine
from kailash_ml.engine import TenantRequiredError
from kailash_ml.engines.model_registry import LocalFileArtifactStore, ModelRegistry
from kailash_ml.types import FeatureField, FeatureSchema, ModelSignature


@pytest.fixture
async def registry(tmp_path):
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    reg = ModelRegistry(cm, artifact_store=store)
    yield reg
    await cm.close()


@pytest.fixture
def trained_model_bytes():
    rng = np.random.default_rng(seed=21)
    X = rng.random((20, 2), dtype=np.float64)
    y = (X[:, 0] > 0.5).astype(int)
    model = RandomForestClassifier(n_estimators=2, random_state=0)
    model.fit(X, y)
    return pickle.dumps(model)


@pytest.fixture
def signature():
    return ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [FeatureField("a", "float64"), FeatureField("b", "float64")],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )


@pytest.mark.integration
async def test_rest_endpoint_rejects_mismatched_tenant(
    registry, trained_model_bytes, signature
):
    """Engine.tenant_id='acme' serves REST; invocation with tenant='bob' refused."""
    await registry.register_model(
        "tenant_rest", trained_model_bytes, signature=signature
    )
    engine = MLEngine(registry=registry, tenant_id="acme")
    result = await engine.serve("models://tenant_rest/v1", channels=["rest"])
    binding = engine._active_serves[("tenant_rest", 1, "rest")]

    # Direct binding.invoke with a mismatched tenant MUST raise.
    with pytest.raises(TenantRequiredError):
        await binding.invoke({"a": 0.5, "b": 0.5}, tenant_id="bob")

    # Same binding with matching tenant succeeds.
    out = await binding.invoke({"a": 0.5, "b": 0.5}, tenant_id="acme")
    assert "predictions" in out
    assert result.tenant_id == "acme"


@pytest.mark.integration
async def test_mcp_endpoint_rejects_mismatched_tenant(
    registry, trained_model_bytes, signature
):
    """Same contract as REST — MCP tool refuses cross-tenant invocations."""
    await registry.register_model(
        "tenant_mcp", trained_model_bytes, signature=signature
    )
    engine = MLEngine(registry=registry, tenant_id="acme")
    await engine.serve("models://tenant_mcp/v1", channels=["mcp"])
    binding = engine._active_serves[("tenant_mcp", 1, "mcp")]

    with pytest.raises(TenantRequiredError):
        await binding.invoke({"a": 0.5, "b": 0.5}, tenant_id="bob")
    out = await binding.invoke({"a": 0.5, "b": 0.5}, tenant_id="acme")
    assert "predictions" in out


@pytest.mark.integration
async def test_single_tenant_engine_accepts_any_tenant(
    registry, trained_model_bytes, signature
):
    """Engine.tenant_id=None (single-tenant) doesn't gate on the invocation tenant."""
    await registry.register_model(
        "single_tenant", trained_model_bytes, signature=signature
    )
    engine = MLEngine(registry=registry)  # no tenant_id
    await engine.serve("models://single_tenant/v1", channels=["rest"])
    binding = engine._active_serves[("single_tenant", 1, "rest")]

    # Whatever tenant the caller supplies, single-tenant mode accepts.
    out = await binding.invoke({"a": 0.5, "b": 0.5}, tenant_id="anything")
    assert "predictions" in out
