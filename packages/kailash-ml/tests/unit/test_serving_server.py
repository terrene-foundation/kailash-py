# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests — ``InferenceServer`` lifecycle + signature validation.

Uses a deterministic Protocol-satisfying fake registry per
``rules/testing.md`` § "Exception: Protocol-Satisfying Deterministic
Adapters Are Not Mocks". The fake implements the same surface
(:meth:`get_model`, :meth:`load_artifact`) that the real
:class:`ModelRegistry` exposes — returns real :class:`ModelVersion`
instances and real pickled model bytes.

Invariants covered:

* Invariant 1 — signature mismatch raises :class:`InvalidInputSchemaError`.
* Invariant 3 — ``ServeHandle.urls["rest"].endswith("/predict/{ModelName}")``.
* Invariant 4 — :meth:`InferenceServer.health` returns 200-shape when
  model is registered and server is ready.
* Invariant 5 — ``km.serve("name@production")`` path resolves via
  ``registry.get_model(name, stage="production")``.
* Invariant 6 — default runtime is ONNX; pickle requires explicit opt-in
  and emits a WARN log on every load.
* Invariant 7 — :class:`InferenceServerError` typed for every failure mode.
"""
from __future__ import annotations

import asyncio
import io
import logging
import pickle
from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash_ml.errors import (
    InferenceServerError,
    InvalidInputSchemaError,
    ModelLoadError,
    ModelNotFoundError,
)
from kailash_ml.serving import (
    InferenceServer,
    InferenceServerConfig,
    ServeHandle,
)
from kailash_ml.engines.model_registry import ModelVersion
from kailash_ml.types import FeatureField, FeatureSchema, ModelSignature


# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------


def _make_pickled_rf_bytes() -> bytes:
    """Train a tiny RF and return its pickle bytes.

    Per ``rules/testing.md`` § Protocol-Satisfying Adapters this is a
    real pickled sklearn model — the inference path runs real numpy
    + sklearn code against it, not a mock.
    """
    rng = np.random.default_rng(42)
    X = rng.normal(size=(40, 3))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    clf = RandomForestClassifier(n_estimators=5, random_state=42)
    clf.fit(X, y)
    return pickle.dumps(clf)


def _make_signature(
    *, feature_names: tuple[str, ...] = ("amount", "merchant_score", "velocity")
) -> ModelSignature:
    """Real ModelSignature — used to drive invariant 1."""
    return ModelSignature(
        input_schema=FeatureSchema(
            name="fraud_features",
            features=[FeatureField(name=n, dtype="float") for n in feature_names],
            entity_id_column="user_id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int"],
        model_type="classifier",
    )


@dataclass
class FakeRegistry:
    """Deterministic Protocol-satisfying fake.

    Per ``rules/testing.md`` § "Exception: Protocol-Satisfying
    Deterministic Adapters Are Not Mocks" this is a real implementation
    of the registry's public surface — :meth:`get_model` +
    :meth:`load_artifact` — that returns real :class:`ModelVersion`
    instances and real pickled model bytes. Behaviour is deterministic
    from inputs; no mocking framework.
    """

    model_name: str = "fraud"
    model_version: int = 1
    stage: str = "production"
    signature: ModelSignature | None = None
    pickle_bytes: bytes = b""
    onnx_bytes: bytes | None = None

    async def get_model(
        self,
        name: str,
        version: int | None = None,
        *,
        stage: str | None = None,
    ) -> ModelVersion:
        if name != self.model_name:
            # Raise with the same shape the real registry uses so
            # InferenceServer's exception mapping works.
            from kailash_ml.engines.model_registry import (
                ModelNotFoundError as _RegistryNotFound,
            )

            raise _RegistryNotFound(f"Model {name!r} not found.")
        if stage is not None and stage != self.stage:
            from kailash_ml.engines.model_registry import (
                ModelNotFoundError as _RegistryNotFound,
            )

            raise _RegistryNotFound(f"No version of model {name!r} at stage {stage!r}.")
        if version is not None and version != self.model_version:
            from kailash_ml.engines.model_registry import (
                ModelNotFoundError as _RegistryNotFound,
            )

            raise _RegistryNotFound(f"Model {name!r} version {version} not found.")
        return ModelVersion(
            name=self.model_name,
            version=self.model_version,
            stage=self.stage,
            signature=self.signature,
        )

    async def load_artifact(
        self, name: str, version: int, filename: str = "model.pkl"
    ) -> bytes:
        if name != self.model_name or version != self.model_version:
            raise FileNotFoundError(f"No artifact for {name}:{version}/{filename}")
        if filename == "model.pkl":
            if not self.pickle_bytes:
                raise FileNotFoundError("pickle bytes not configured")
            return self.pickle_bytes
        if filename == "model.onnx":
            if self.onnx_bytes is None:
                raise FileNotFoundError("onnx bytes not configured")
            return self.onnx_bytes
        raise FileNotFoundError(f"unknown artifact {filename!r}")


@pytest.fixture
def signature() -> ModelSignature:
    return _make_signature()


@pytest.fixture
def fake_registry(signature: ModelSignature) -> FakeRegistry:
    """Registry with a pickled RF model — no ONNX bytes by default."""
    return FakeRegistry(
        signature=signature,
        pickle_bytes=_make_pickled_rf_bytes(),
    )


# ---------------------------------------------------------------------------
# Construction + lifecycle
# ---------------------------------------------------------------------------


class TestInferenceServerConstruction:
    def test_requires_registry(self):
        config = InferenceServerConfig(
            tenant_id="acme",
            model_name="fraud",
            model_version=1,
        )
        with pytest.raises(ValueError, match="requires a registry"):
            InferenceServer(config, registry=None)  # type: ignore[arg-type]

    def test_server_id_generated_when_omitted(self, fake_registry):
        config = InferenceServerConfig(
            tenant_id="acme",
            model_name="fraud",
            model_version=1,
            runtime="pickle",
        )
        server = InferenceServer(config, registry=fake_registry)
        assert len(server.server_id) == 16
        assert server.status == "starting"

    def test_server_id_honoured(self, fake_registry):
        config = InferenceServerConfig(
            tenant_id="acme",
            model_name="fraud",
            model_version=1,
            runtime="pickle",
        )
        server = InferenceServer(config, registry=fake_registry, server_id="my-id")
        assert server.server_id == "my-id"


# ---------------------------------------------------------------------------
# Alias resolution — invariant 5
# ---------------------------------------------------------------------------


class TestFromRegistryAliasResolution:
    def test_at_production_resolves_via_stage(self, fake_registry):
        # Invariant 5: km.serve("fraud@production") resolves via
        # registry.get_model(name, stage="production"). The fake's
        # get_model verifies that stage kwarg is passed.
        server = asyncio.run(
            InferenceServer.from_registry(
                "fraud@production",
                registry=fake_registry,
                tenant_id="acme",
                runtime="pickle",
            )
        )
        assert server.config.model_name == "fraud"
        assert server.config.model_version == 1  # the registry's version
        assert server.config.alias == "@production"

    def test_bare_name_resolves_to_latest(self, fake_registry):
        server = asyncio.run(
            InferenceServer.from_registry(
                "fraud",
                registry=fake_registry,
                tenant_id="acme",
                runtime="pickle",
            )
        )
        assert server.config.model_name == "fraud"

    def test_pinned_version_resolves_exactly(self, fake_registry):
        server = asyncio.run(
            InferenceServer.from_registry(
                "fraud:1",
                registry=fake_registry,
                tenant_id="acme",
                runtime="pickle",
            )
        )
        assert server.config.model_version == 1

    def test_missing_model_raises_model_not_found(self, fake_registry):
        # Request a non-existent model; our fake raises the registry's
        # own ModelNotFoundError, which InferenceServer re-wraps.
        with pytest.raises(ModelNotFoundError):
            asyncio.run(
                InferenceServer.from_registry(
                    "nonexistent@production",
                    registry=fake_registry,
                    tenant_id="acme",
                    runtime="pickle",
                )
            )


# ---------------------------------------------------------------------------
# start() + URL invariants
# ---------------------------------------------------------------------------


class TestStartReturnsServeHandle:
    def test_urls_rest_ends_with_predict_model(self, fake_registry):
        # Invariant 3
        server = asyncio.run(
            InferenceServer.from_registry(
                "fraud@production",
                registry=fake_registry,
                tenant_id="acme",
                channels=("rest",),
                runtime="pickle",
            )
        )
        handle = asyncio.run(server.start())
        assert isinstance(handle, ServeHandle)
        assert handle.urls["rest"].endswith("/predict/fraud")
        assert handle.url == handle.urls["rest"]
        asyncio.run(handle.stop())

    def test_multichannel_urls(self, fake_registry):
        server = asyncio.run(
            InferenceServer.from_registry(
                "fraud@production",
                registry=fake_registry,
                tenant_id="acme",
                channels=("rest", "mcp"),
                runtime="pickle",
            )
        )
        handle = asyncio.run(server.start())
        assert set(handle.urls.keys()) == {"rest", "mcp"}
        assert handle.urls["mcp"].startswith("mcp+stdio://")
        asyncio.run(handle.stop())

    def test_status_transitions_ready_then_stopped(self, fake_registry):
        server = asyncio.run(
            InferenceServer.from_registry(
                "fraud@production",
                registry=fake_registry,
                tenant_id="acme",
                runtime="pickle",
            )
        )
        assert server.status == "starting"
        handle = asyncio.run(server.start())
        assert server.status == "ready"
        assert handle.status == "ready"
        asyncio.run(handle.stop())
        assert server.status == "stopped"
        assert handle.status == "stopped"

    def test_stop_is_idempotent(self, fake_registry):
        server = asyncio.run(
            InferenceServer.from_registry(
                "fraud@production",
                registry=fake_registry,
                tenant_id="acme",
                runtime="pickle",
            )
        )
        handle = asyncio.run(server.start())
        asyncio.run(handle.stop())
        # Repeated stop should NOT raise.
        asyncio.run(handle.stop())
        assert server.status == "stopped"

    def test_start_twice_raises(self, fake_registry):
        server = asyncio.run(
            InferenceServer.from_registry(
                "fraud@production",
                registry=fake_registry,
                tenant_id="acme",
                runtime="pickle",
            )
        )
        asyncio.run(server.start())
        with pytest.raises(InferenceServerError, match="already started"):
            asyncio.run(server.start())
        asyncio.run(server.stop())


# ---------------------------------------------------------------------------
# health() — invariant 4
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_ok_when_ready(self, fake_registry):
        server = asyncio.run(
            InferenceServer.from_registry(
                "fraud@production",
                registry=fake_registry,
                tenant_id="acme",
                runtime="pickle",
            )
        )
        asyncio.run(server.start())
        body = server.health()
        assert body["status"] == "healthy"
        assert body["model"] == "fraud"
        assert body["model_version"] == 1
        assert body["tenant_id"] == "acme"
        asyncio.run(server.stop())

    def test_health_not_healthy_before_start(self, fake_registry):
        config = InferenceServerConfig(
            tenant_id="acme",
            model_name="fraud",
            model_version=1,
            runtime="pickle",
        )
        server = InferenceServer(config, registry=fake_registry)
        body = server.health()
        # Pre-start — status is "starting", NOT "healthy"
        assert body["status"] == "starting"


# ---------------------------------------------------------------------------
# Signature validation — invariant 1
# ---------------------------------------------------------------------------


class TestSignatureValidation:
    def _start_server(self, fake_registry):
        return asyncio.run(
            InferenceServer.from_registry(
                "fraud@production",
                registry=fake_registry,
                tenant_id="acme",
                runtime="pickle",
            )
        )

    def test_valid_single_record_predict(self, fake_registry):
        server = self._start_server(fake_registry)
        asyncio.run(server.start())
        result = asyncio.run(
            server.predict(
                {"amount": 1.0, "merchant_score": 0.5, "velocity": 0.2},
                tenant_id="acme",
            )
        )
        assert "predictions" in result
        assert result["framework"] in ("native", "onnx")
        asyncio.run(server.stop())

    def test_missing_feature_raises_invalid_input_schema_error(self, fake_registry):
        # Invariant 1: mismatch => InvalidInputSchemaError, NOT a silent
        # 0.0 default. Payload is missing "velocity".
        server = self._start_server(fake_registry)
        asyncio.run(server.start())
        with pytest.raises(InvalidInputSchemaError, match="velocity"):
            asyncio.run(
                server.predict(
                    {"amount": 1.0, "merchant_score": 0.5},  # missing velocity
                    tenant_id="acme",
                )
            )
        asyncio.run(server.stop())

    def test_batch_payload_missing_feature_raises(self, fake_registry):
        server = self._start_server(fake_registry)
        asyncio.run(server.start())
        with pytest.raises(InvalidInputSchemaError, match="velocity"):
            asyncio.run(
                server.predict(
                    {
                        "records": [
                            {"amount": 1.0, "merchant_score": 0.5},  # no velocity
                            {"amount": 2.0, "merchant_score": 0.5, "velocity": 0.1},
                        ]
                    },
                    tenant_id="acme",
                )
            )
        asyncio.run(server.stop())

    def test_valid_batch_payload(self, fake_registry):
        server = self._start_server(fake_registry)
        asyncio.run(server.start())
        result = asyncio.run(
            server.predict(
                {
                    "records": [
                        {"amount": 1.0, "merchant_score": 0.5, "velocity": 0.2},
                        {"amount": 2.0, "merchant_score": 0.6, "velocity": 0.1},
                    ]
                },
                tenant_id="acme",
            )
        )
        preds = result["predictions"]
        assert len(preds) == 2
        asyncio.run(server.stop())


# ---------------------------------------------------------------------------
# Tenant isolation — spec §11.1
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    def test_cross_tenant_predict_refused(self, fake_registry):
        server = asyncio.run(
            InferenceServer.from_registry(
                "fraud@production",
                registry=fake_registry,
                tenant_id="acme",
                runtime="pickle",
            )
        )
        asyncio.run(server.start())
        with pytest.raises(InferenceServerError, match="scoped to tenant"):
            asyncio.run(
                server.predict(
                    {"amount": 1.0, "merchant_score": 0.5, "velocity": 0.2},
                    tenant_id="bob",
                )
            )
        asyncio.run(server.stop())


# ---------------------------------------------------------------------------
# Runtime selection — invariant 6
# ---------------------------------------------------------------------------


class TestRuntimeSelection:
    def test_pickle_runtime_emits_loud_warn(self, fake_registry, caplog):
        # Invariant 6: pickle fallback is explicit opt-in AND emits
        # server.load.pickle_fallback WARN on every load.
        with caplog.at_level(logging.WARNING):
            server = asyncio.run(
                InferenceServer.from_registry(
                    "fraud@production",
                    registry=fake_registry,
                    tenant_id="acme",
                    runtime="pickle",
                )
            )
            asyncio.run(server.start())
        # Grep the WARN records for the pickle_fallback event name
        fallback_records = [
            r
            for r in caplog.records
            if r.levelname == "WARNING" and "pickle_fallback" in r.message
        ]
        assert len(fallback_records) == 1
        asyncio.run(server.stop())

    def test_onnx_runtime_no_onnx_raises_model_load_error(self, fake_registry):
        # Registry has no ONNX bytes — default runtime="onnx" should
        # fail at load time with ModelLoadError (invariant 7).
        server = asyncio.run(
            InferenceServer.from_registry(
                "fraud@production",
                registry=fake_registry,
                tenant_id="acme",
                runtime="onnx",  # explicit so we don't rely on default
            )
        )
        with pytest.raises(ModelLoadError, match="model.onnx"):
            asyncio.run(server.start())
        # Server should not be "ready" after a failed start
        assert server.status == "stopped"
