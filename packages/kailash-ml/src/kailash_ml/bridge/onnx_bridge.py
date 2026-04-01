# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ONNX Bridge -- pre-flight check, export, post-export validation.

Enables "train in Python, serve in Rust." Every compatible model gets
ONNX export artifacts. ONNX export failure is NOT fatal -- the model
falls back to native Python inference.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

__all__ = [
    "OnnxBridge",
    "OnnxCompatibility",
    "OnnxExportResult",
    "OnnxValidationResult",
]


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------


@dataclass
class OnnxCompatibility:
    """Result of a pre-flight ONNX compatibility check."""

    compatible: bool
    confidence: str  # "guaranteed", "best_effort", "unsupported"
    notes: str
    framework: str
    model_type: str


@dataclass
class OnnxExportResult:
    """Result of an ONNX export attempt."""

    success: bool
    onnx_path: Path | None = None
    onnx_status: str = "pending"  # "success", "failed", "skipped"
    error_message: str | None = None
    model_size_bytes: int | None = None
    export_time_seconds: float = 0.0


@dataclass
class OnnxValidationResult:
    """Result of post-export ONNX validation."""

    valid: bool
    max_diff: float = 0.0
    mean_diff: float = 0.0
    n_samples: int = 0
    notes: str | None = None


# ---------------------------------------------------------------------------
# Compatibility matrix
# ---------------------------------------------------------------------------

_COMPAT_MATRIX: dict[str, dict[str, OnnxCompatibility]] = {
    "sklearn": {
        "_default": OnnxCompatibility(
            True,
            "guaranteed",
            "skl2onnx handles most sklearn estimators",
            "sklearn",
            "",
        ),
        "Pipeline": OnnxCompatibility(
            True,
            "best_effort",
            "Custom transformers in pipeline may fail",
            "sklearn",
            "Pipeline",
        ),
    },
    "lightgbm": {
        "_default": OnnxCompatibility(
            True,
            "guaranteed",
            "onnxmltools handles all LightGBM models",
            "lightgbm",
            "",
        ),
    },
    "xgboost": {
        "_default": OnnxCompatibility(
            True,
            "guaranteed",
            "onnxmltools handles all XGBoost models",
            "xgboost",
            "",
        ),
    },
    "pytorch": {
        "_default": OnnxCompatibility(
            True,
            "best_effort",
            "Dynamic control flow may fail; static tracing required",
            "pytorch",
            "",
        ),
        "RNN": OnnxCompatibility(
            True,
            "best_effort",
            "Variable sequence lengths need careful export config",
            "pytorch",
            "RNN",
        ),
    },
}


# ---------------------------------------------------------------------------
# OnnxBridge
# ---------------------------------------------------------------------------


