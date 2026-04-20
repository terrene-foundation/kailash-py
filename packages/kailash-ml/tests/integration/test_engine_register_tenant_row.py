# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration test for tenant_id persistence through register().

Per ``specs/ml-engines.md`` §5.1 MUST 4: ``register()`` MUST persist
``tenant_id`` on the model version row and the primary key MUST include
it as ``(tenant_id, name, version)``. Two tenants registering a model
with the same ``name`` MUST NOT collide.

Per §5.2: every register() call MUST write an audit row carrying
``tenant_id``, ``operation="register"``, ``duration_ms``, ``outcome``.
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("skl2onnx")


def _training_result(model: Any, family: str) -> Any:
    from kailash_ml._result import TrainingResult

    result = TrainingResult(
        model_uri="models://smoke/v0",
        metrics={"accuracy": 0.9},
        device_used="cpu",
        accelerator="cpu",
        precision="32-true",
        elapsed_seconds=0.01,
        tracker_run_id=None,
        tenant_id=None,
        artifact_uris={},
        lightning_trainer_config={},
        family=family,
    )
    object.__setattr__(result, "model", model)
    return result


def _fit_minimal_sklearn() -> Any:
    from sklearn.datasets import make_classification
    from sklearn.linear_model import LogisticRegression

    X, y = make_classification(n_samples=60, n_features=4, random_state=42)
    return LogisticRegression(max_iter=200).fit(X.astype(np.float32), y)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_persists_tenant_id_on_version_row() -> None:
    """_kml_engine_versions row carries tenant_id and matches the engine."""
    from kailash_ml import MLEngine
    from kailash_ml.engines import _engine_sql as _sql

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        os.environ["KAILASH_ML_ARTIFACT_ROOT"] = tmp

        engine = MLEngine(tenant_id="acme")
        result = _training_result(_fit_minimal_sklearn(), family="sklearn")
        reg = await engine.register(result, format="onnx")
        assert reg.tenant_id == "acme"

        # Read the row through the SQL helper.
        conn = await engine._acquire_connection()
        row = await _sql.fetch_version_row(
            conn, tenant_id="acme", name=reg.name, version=reg.version
        )
        assert row is not None
        assert row["tenant_id"] == "acme"
        assert row["name"] == reg.name
        assert row["version"] == reg.version
        assert row["stage"] == "staging"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_two_tenants_independent_versions() -> None:
    """(tenant_id, name, version) primary key — two tenants don't collide."""
    from kailash_ml import MLEngine
    from kailash_ml.engines import _engine_sql as _sql

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        os.environ["KAILASH_ML_ARTIFACT_ROOT"] = tmp

        engine_a = MLEngine(tenant_id="acme")
        engine_b = MLEngine(tenant_id="globex")
        result_a = _training_result(_fit_minimal_sklearn(), family="sklearn")
        result_b = _training_result(_fit_minimal_sklearn(), family="sklearn")

        reg_a = await engine_a.register(result_a, name="sklearn", format="onnx")
        reg_b = await engine_b.register(result_b, name="sklearn", format="onnx")

        # Both tenants start at version 1 — no cross-tenant collision.
        assert reg_a.version == 1
        assert reg_b.version == 1

        # Second register in tenant "acme" increments.
        reg_a2 = await engine_a.register(result_a, name="sklearn", format="onnx")
        assert reg_a2.version == 2

        # Counts are tenant-scoped.
        conn = await engine_a._acquire_connection()
        n_acme = await _sql.count_versions(conn, tenant_id="acme", name="sklearn")
        n_globex = await _sql.count_versions(conn, tenant_id="globex", name="sklearn")
        assert n_acme == 2
        assert n_globex == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_writes_audit_row_with_tenant_id() -> None:
    """§5.2 audit row — tenant_id + operation + outcome persisted."""
    from kailash_ml import MLEngine

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        os.environ["KAILASH_ML_ARTIFACT_ROOT"] = tmp

        engine = MLEngine(tenant_id="acme")
        result = _training_result(_fit_minimal_sklearn(), family="sklearn")
        await engine.register(result, format="onnx")

        conn = await engine._acquire_connection()
        rows = await conn.fetch(
            "SELECT * FROM _kml_engine_audit WHERE tenant_id = ? " "AND operation = ?",
            "acme",
            "register",
        )
        assert len(rows) >= 1
        row = rows[0]
        assert row["tenant_id"] == "acme"
        assert row["operation"] == "register"
        assert row["outcome"] == "success"
        assert row["duration_ms"] > 0
        assert row["model_uri"].startswith("models://")
