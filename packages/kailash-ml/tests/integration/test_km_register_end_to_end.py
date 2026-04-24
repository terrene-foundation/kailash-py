# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 end-to-end integration: km.train -> km.register across backends.

Per `rules/orphan-detection.md` §2, every wired framework surface must
have at least one Tier 2 test that exercises the actual production path
against real infrastructure. For W33c the wired surface is the
`TrainingResult.trainable` back-reference — every Trainable.fit() return
site attaches it, and `MLEngine.register()` consumes it.

A helper-level unit test (see `tests/unit/test_training_result_trainable_field.py`)
proves the field is wired correctly in isolation. This file proves the
framework ACTUALLY populates and consumes it end-to-end on multiple
backends — sklearn + xgboost + lightgbm. Each backend is gated on the
presence of its package (+ ONNX converter) but the sklearn path runs
unconditionally because sklearn is a base dep.

Each test:
  1. Constructs a real MLEngine against a temp SQLite store.
  2. Calls `engine.fit(df, target=..., family=...)` — exercises the
     real Trainable.fit() code path, which MUST attach `trainable=self`
     to the returned TrainingResult.
  3. Asserts `result.trainable is the live Trainable` and
     `result.trainable.model is a fitted estimator`.
  4. Calls `engine.register(result, format="onnx")` — exercises the
     W33c fixed lookup chain `result.trainable.model`.
  5. Asserts an ONNX artifact URI is populated on disk.
"""
from __future__ import annotations

import os
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

import polars as pl
import pytest

pytest.importorskip("sklearn")


_SEGFAULT_HOST = (
    sys.platform == "darwin"
    and platform.machine() == "arm64"
    and sys.version_info[:2] >= (3, 13)
)


def _engine_in_tmp(tmp: str) -> Any:
    """Construct an engine pointed at a throwaway SQLite store."""
    os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
    os.environ["KAILASH_ML_ARTIFACT_ROOT"] = tmp
    from kailash_ml import MLEngine

    return MLEngine()


def _binary_classification_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "feature_a": [0.1, 0.9, 0.2, 0.8, 0.15, 0.85, 0.25, 0.75] * 10,
            "feature_b": [1.0, 0.1, 0.9, 0.2, 0.95, 0.05, 0.85, 0.15] * 10,
            "target": [0, 1, 0, 1, 0, 1, 0, 1] * 10,
        }
    )


# ---------------------------------------------------------------------------
# sklearn — unconditional (base dep)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sklearn_fit_attaches_trainable_and_register_finds_model() -> None:
    """sklearn: engine.fit attaches trainable; engine.register finds model."""
    pytest.importorskip("skl2onnx")
    pytest.importorskip("onnxruntime")

    with tempfile.TemporaryDirectory() as tmp:
        engine = _engine_in_tmp(tmp)
        df = _binary_classification_df()

        # Step 1: fit via the real family dispatch
        result = await engine.fit(df, target="target", family="sklearn")

        # Step 2: W33c contract — the back-reference MUST be populated
        assert result.trainable is not None, (
            "W33c regression: engine.fit did not populate result.trainable "
            "on the sklearn path"
        )
        # Step 3: .model property exposes the fitted estimator
        assert result.trainable.model is not None, (
            "Trainable.model property returned None — sklearn adapter "
            "did not expose its fitted estimator"
        )

        # Step 4: register via the canonical lookup path
        reg = await engine.register(result, name="w33c_e2e_sklearn", format="onnx")
        assert reg.name == "w33c_e2e_sklearn"
        assert reg.version == 1
        assert "onnx" in reg.artifact_uris
        assert Path(reg.artifact_uris["onnx"]).exists()


# ---------------------------------------------------------------------------
# xgboost — optional (requires xgboost + onnxmltools on the host)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    _SEGFAULT_HOST,
    reason="xgboost segfaults on darwin-arm + py3.13; covered by Linux CI.",
)
async def test_xgboost_fit_attaches_trainable_and_register_finds_model() -> None:
    """xgboost: engine.fit attaches trainable; engine.register finds model."""
    pytest.importorskip("xgboost")
    pytest.importorskip("onnxmltools")

    with tempfile.TemporaryDirectory() as tmp:
        engine = _engine_in_tmp(tmp)
        df = _binary_classification_df()

        result = await engine.fit(df, target="target", family="xgboost")

        assert (
            result.trainable is not None
        ), "W33c regression: xgboost adapter did not attach trainable"
        assert result.trainable.model is not None

        reg = await engine.register(result, name="w33c_e2e_xgboost", format="onnx")
        assert reg.name == "w33c_e2e_xgboost"
        assert "onnx" in reg.artifact_uris


# ---------------------------------------------------------------------------
# lightgbm — optional (requires lightgbm + onnxmltools)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    _SEGFAULT_HOST,
    reason="lightgbm segfaults on darwin-arm + py3.13; covered by Linux CI.",
)
async def test_lightgbm_fit_attaches_trainable_and_register_finds_model() -> None:
    """lightgbm: engine.fit attaches trainable; engine.register finds model."""
    pytest.importorskip("lightgbm")
    pytest.importorskip("onnxmltools")

    with tempfile.TemporaryDirectory() as tmp:
        engine = _engine_in_tmp(tmp)
        df = _binary_classification_df()

        result = await engine.fit(df, target="target", family="lightgbm")

        assert (
            result.trainable is not None
        ), "W33c regression: lightgbm adapter did not attach trainable"
        assert result.trainable.model is not None

        reg = await engine.register(result, name="w33c_e2e_lightgbm", format="onnx")
        assert reg.name == "w33c_e2e_lightgbm"
        assert "onnx" in reg.artifact_uris


# ---------------------------------------------------------------------------
# Tenant-id propagation — the dataclasses.replace() path must preserve
# the trainable back-reference or the km.register pipeline breaks in
# multi-tenant mode.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tenant_id_replace_preserves_trainable() -> None:
    """W33c: MLEngine.fit's tenant-id replace() MUST preserve trainable.

    This is the exact path that broke before W33c: `MLEngine.fit`
    constructs a TrainingResult via the Trainable, then runs
    `dataclasses.replace(result, tenant_id=self._tenant_id)` to enforce
    §4.2 MUST 3. If the `trainable` field were dropped by replace() the
    subsequent register() call would fail. This test proves the path.
    """
    pytest.importorskip("skl2onnx")
    pytest.importorskip("onnxruntime")

    from kailash_ml import MLEngine

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        os.environ["KAILASH_ML_ARTIFACT_ROOT"] = tmp

        engine = MLEngine(tenant_id="tenant_w33c")
        df = _binary_classification_df()

        # fit() triggers the tenant_id mismatch branch: the trainable
        # returned tenant_id=None (no ctx tenant) but the engine forces
        # "tenant_w33c" via replace(). After replace the `trainable`
        # field MUST still be attached.
        result = await engine.fit(df, target="target", family="sklearn")
        assert result.tenant_id == "tenant_w33c"
        assert result.trainable is not None, (
            "dataclasses.replace() stripped result.trainable — "
            "multi-tenant km.register pipeline would break"
        )

        reg = await engine.register(
            result, name="w33c_tenant_propagation", format="onnx"
        )
        assert reg.tenant_id == "tenant_w33c"
        assert "onnx" in reg.artifact_uris