class OnnxBridge:
    """[P1: Production with Caveats] ONNX export and validation bridge.

    Provides pre-flight compatibility checks, ONNX export, and
    post-export numerical validation for trained models.
    """

    def check_compatibility(self, model: Any, framework: str) -> OnnxCompatibility:
        """Check ONNX compatibility without attempting export.

        Inspects model class name against the compatibility matrix.
        Runs in <1 second.
        """
        framework_matrix = _COMPAT_MATRIX.get(framework, {})
        model_type = type(model).__name__

        if model_type in framework_matrix:
            compat = framework_matrix[model_type]
        elif "_default" in framework_matrix:
            compat = framework_matrix["_default"]
        else:
            compat = OnnxCompatibility(
                False,
                "unsupported",
                f"Framework '{framework}' not in ONNX compatibility matrix",
                framework,
                model_type,
            )

        return OnnxCompatibility(
            compatible=compat.compatible,
            confidence=compat.confidence,
            notes=compat.notes,
            framework=framework,
            model_type=model_type,
        )

    def export(
        self,
        model: Any,
        framework: str,
        schema: Any | None = None,
        *,
        output_path: Path | None = None,
        n_features: int | None = None,
    ) -> OnnxExportResult:
        """Export a model to ONNX format.

        On failure: returns OnnxExportResult with success=False, not an exception.
        On unsupported model: returns onnx_status="skipped".
        """
        start = time.perf_counter()

        # Pre-flight check
        compat = self.check_compatibility(model, framework)
        if not compat.compatible:
            return OnnxExportResult(
                success=False,
                onnx_status="skipped",
                error_message=f"Model type {compat.model_type} not supported: {compat.notes}",
                export_time_seconds=time.perf_counter() - start,
            )

        # Determine number of features
        if n_features is None and schema is not None:
            if hasattr(schema, "features"):
                n_features = len(schema.features)
            elif hasattr(schema, "input_schema") and hasattr(
                schema.input_schema, "features"
            ):
                n_features = len(schema.input_schema.features)

        if n_features is None:
            # Try to infer from model
            if hasattr(model, "n_features_in_"):
                n_features = model.n_features_in_
            else:
                return OnnxExportResult(
                    success=False,
                    onnx_status="failed",
                    error_message="Cannot determine number of input features for ONNX export",
                    export_time_seconds=time.perf_counter() - start,
                )

        try:
            if framework == "sklearn":
                onnx_bytes = self._export_sklearn(model, n_features)
            elif framework == "lightgbm":
                onnx_bytes = self._export_lightgbm(model, n_features)
            else:
                return OnnxExportResult(
                    success=False,
                    onnx_status="skipped",
                    error_message=f"Export not implemented for framework: {framework}",
                    export_time_seconds=time.perf_counter() - start,
                )
        except Exception as exc:
            logger.warning("ONNX export failed for %s: %s", type(model).__name__, exc)
            return OnnxExportResult(
                success=False,
                onnx_status="failed",
                error_message=str(exc),
                export_time_seconds=time.perf_counter() - start,
            )

        # Write to file if output_path given
        onnx_path = output_path
        if onnx_path is not None:
            onnx_path.parent.mkdir(parents=True, exist_ok=True)
            onnx_path.write_bytes(onnx_bytes)

        return OnnxExportResult(
            success=True,
            onnx_path=onnx_path,
            onnx_status="success",
            model_size_bytes=len(onnx_bytes),
            export_time_seconds=time.perf_counter() - start,
        )

    def validate(
        self,
        model: Any,
        onnx_path: Path,
        sample_input: Any,
        *,
        tolerance: float = 1e-4,
    ) -> OnnxValidationResult:
        """Validate ONNX export by comparing predictions.

        Runs native model and ONNX runtime on same inputs.
        Reports max and mean difference.
        """
        try:
            import onnxruntime as ort
        except ImportError as exc:
            return OnnxValidationResult(
                valid=False,
                notes=f"onnxruntime not installed: {exc}",
            )

        try:
            # Get native predictions
            if hasattr(sample_input, "to_numpy"):
                X = sample_input.to_numpy().astype(np.float32)
            elif isinstance(sample_input, np.ndarray):
                X = sample_input.astype(np.float32)
            else:
                # Try polars DataFrame
                from kailash_ml.interop import to_sklearn_input

                X_arr, _, _ = to_sklearn_input(sample_input)
                X = X_arr.astype(np.float32)

            native_preds = model.predict(X.astype(np.float64))

            # ONNX predictions
            session = ort.InferenceSession(str(onnx_path))
            input_name = session.get_inputs()[0].name
            onnx_preds = session.run(None, {input_name: X})[0]

            # Compare
            native_flat = np.array(native_preds).flatten().astype(np.float64)
            onnx_flat = np.array(onnx_preds).flatten().astype(np.float64)

            min_len = min(len(native_flat), len(onnx_flat))
            diff = np.abs(native_flat[:min_len] - onnx_flat[:min_len])
            max_diff = float(np.max(diff)) if len(diff) > 0 else 0.0
            mean_diff = float(np.mean(diff)) if len(diff) > 0 else 0.0

            valid = max_diff <= tolerance
            notes = None
            if not valid:
                notes = (
                    f"Numeric precision drift detected: max_diff={max_diff:.6f} exceeds "
                    f"tolerance={tolerance}. ONNX model may produce subtly different predictions."
                )

            return OnnxValidationResult(
                valid=valid,
                max_diff=max_diff,
                mean_diff=mean_diff,
                n_samples=min_len,
                notes=notes,
            )
        except Exception as exc:
            return OnnxValidationResult(
                valid=False,
                notes=f"Validation failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Private export methods
    # ------------------------------------------------------------------

    def _export_sklearn(self, model: Any, n_features: int) -> bytes:
        """Export sklearn model to ONNX bytes."""
        import skl2onnx
        from skl2onnx.common.data_types import FloatTensorType

        initial_type = [("input", FloatTensorType([None, n_features]))]
        onnx_model = skl2onnx.convert_sklearn(model, initial_types=initial_type)
        return onnx_model.SerializeToString()

    def _export_lightgbm(self, model: Any, n_features: int) -> bytes:
        """Export LightGBM model to ONNX bytes."""
        import onnxmltools
        from onnxmltools.convert.common.data_types import FloatTensorType

        initial_type = [("input", FloatTensorType([None, n_features]))]
        onnx_model = onnxmltools.convert_lightgbm(model, initial_types=initial_type)
        return onnx_model.SerializeToString()
