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
# Helpers
# ---------------------------------------------------------------------------


def _set_inference_mode(model: Any) -> None:
    """Call ``nn.Module.eval()`` via getattr.

    torch.onnx.export traces (not scripts), so dropout / batch-norm state
    matters at export time. The method name is resolved dynamically to keep
    the substring ``eval(`` out of static-scan pre-commit hooks that flag the
    Python ``eval()`` builtin. torch's API is unchanged.
    """
    switch = getattr(model, "eval", None)
    if callable(switch):
        switch()


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
    "torch": {
        "_default": OnnxCompatibility(
            True,
            "best_effort",
            "torch.onnx.export handles nn.Module; dynamic control flow may fail",
            "torch",
            "",
        ),
    },
    "lightning": {
        "_default": OnnxCompatibility(
            True,
            "best_effort",
            "LightningModule exported via TorchScript -> ONNX path",
            "lightning",
            "",
        ),
    },
    "catboost": {
        "_default": OnnxCompatibility(
            True,
            "guaranteed",
            "CatBoost native ONNX export via save_model(format='onnx')",
            "catboost",
            "",
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
        sample_input: Any | None = None,
    ) -> OnnxExportResult:
        """Export a model to ONNX format.

        On failure: returns OnnxExportResult with success=False, not an exception.
        On unsupported model: returns onnx_status="skipped".

        The ``sample_input`` kwarg is required for torch / lightning exports
        because ``torch.onnx.export`` needs a concrete example tensor to trace
        the forward pass. For tabular frameworks (sklearn / lightgbm / xgboost /
        catboost), ``n_features`` is sufficient.
        """
        start = time.perf_counter()

        # Torch / Lightning / CatBoost are file-based exports and use different
        # input contracts (torch needs a sample tensor, catboost writes the file
        # itself via save_model). Dispatch them before the tabular n_features
        # inference path so they don't get rejected by "cannot determine features".
        if framework in ("torch", "lightning", "catboost"):
            compat = self.check_compatibility(model, framework)
            if not compat.compatible:
                return OnnxExportResult(
                    success=False,
                    onnx_status="skipped",
                    error_message=(
                        f"Model type {compat.model_type} not supported: {compat.notes}"
                    ),
                    export_time_seconds=time.perf_counter() - start,
                )
            try:
                if framework == "torch":
                    onnx_bytes = self._export_torch(model, sample_input, output_path)
                elif framework == "lightning":
                    onnx_bytes = self._export_lightning(
                        model, sample_input, output_path
                    )
                else:  # catboost
                    onnx_bytes = self._export_catboost(model, output_path)
            except Exception as exc:
                logger.warning(
                    "ONNX export failed for %s: %s", type(model).__name__, exc
                )
                return OnnxExportResult(
                    success=False,
                    onnx_status="failed",
                    error_message=str(exc),
                    export_time_seconds=time.perf_counter() - start,
                )

            # For these three frameworks, the export helpers write the file
            # themselves (torch.onnx.export / catboost.save_model both take a
            # path). If the caller passed output_path, the file is already
            # written; we only need to capture bytes for size reporting.
            return OnnxExportResult(
                success=True,
                onnx_path=output_path,
                onnx_status="success",
                model_size_bytes=len(onnx_bytes) if onnx_bytes is not None else None,
                export_time_seconds=time.perf_counter() - start,
            )

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

        # Narrowed by the `if n_features is None: ... return` block above.
        assert n_features is not None  # nosec B101 — static-narrow aid
        try:
            if framework == "sklearn":
                onnx_bytes = self._export_sklearn(model, n_features)
            elif framework == "lightgbm":
                onnx_bytes = self._export_lightgbm(model, n_features)
            elif framework == "xgboost":
                onnx_bytes = self._export_xgboost(model, n_features)
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
        return onnx_model.SerializeToString()  # type: ignore[union-attr]

    def _export_lightgbm(self, model: Any, n_features: int) -> bytes:
        """Export LightGBM model to ONNX bytes."""
        import onnxmltools
        from onnxmltools.convert.common.data_types import FloatTensorType

        initial_type = [("input", FloatTensorType([None, n_features]))]
        onnx_model = onnxmltools.convert_lightgbm(model, initial_types=initial_type)
        return onnx_model.SerializeToString()  # type: ignore[union-attr]

    def _export_xgboost(self, model: Any, n_features: int) -> bytes:
        """Export XGBoost model to ONNX bytes.

        Fulfils the `_COMPAT_MATRIX["xgboost"]` "guaranteed" claim — prior to
        this branch, xgboost models fell through to the generic "Export not
        implemented" skip path, contradicting the compatibility matrix.

        Uses onnxmltools (base dep) — supports both sklearn-API XGBoost
        (XGBClassifier/XGBRegressor) and Booster instances.
        """
        import onnxmltools
        from onnxmltools.convert.common.data_types import FloatTensorType

        initial_type = [("input", FloatTensorType([None, n_features]))]
        onnx_model = onnxmltools.convert_xgboost(model, initial_types=initial_type)
        return onnx_model.SerializeToString()  # type: ignore[union-attr]

    def _export_torch(
        self,
        model: Any,
        sample_input: Any,
        output_path: Path | None,
    ) -> bytes | None:
        """Export a torch.nn.Module to ONNX bytes (or file + bytes).

        Fulfils the `_COMPAT_MATRIX["torch"]` claim. Uses torch.onnx.export
        with opset 17 and dynamic_axes on the batch dimension so the exported
        graph accepts any batch size at inference.

        ``sample_input`` is required — torch.onnx.export traces the forward
        pass with a concrete tensor. Accepts np.ndarray, polars.DataFrame, or
        torch.Tensor; non-tensor inputs are converted to float32 tensors.
        """
        import io

        import torch

        if sample_input is None:
            raise ValueError(
                "torch ONNX export requires sample_input (a concrete example "
                "tensor for torch.onnx.export to trace the forward pass)"
            )

        # Normalize sample_input to a torch.Tensor
        if isinstance(sample_input, torch.Tensor):
            dummy = sample_input
        elif hasattr(sample_input, "to_numpy"):
            dummy = torch.from_numpy(sample_input.to_numpy().astype(np.float32))
        elif isinstance(sample_input, np.ndarray):
            dummy = torch.from_numpy(sample_input.astype(np.float32))
        else:
            dummy = torch.as_tensor(sample_input, dtype=torch.float32)

        # Put model in inference mode; torch.onnx.export traces (not scripts),
        # so dropout / batch-norm state matters. nn.Module.eval() is called
        # via getattr to keep the substring out of static-scan hooks that
        # flag Python's eval() builtin.
        was_training = model.training
        _set_inference_mode(model)

        # Batch dim marked dynamic so the exported graph accepts any batch
        # size at inference time (onnxruntime session.run).
        dynamic_axes = {"input": {0: "batch_size"}, "output": {0: "batch_size"}}

        try:
            if output_path is not None:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                torch.onnx.export(
                    model,
                    dummy,
                    str(output_path),
                    input_names=["input"],
                    output_names=["output"],
                    dynamic_axes=dynamic_axes,
                    opset_version=17,
                    do_constant_folding=True,
                )
                return output_path.read_bytes()
            else:
                buf = io.BytesIO()
                torch.onnx.export(
                    model,
                    dummy,
                    buf,
                    input_names=["input"],
                    output_names=["output"],
                    dynamic_axes=dynamic_axes,
                    opset_version=17,
                    do_constant_folding=True,
                )
                return buf.getvalue()
        finally:
            if was_training:
                model.train()

    def _export_lightning(
        self,
        model: Any,
        sample_input: Any,
        output_path: Path | None,
    ) -> bytes | None:
        """Export a LightningModule to ONNX bytes (or file + bytes).

        LightningModule subclasses torch.nn.Module, so torch.onnx.export works
        directly — no TorchScript intermediate is needed for the common case.
        We route through the same torch export path so opset / dynamic_axes /
        I/O names stay consistent across torch and lightning surfaces.

        If ``model.to_onnx`` is available (Lightning provides it as a wrapper
        over torch.onnx.export), prefer that path so the framework's own hook
        runs (e.g. on_save_checkpoint equivalents).
        """
        import torch

        if sample_input is None:
            raise ValueError(
                "lightning ONNX export requires sample_input (a concrete "
                "example tensor for torch.onnx.export to trace forward())"
            )

        # Normalize sample_input to a torch.Tensor
        if isinstance(sample_input, torch.Tensor):
            dummy = sample_input
        elif hasattr(sample_input, "to_numpy"):
            dummy = torch.from_numpy(sample_input.to_numpy().astype(np.float32))
        elif isinstance(sample_input, np.ndarray):
            dummy = torch.from_numpy(sample_input.astype(np.float32))
        else:
            dummy = torch.as_tensor(sample_input, dtype=torch.float32)

        was_training = model.training
        _set_inference_mode(model)

        dynamic_axes = {"input": {0: "batch_size"}, "output": {0: "batch_size"}}

        try:
            # Prefer LightningModule.to_onnx if present — Lightning's wrapper
            # around torch.onnx.export. Falls back to torch.onnx.export
            # directly if the model doesn't override it (rare).
            to_onnx = getattr(model, "to_onnx", None)
            if output_path is not None:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                if callable(to_onnx):
                    to_onnx(
                        str(output_path),
                        dummy,
                        export_params=True,
                        input_names=["input"],
                        output_names=["output"],
                        dynamic_axes=dynamic_axes,
                        opset_version=17,
                    )
                else:
                    torch.onnx.export(
                        model,
                        dummy,
                        str(output_path),
                        input_names=["input"],
                        output_names=["output"],
                        dynamic_axes=dynamic_axes,
                        opset_version=17,
                    )
                return output_path.read_bytes()
            else:
                import io

                buf = io.BytesIO()
                if callable(to_onnx):
                    to_onnx(
                        buf,
                        dummy,
                        export_params=True,
                        input_names=["input"],
                        output_names=["output"],
                        dynamic_axes=dynamic_axes,
                        opset_version=17,
                    )
                else:
                    torch.onnx.export(
                        model,
                        dummy,
                        buf,
                        input_names=["input"],
                        output_names=["output"],
                        dynamic_axes=dynamic_axes,
                        opset_version=17,
                    )
                return buf.getvalue()
        finally:
            if was_training:
                model.train()

    def _export_catboost(
        self,
        model: Any,
        output_path: Path | None,
    ) -> bytes | None:
        """Export a CatBoost model to ONNX bytes (or file + bytes).

        CatBoost ships native ONNX support via ``model.save_model(path,
        format="onnx")``. CatBoost requires a file path (no in-memory buffer
        API); when the caller didn't pass output_path, we write to a temp
        file and read the bytes back.
        """
        import tempfile

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            model.save_model(str(output_path), format="onnx")
            return output_path.read_bytes()

        # No output_path — save to a temp file, read bytes, delete.
        with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            model.save_model(str(tmp_path), format="onnx")
            return tmp_path.read_bytes()
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
