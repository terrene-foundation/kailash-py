# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression for GH issue #700 — 1.5.x canonical per-model surface.

Per ``rules/testing.md`` § "End-to-End Pipeline Regression" every
canonical pipeline the docs teach MUST have a Tier-2+ regression test
executing DOCS-EXACT code against real infra, asserting the
final user-visible outcome.

This test exercises the 1.5.x DOCS-EXACT pipeline:

.. code-block:: python

    server = await InferenceServer.from_registry("fraud@production", registry=registry)
    await server.start()
    out = await server.predict({...})

Asserts:

1. NO ``DeprecationWarning`` is emitted along the canonical path
   (the 1.6.0 deprecation routing is reserved exclusively for the
   1.1.x kwarg shape).
2. The returned object is a :class:`InferenceServer` (NOT
   :class:`MultiModelAdapter`).
3. ``predict({...})`` returns real sklearn predictions end-to-end.
4. ``InferenceServer.from_registry_many(names, registry=)`` constructs
   one distinct server per name (the canonical 1.5.x multi-model
   sugar landed by #700).

Per ``rules/testing.md`` § Tier 2/3 NO mocking -- real
:class:`ConnectionManager` + :class:`LocalFileArtifactStore` +
:class:`RandomForestClassifier` throughout.
"""
from __future__ import annotations

import pickle
import warnings

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml import MultiModelAdapter
from kailash_ml.engines.model_registry import LocalFileArtifactStore, ModelRegistry
from kailash_ml.serving.server import InferenceServer
from kailash_ml.types import FeatureField, FeatureSchema, MetricSpec, ModelSignature


@pytest.fixture
async def registry(tmp_path):
    cm = ConnectionManager("sqlite://:memory:")
    await cm.initialize()
    store = LocalFileArtifactStore(root_dir=tmp_path / "artifacts")
    reg = ModelRegistry(cm, artifact_store=store)
    yield reg
    await cm.close()


def _make_signature() -> ModelSignature:
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
async def two_production_models(registry: ModelRegistry):
    """Register + promote TWO real sklearn classifiers to @production."""
    rng = np.random.default_rng(42)
    X = rng.normal(size=(64, 3))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    clf = RandomForestClassifier(n_estimators=5, random_state=42)
    clf.fit(X, y)
    sig = _make_signature()

    mv_a = await registry.register_model(
        "fraud", pickle.dumps(clf), metrics=[MetricSpec("accuracy", 0.9)], signature=sig
    )
    await registry.promote_model(mv_a.name, mv_a.version, "production")

    mv_b = await registry.register_model(
        "churn",
        pickle.dumps(clf),
        metrics=[MetricSpec("accuracy", 0.85)],
        signature=sig,
    )
    await registry.promote_model(mv_b.name, mv_b.version, "production")
    return mv_a, mv_b


@pytest.mark.regression
@pytest.mark.integration
async def test_issue_700_canonical_per_model_predicts(
    registry: ModelRegistry, two_production_models
) -> None:
    """1.5.x DOCS-EXACT: from_registry + start + predict, no DeprecationWarning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        server = await InferenceServer.from_registry(
            "fraud@production",
            registry=registry,
            tenant_id="acme",
            runtime="pickle",
        )

    # Invariant 1: NO DeprecationWarning on the canonical path. The
    # 1.6.0 deprecation routing is reserved for the 1.1.x kwarg shape.
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations == [], (
        f"canonical from_registry path MUST NOT emit DeprecationWarning; "
        f"got: {[str(w.message) for w in deprecations]}"
    )

    # Invariant 2: returns a real InferenceServer (NOT MultiModelAdapter).
    assert isinstance(
        server, InferenceServer
    ), f"from_registry MUST return InferenceServer; got {type(server).__name__}"
    assert not isinstance(server, MultiModelAdapter)

    # Invariant 3: predict returns real sklearn predictions end-to-end.
    try:
        await server.start()
        out = await server.predict(
            {"amount": 1.2, "merchant_score": 0.4, "velocity": 0.3},
            tenant_id="acme",
        )
        assert "predictions" in out
        assert len(out["predictions"]) == 1
    finally:
        await server.stop()


@pytest.mark.regression
@pytest.mark.integration
async def test_issue_700_from_registry_many_returns_distinct_servers(
    registry: ModelRegistry, two_production_models
) -> None:
    """from_registry_many: one distinct InferenceServer per name (#700 ADR-2)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        servers = await InferenceServer.from_registry_many(
            ["fraud", "churn"],
            registry=registry,
            tenant_id="acme",
            runtime="pickle",
        )

    # Invariant: NO DeprecationWarning on this canonical helper.
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations == []

    # Invariant: dict[str, InferenceServer] with one DISTINCT server per name.
    assert set(servers.keys()) == {"fraud", "churn"}
    assert servers["fraud"] is not servers["churn"], (
        "from_registry_many MUST return distinct InferenceServer instances "
        "per #700 ADR-2 invariant 3"
    )
    assert isinstance(servers["fraud"], InferenceServer)
    assert isinstance(servers["churn"], InferenceServer)
    assert servers["fraud"].config.model_name == "fraud"
    assert servers["churn"].config.model_name == "churn"
