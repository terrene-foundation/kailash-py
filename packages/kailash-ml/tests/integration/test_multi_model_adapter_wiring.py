# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring test -- ``MultiModelAdapter`` through the real registry.

Per ``rules/facade-manager-detection.md`` MUST Rule 2 every manager-
shape class MUST have a Tier-2 wiring test named
``test_<lowercase_manager_name>_wiring.py`` that:

1. Imports through the framework facade
   (``kailash_ml.serving.multi_model_adapter`` + real
   :class:`ModelRegistry` backed by a real
   :class:`ConnectionManager`).
2. Constructs a real framework instance against real infrastructure
   (SQLite + :class:`LocalFileArtifactStore`).
3. Triggers a code path that calls at least one method on the
   manager.
4. Asserts the externally-observable effect (cache populated,
   ``load_model`` refused with typed error, ``predict`` returns real
   sklearn predictions).

Per ``rules/testing.md`` § Tier 2 NO mocking -- real infra throughout.
"""
from __future__ import annotations

import pickle

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash.db.connection import ConnectionManager
from kailash_ml.engines.model_registry import LocalFileArtifactStore, ModelRegistry
from kailash_ml.serving.multi_model_adapter import MultiModelAdapter
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
async def two_registered_models(registry: ModelRegistry, signature: ModelSignature):
    """Register two models with promoted production aliases."""
    rng = np.random.default_rng(42)
    X = rng.normal(size=(80, 3))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    clf = RandomForestClassifier(n_estimators=5, random_state=42)
    clf.fit(X, y)

    mv_a = await registry.register_model(
        "fraud",
        pickle.dumps(clf),
        metrics=[MetricSpec("accuracy", 0.9)],
        signature=signature,
    )
    await registry.promote_model(mv_a.name, mv_a.version, "production")

    mv_b = await registry.register_model(
        "churn",
        pickle.dumps(clf),
        metrics=[MetricSpec("accuracy", 0.85)],
        signature=signature,
    )
    await registry.promote_model(mv_b.name, mv_b.version, "production")
    return mv_a, mv_b


# ---------------------------------------------------------------------------
# Construction + invariant 3 of #700 (registry passed explicitly)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_multi_model_adapter_construct_with_registry(
    registry: ModelRegistry,
) -> None:
    """Per facade-manager-detection.md Rule 3: registry is a constructor arg."""
    adapter = MultiModelAdapter(registry=registry, cache_size=4)
    assert adapter.registry is registry
    assert adapter.cache_size == 4
    assert adapter.servers == {}


@pytest.mark.integration
async def test_multi_model_adapter_rejects_none_registry() -> None:
    with pytest.raises(ValueError, match="registry"):
        MultiModelAdapter(registry=None, cache_size=4)  # type: ignore[arg-type]


@pytest.mark.integration
async def test_multi_model_adapter_rejects_invalid_cache_size(
    registry: ModelRegistry,
) -> None:
    with pytest.raises(ValueError, match="cache_size"):
        MultiModelAdapter(registry=registry, cache_size=0)
    with pytest.raises(ValueError, match="cache_size"):
        MultiModelAdapter(registry=registry, cache_size=-1)


# ---------------------------------------------------------------------------
# warm_cache -- lazy construction through real registry
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_warm_cache_constructs_one_server_per_model(
    registry: ModelRegistry, two_registered_models
) -> None:
    """warm_cache populates self._servers via InferenceServer.from_registry."""
    adapter = MultiModelAdapter(registry=registry, cache_size=4)
    await adapter.warm_cache(["fraud", "churn"])

    cached = adapter.servers
    assert set(cached.keys()) == {"fraud", "churn"}
    # Each entry MUST be a distinct InferenceServer (1.5.x architecture).
    assert cached["fraud"] is not cached["churn"]
    assert cached["fraud"].config.model_name == "fraud"
    assert cached["churn"].config.model_name == "churn"


@pytest.mark.integration
async def test_warm_cache_is_idempotent(
    registry: ModelRegistry, two_registered_models
) -> None:
    """Calling warm_cache twice does not re-construct already-cached servers."""
    adapter = MultiModelAdapter(registry=registry, cache_size=4)
    await adapter.warm_cache(["fraud"])
    first_server = adapter.servers["fraud"]
    await adapter.warm_cache(["fraud", "churn"])
    # Same identity preserved for the existing entry.
    assert adapter.servers["fraud"] is first_server
    assert "churn" in adapter.servers


@pytest.mark.integration
async def test_warm_cache_rejects_non_list(registry: ModelRegistry) -> None:
    adapter = MultiModelAdapter(registry=registry, cache_size=4)
    with pytest.raises(TypeError, match="list"):
        await adapter.warm_cache("fraud")  # type: ignore[arg-type]


@pytest.mark.integration
async def test_warm_cache_rejects_empty_string_name(
    registry: ModelRegistry,
) -> None:
    adapter = MultiModelAdapter(registry=registry, cache_size=4)
    with pytest.raises(TypeError, match="non-empty"):
        await adapter.warm_cache([""])


# ---------------------------------------------------------------------------
# load_model -- BLOCKED with typed migration hint
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_load_model_raises_typed_error_with_migration_hint(
    registry: ModelRegistry,
) -> None:
    """1.1.x load_model(bytes) is removed in 1.5.x architecture."""
    adapter = MultiModelAdapter(registry=registry, cache_size=4)
    with pytest.raises(TypeError) as exc_info:
        await adapter.load_model("fraud", b"\x00\x01\x02")
    msg = str(exc_info.value)
    # Migration hint MUST mention register_model + warm_cache (specs/ml-serving.md §1.1).
    assert "register_model" in msg
    assert "warm_cache" in msg
    assert "specs/ml-serving.md" in msg


@pytest.mark.integration
async def test_load_model_refusal_does_not_mutate_cache(
    registry: ModelRegistry,
) -> None:
    """The refusal MUST NOT silently drop -- and MUST NOT mutate state."""
    adapter = MultiModelAdapter(registry=registry, cache_size=4)
    with pytest.raises(TypeError):
        await adapter.load_model("fraud", {"weights": [1, 2, 3]})
    assert adapter.servers == {}


# ---------------------------------------------------------------------------
# predict -- end-to-end through real RF classifier
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_predict_dispatches_to_per_model_server(
    registry: ModelRegistry, two_registered_models
) -> None:
    """End-to-end: warm_cache + predict returns real sklearn predictions."""
    adapter = MultiModelAdapter(registry=registry, cache_size=4)
    await adapter.warm_cache(["fraud"])
    out = await adapter.predict(
        "fraud",
        {"amount": 1.2, "merchant_score": 0.4, "velocity": 0.3},
    )
    assert "predictions" in out
    assert len(out["predictions"]) == 1


@pytest.mark.integration
async def test_predict_unknown_name_raises_key_error(
    registry: ModelRegistry,
) -> None:
    """KeyError with migration hint when model not in cache."""
    adapter = MultiModelAdapter(registry=registry, cache_size=4)
    with pytest.raises(KeyError, match="warm_cache"):
        await adapter.predict("fraud", {"x": 1})


@pytest.mark.integration
async def test_predict_rejects_invalid_name(registry: ModelRegistry) -> None:
    adapter = MultiModelAdapter(registry=registry, cache_size=4)
    with pytest.raises(TypeError, match="non-empty"):
        await adapter.predict("", {"x": 1})
    with pytest.raises(TypeError, match="non-empty"):
        await adapter.predict(None, {"x": 1})  # type: ignore[arg-type]
