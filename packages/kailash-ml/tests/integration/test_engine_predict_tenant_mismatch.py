# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 test: predict() cross-tenant access is refused.

Per specs/ml-engines.md §5.1 MUST 3, a multi-tenant model whose tenant_id
does not match MLEngine.tenant_id MUST raise TenantRequiredError before
any artifact is loaded.

Note: In 0.15.0 the underlying ModelRegistry/ModelVersion does not yet
persist tenant_id (shard A adds the tenant_id column). To exercise the
cross-tenant-access gate that lives on MLEngine, we construct a
ModelVersion-shape object with an explicit tenant_id and invoke
engine.predict() directly — that path runs `_check_tenant_match` before
touching the registry, which is what the spec's MUST 3 clause guards.
"""
from __future__ import annotations

import pickle

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import MLEngine
from kailash_ml.engine import TenantRequiredError
from kailash_ml.engines.model_registry import (
    LocalFileArtifactStore,
    ModelRegistry,
    ModelVersion,
)
from kailash_ml.types import FeatureField, FeatureSchema, ModelSignature


@pytest.fixture
async def registry(tmp_path):
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    reg = ModelRegistry(cm, artifact_store=store)
    yield reg
    await cm.close()


@pytest.mark.integration
async def test_predict_refuses_cross_tenant_access(registry):
    """Engine tenant='bob' + model tenant='acme' → TenantRequiredError."""
    rng = np.random.default_rng(seed=7)
    X = rng.random((20, 2), dtype=np.float64)
    y = (X[:, 0] > 0.5).astype(int)
    model = RandomForestClassifier(n_estimators=2, random_state=0)
    model.fit(X, y)

    signature = ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [FeatureField("a", "float64"), FeatureField("b", "float64")],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )
    mv_from_registry = await registry.register_model(
        "acme_churn", pickle.dumps(model), signature=signature
    )

    # Simulate shard-A tenant_id persistence by constructing a
    # ModelVersion instance with an explicit tenant_id attribute. The
    # engine's `_resolve_model` picks the attribute up via getattr().
    mv_scoped = ModelVersion(
        name=mv_from_registry.name,
        version=mv_from_registry.version,
        stage=mv_from_registry.stage,
        metrics=mv_from_registry.metrics,
        signature=mv_from_registry.signature,
        onnx_status=mv_from_registry.onnx_status,
        onnx_error=mv_from_registry.onnx_error,
        artifact_path=mv_from_registry.artifact_path,
        model_uuid=mv_from_registry.model_uuid,
        created_at=mv_from_registry.created_at,
    )
    # Attach tenant_id dynamically (shard A will formalise this field).
    mv_scoped.tenant_id = "acme"  # type: ignore[attr-defined]

    engine = MLEngine(registry=registry, tenant_id="bob")
    with pytest.raises(TenantRequiredError) as exc_info:
        await engine.predict(mv_scoped, {"a": 0.5, "b": 0.5}, channel="direct")
    assert "acme" in str(exc_info.value) or "bob" in str(exc_info.value)


@pytest.mark.integration
async def test_predict_same_tenant_allowed(registry):
    """Engine tenant='acme' + model tenant='acme' → no error, prediction returns."""
    rng = np.random.default_rng(seed=11)
    X = rng.random((20, 2), dtype=np.float64)
    y = (X[:, 0] > 0.5).astype(int)
    model = RandomForestClassifier(n_estimators=2, random_state=0)
    model.fit(X, y)

    signature = ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [FeatureField("a", "float64"), FeatureField("b", "float64")],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )
    mv = await registry.register_model(
        "acme_shared", pickle.dumps(model), signature=signature
    )
    mv.tenant_id = "acme"  # type: ignore[attr-defined]

    engine = MLEngine(registry=registry, tenant_id="acme")
    result = await engine.predict(mv, {"a": 0.5, "b": 0.5}, channel="direct")
    assert result.tenant_id == "acme"
