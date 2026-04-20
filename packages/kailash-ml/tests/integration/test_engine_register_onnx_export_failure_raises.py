# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 test for ONNX export failure semantics in ``register()``.

Per ``specs/ml-engines.md`` §4.2 MUST 4 / §6.1 MUST 4: when
``register(format="onnx")`` fails to export the model to ONNX, it MUST
raise :class:`OnnxExportError`. Silent fallback to pickle under the
default format is BLOCKED.

``register(format="both")`` tolerates partial ONNX failure (§6.1 MUST 5).
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest


def _training_result_with_unexportable_model() -> Any:
    """Build a TrainingResult carrying a model the ONNX bridge cannot export.

    We use a plain ``object()`` as the "model" — it matches no framework
    in the bridge's ``_COMPAT_MATRIX`` so the export returns
    ``OnnxExportResult(success=False, onnx_status="skipped")`` and
    register() promotes that to :class:`OnnxExportError` per §6.1 MUST 4.
    """
    from kailash_ml._result import TrainingResult

    result = TrainingResult(
        model_uri="models://broken/v0",
        metrics={"accuracy": 0.9},
        device_used="cpu",
        accelerator="cpu",
        precision="32-true",
        elapsed_seconds=0.01,
        tracker_run_id=None,
        tenant_id=None,
        artifact_uris={},
        lightning_trainer_config={},
        family="unknown_family",
    )
    object.__setattr__(result, "model", object())
    return result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_onnx_failure_raises_typed_error() -> None:
    """format='onnx' (default) MUST raise OnnxExportError on failure."""
    from kailash_ml import MLEngine
    from kailash_ml.engine import OnnxExportError

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        os.environ["KAILASH_ML_ARTIFACT_ROOT"] = tmp

        engine = MLEngine()
        result = _training_result_with_unexportable_model()

        with pytest.raises(OnnxExportError) as exc_info:
            await engine.register(result, format="onnx")

        # §4.2 MUST 4: the raised error names the framework + cause so
        # operators can tell which branch failed without reading the log.
        assert exc_info.value.framework is not None
        assert exc_info.value.cause


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_format_both_tolerates_onnx_failure() -> None:
    """format='both' returns RegisterResult with pickle-only artifact_uris (§6.1 MUST 5)."""
    from kailash_ml import MLEngine

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        os.environ["KAILASH_ML_ARTIFACT_ROOT"] = tmp

        engine = MLEngine()
        # Use a real sklearn model — ONNX export succeeds for sklearn so we
        # need an unexportable shape. An ``object()`` with a valid pickle
        # path: object() is picklable. ONNX fails (unknown framework),
        # pickle succeeds, and format="both" returns pickle-only.
        result = _training_result_with_unexportable_model()

        reg = await engine.register(result, format="both")

        # pickle artifact IS present; ONNX is NOT.
        assert "pickle" in reg.artifact_uris
        assert "onnx" not in reg.artifact_uris


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_audit_row_records_failure_outcome() -> None:
    """§5.2 — failed register() still writes audit row with outcome='failure'."""
    from kailash_ml import MLEngine
    from kailash_ml.engine import OnnxExportError

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KAILASH_ML_STORE_URL"] = f"sqlite:///{tmp}/ml.db"
        os.environ["KAILASH_ML_ARTIFACT_ROOT"] = tmp

        engine = MLEngine(tenant_id="acme")
        result = _training_result_with_unexportable_model()

        with pytest.raises(OnnxExportError):
            await engine.register(result, format="onnx")

        # Audit row MUST land even though register() raised.
        conn = await engine._acquire_connection()
        rows = await conn.fetch(
            "SELECT * FROM _kml_engine_audit WHERE tenant_id = ? " "AND outcome = ?",
            "acme",
            "failure",
        )
        assert len(rows) >= 1
        assert rows[0]["operation"] == "register"
