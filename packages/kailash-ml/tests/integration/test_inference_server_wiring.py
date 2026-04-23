# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring test — ``InferenceServer`` through the real registry.

Per ``rules/facade-manager-detection.md`` MUST Rule 2 every manager-
shape class MUST have a Tier-2 wiring test named
``test_<lowercase_manager_name>_wiring.py`` that:

1. Imports through the framework facade (``kailash_ml.serving`` +
   real :class:`ModelRegistry` backed by real ConnectionManager).
2. Constructs a real framework instance against real infrastructure
   (SQLite in-memory + LocalFileArtifactStore).
3. Triggers a code path that ends up calling at least one method on
   the manager.
4. Asserts the externally-observable effect (URIs, predictions, status
   transitions).

This test proves W25 invariants 1, 3, 4, 5, 6, 7 end-to-end — not just
the unit-level contracts that :mod:`tests.unit.test_serving_server`
covers.
"""
from __future__ import annotations

import pickle

import numpy as np
import polars as pl
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml.engines.model_registry import LocalFileArtifactStore, ModelRegistry
from kailash_ml.errors import (
    InferenceServerError,
    InvalidInputSchemaError,
    ModelNotFoundError,
)
from kailash_ml.serving import InferenceServer, ServeHandle
from kailash_ml.types import FeatureField, FeatureSchema, MetricSpec, ModelSignature


# ---------------------------------------------------------------------------
# Real infrastructure fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def registry(tmp_path):
    """Real SQLite ModelRegistry + real filesystem artifact store."""
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    reg = ModelRegistry(cm, artifact_store=store)
    yield reg
    await cm.close()


@pytest.fixture
def signature() -> ModelSignature:
    """Real :class:`ModelSignature` — drives invariant 1 validation."""
    return ModelSignature(
        input_schema=FeatureSchema(
            name="fraud_features",
            features=[
                FeatureField(name="amount", dtype="float64"),
                FeatureField(name="merchant_score", dtype="float64"),
                FeatureField(name="velocity", dtype="float64"),
            ],
            entity_id_column="user_id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )


@pytest.fixture
async def registered_classifier(registry: ModelRegistry, signature: ModelSignature):
    """Fit + register a real sklearn classifier; promote to production."""
    rng = np.random.default_rng(42)
    X = rng.normal(size=(80, 3))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    clf = RandomForestClassifier(n_estimators=5, random_state=42)
    clf.fit(X, y)

    mv = await registry.register_model(
        "fraud",
        pickle.dumps(clf),
        metrics=[MetricSpec("accuracy", 0.9)],
        signature=signature,
    )
    # Promote to @production so the alias-resolution path is exercised.
    await registry.promote_model(mv.name, mv.version, "production")
    return mv


# ---------------------------------------------------------------------------
# Invariant 5 + 3: alias resolution + URL shape
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_from_registry_resolves_at_production_alias(
    registry: ModelRegistry, registered_classifier
) -> None:
    """km.serve('fraud@production') resolves via registry.get_model(stage=...)."""
    server = await InferenceServer.from_registry(
        "fraud@production",
        registry=registry,
        tenant_id="acme",
        runtime="pickle",
    )
    assert server.config.model_name == "fraud"
    assert server.config.model_version == registered_classifier.version
    assert server.config.alias == "@production"


@pytest.mark.integration
async def test_start_returns_handle_with_predict_model_uri(
    registry: ModelRegistry, registered_classifier
) -> None:
    """Invariant 3 — urls['rest'] ends with /predict/{ModelName}."""
    server = await InferenceServer.from_registry(
        "fraud@production",
        registry=registry,
        tenant_id="acme",
        channels=("rest",),
        runtime="pickle",
    )
    handle: ServeHandle = await server.start()
    try:
        assert handle.urls["rest"].endswith("/predict/fraud")
        assert handle.channels == ("rest",)
        assert handle.model_name == "fraud"
        assert handle.model_version == registered_classifier.version
        assert handle.tenant_id == "acme"
        assert handle.alias == "@production"
    finally:
        await handle.stop()


# ---------------------------------------------------------------------------
# Invariant 4: health 200-shape when model is registered + ready
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_health_returns_healthy_when_model_ready(
    registry: ModelRegistry, registered_classifier
) -> None:
    """Invariant 4 — health() returns status='healthy' post-start."""
    server = await InferenceServer.from_registry(
        "fraud@production",
        registry=registry,
        tenant_id="acme",
        runtime="pickle",
    )
    try:
        await server.start()
        body = server.health()
        assert body["status"] == "healthy"
        assert body["model"] == "fraud"
        assert body["model_version"] == registered_classifier.version
        assert "rest" in body["channels"]
    finally:
        await server.stop()


# ---------------------------------------------------------------------------
# Invariant 1 + 7: signature validation + typed failure modes
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_predict_roundtrip_returns_real_predictions(
    registry: ModelRegistry, registered_classifier
) -> None:
    """End-to-end predict against a real pickled sklearn classifier."""
    server = await InferenceServer.from_registry(
        "fraud@production",
        registry=registry,
        tenant_id="acme",
        runtime="pickle",
    )
    try:
        await server.start()
        result = await server.predict(
            {"amount": 1.2, "merchant_score": 0.4, "velocity": 0.3},
            tenant_id="acme",
        )
        # Real predictions from the registered RF
        assert "predictions" in result
        assert len(result["predictions"]) == 1
        # Prediction is an int (classifier) or list-with-one-int
        pred = result["predictions"][0]
        assert isinstance(pred, (int, np.integer)) or (
            isinstance(pred, list) and len(pred) >= 1
        )
    finally:
        await server.stop()


@pytest.mark.integration
async def test_predict_signature_mismatch_raises_invalid_input_schema(
    registry: ModelRegistry, registered_classifier
) -> None:
    """Invariant 1 — missing feature raises InvalidInputSchemaError."""
    server = await InferenceServer.from_registry(
        "fraud@production",
        registry=registry,
        tenant_id="acme",
        runtime="pickle",
    )
    try:
        await server.start()
        with pytest.raises(InvalidInputSchemaError, match="velocity"):
            await server.predict(
                {"amount": 1.2, "merchant_score": 0.4},  # missing velocity
                tenant_id="acme",
            )
    finally:
        await server.stop()


@pytest.mark.integration
async def test_cross_tenant_predict_refused(
    registry: ModelRegistry, registered_classifier
) -> None:
    """Spec §11.1 — cross-tenant invocation raises InferenceServerError."""
    server = await InferenceServer.from_registry(
        "fraud@production",
        registry=registry,
        tenant_id="acme",
        runtime="pickle",
    )
    try:
        await server.start()
        with pytest.raises(InferenceServerError, match="scoped to tenant"):
            await server.predict(
                {"amount": 1.0, "merchant_score": 0.5, "velocity": 0.2},
                tenant_id="bob",
            )
    finally:
        await server.stop()


@pytest.mark.integration
async def test_model_not_found_raises_typed(registry: ModelRegistry) -> None:
    """Invariant 7 — missing model raises ModelNotFoundError (typed)."""
    with pytest.raises(ModelNotFoundError):
        await InferenceServer.from_registry(
            "does-not-exist@production",
            registry=registry,
            tenant_id="acme",
            runtime="pickle",
        )


# ---------------------------------------------------------------------------
# Invariant 6: pickle opt-in + loud WARN
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_onnx_runtime_loads_when_artifact_present(
    registry: ModelRegistry, registered_classifier
) -> None:
    """ONNX default path loads real ONNX bytes persisted by register_model.

    ``ModelRegistry.register_model`` runs an ONNX export probe on every
    registration with a signature attached (see registry
    :func:`_attempt_onnx_export`). A successful probe stores ``model.onnx``
    alongside ``model.pkl``. Invariant 6's default behaviour — prefer
    ONNX — MUST successfully load that artifact end-to-end.
    """
    server = await InferenceServer.from_registry(
        "fraud@production",
        registry=registry,
        tenant_id="acme",
        runtime="onnx",
    )
    try:
        await server.start()
        assert server.status == "ready"
        # Sanity check: predict through the ONNX runtime returns real
        # predictions that include framework="onnx" tagging.
        result = await server.predict(
            {"amount": 1.0, "merchant_score": 0.5, "velocity": 0.2},
            tenant_id="acme",
        )
        assert result["framework"] == "onnx"
    finally:
        await server.stop()


@pytest.mark.integration
async def test_pickle_runtime_is_explicit_opt_in(
    registry: ModelRegistry, registered_classifier, caplog
) -> None:
    """Invariant 6 — runtime='pickle' emits the loud pickle-fallback WARN.

    ``rules/observability.md §3`` mandates a ``server.load.pickle_fallback``
    WARN log on every pickle load. The sibling unit test asserts the log
    at Tier 1; this Tier 2 test proves the same log fires against the
    real registry + real artifact store.
    """
    import logging as _logging

    with caplog.at_level(_logging.WARNING):
        server = await InferenceServer.from_registry(
            "fraud@production",
            registry=registry,
            tenant_id="acme",
            runtime="pickle",
        )
        try:
            await server.start()
        finally:
            await server.stop()
    fallback_records = [
        r
        for r in caplog.records
        if r.levelname == "WARNING" and "pickle_fallback" in r.message
    ]
    assert len(fallback_records) >= 1


# ---------------------------------------------------------------------------
# ServeHandle status + stop()
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_serve_handle_status_transitions(
    registry: ModelRegistry, registered_classifier
) -> None:
    server = await InferenceServer.from_registry(
        "fraud@production",
        registry=registry,
        tenant_id="acme",
        runtime="pickle",
    )
    handle = await server.start()
    assert handle.status == "ready"
    await handle.stop()
    assert handle.status == "stopped"
    # Idempotent
    await handle.stop()
    assert handle.status == "stopped"
