# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression for GH issue #700 — 1.1.x InferenceServer multi-model surface.

Per ``rules/testing.md`` § "End-to-End Pipeline Regression" every
canonical pipeline the docs teach MUST have a Tier-2+ regression test
executing DOCS-EXACT code against real infra, asserting the
final user-visible outcome.

This test exercises the 1.1.x DOCS-EXACT pipeline through the back-
compat path:

.. code-block:: python

    server = InferenceServer(registry=registry, cache_size=4)
    await server.warm_cache(["fraud"])
    out = await server.predict("fraud", {...})

Asserts:

1. ``DeprecationWarning`` is emitted at construction (per
   ``rules/observability.md`` Rule 4 -- state transitions are
   loudly observable).
2. The returned object is a :class:`MultiModelAdapter` (route via
   ``InferenceServer.__new__``).
3. ``warm_cache`` populates the per-model server cache.
4. ``predict(name, payload)`` returns real sklearn predictions
   end-to-end.
5. ``load_model(name, bytes)`` raises ``TypeError`` with the
   migration hint -- the 1.5.x architecture has the registry as the
   sole authoritative source of truth.

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


@pytest.fixture
async def fraud_model_registered(registry: ModelRegistry):
    """Register + promote a real sklearn classifier to @production."""
    rng = np.random.default_rng(42)
    X = rng.normal(size=(64, 3))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    clf = RandomForestClassifier(n_estimators=5, random_state=42)
    clf.fit(X, y)

    sig = ModelSignature(
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

    mv = await registry.register_model(
        "fraud",
        pickle.dumps(clf),
        metrics=[MetricSpec("accuracy", 0.9)],
        signature=sig,
    )
    await registry.promote_model(mv.name, mv.version, "production")
    return mv


@pytest.mark.regression
@pytest.mark.integration
async def test_issue_700_legacy_multi_model_adapter_predicts(
    registry: ModelRegistry, fraud_model_registered
) -> None:
    """1.1.x DOCS-EXACT: InferenceServer(registry=, cache_size=) + warm + predict.

    GH issue #700 -- the 1.1.x signature was hard-removed in 1.5.0 without
    a deprecation cycle. This test pins the back-compat path so the next
    refactor that "cleans up" the __new__ routing fails loudly here.
    """
    # 1.1.x DOCS-EXACT construction. Use catch_warnings(record=True) so the
    # filter doesn't reset later assertions.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        server = InferenceServer(registry=registry, cache_size=4)

    # Invariant 1: routes to MultiModelAdapter (per ADR-2 __new__ contract).
    assert isinstance(server, MultiModelAdapter), (
        f"InferenceServer(registry=, cache_size=) MUST route to "
        f"MultiModelAdapter per #700 ADR-2; got {type(server).__name__}"
    )

    # Invariant 2: DeprecationWarning emitted at construction.
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecations) >= 1, (
        f"DeprecationWarning MUST fire when 1.1.x signature is detected; "
        f"got categories={[w.category.__name__ for w in caught]}"
    )
    msg = str(deprecations[0].message)
    assert "1.6.0" in msg, f"DeprecationWarning MUST mention 1.6.0: {msg!r}"
    assert "1.7.0" in msg, f"DeprecationWarning MUST mention 1.7.0 removal: {msg!r}"
    assert (
        "MultiModelAdapter" in msg or "from_registry" in msg
    ), f"DeprecationWarning MUST include migration hint: {msg!r}"

    # Invariant 3: warm_cache populates the per-model server cache.
    await server.warm_cache(["fraud"])
    assert (
        "fraud" in server.servers
    ), "warm_cache MUST populate self._servers per #700 ADR-2 invariant 3"

    # Invariant 4: predict returns real sklearn predictions end-to-end.
    out = await server.predict(
        "fraud",
        {"amount": 1.2, "merchant_score": 0.4, "velocity": 0.3},
    )
    assert "predictions" in out, (
        f"1.1.x predict MUST return predictions through the per-model "
        f"server; got {out!r}"
    )
    assert len(out["predictions"]) == 1


@pytest.mark.regression
@pytest.mark.integration
async def test_issue_700_legacy_load_model_with_bytes_refused(
    registry: ModelRegistry,
) -> None:
    """1.5.x architecture refuses user-supplied bytes (#700 invariant 2).

    Per ADR-2: ``MultiModelAdapter.load_model(name, bytes)`` MUST raise
    TypeError with the migration hint -- registry is the authoritative
    source in 1.5.x. Silent acceptance would re-introduce the byte-
    injection bypass the 1.5.x architecture closed.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        adapter = InferenceServer(registry=registry, cache_size=2)

    with pytest.raises(TypeError) as exc_info:
        await adapter.load_model("fraud", b"\x00\x01\x02")  # type: ignore[union-attr]
    assert "register_model" in str(exc_info.value)
    assert "warm_cache" in str(exc_info.value)
