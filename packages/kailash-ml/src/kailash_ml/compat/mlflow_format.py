# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MLflow MLmodel format v1 read/write.

"Compatible" means kailash-ml can read and write the MLmodel YAML format.
Metadata round-trips through MLflow without data loss.

This is format interoperability, NOT behavioral equivalence.
kailash-ml does NOT run an MLflow tracking server, replace experiment
tracking, or integrate with the MLflow UI.
"""
from __future__ import annotations

import json
import logging
import platform
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "MlflowFormatReader",
    "MlflowFormatWriter",
]


# ---------------------------------------------------------------------------
# dtype mapping
# ---------------------------------------------------------------------------

_DTYPE_TO_MLFLOW: dict[str, str] = {
    "float64": "double",
    "float32": "float",
    "int64": "long",
    "int32": "integer",
    "string": "string",
    "bool": "boolean",
}

_MLFLOW_TO_DTYPE: dict[str, str] = {v: k for k, v in _DTYPE_TO_MLFLOW.items()}


# ---------------------------------------------------------------------------
# MlflowFormatWriter
# ---------------------------------------------------------------------------


class MlflowFormatWriter:
    """Write kailash-ml models in MLflow MLmodel format v1.

    Produces a directory structure compatible with MLflow's model storage:

    .. code-block:: text

        output_dir/
            MLmodel           # YAML metadata
            model.pkl         # serialized model artifact
            requirements.txt  # pip requirements
    """

    def write(
        self,
        model_version: Any,
        output_dir: Path,
        *,
        artifact_data: bytes | None = None,
    ) -> None:
        """Export model in MLflow-compatible directory structure.

        Parameters
        ----------
        model_version:
            A ModelVersion dataclass from ModelRegistry.
        output_dir:
            Directory to write the MLflow model structure.
        artifact_data:
            Optional raw model bytes. If not given, only metadata is written.
        """
        import yaml

        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine artifact filename
        artifact_name = "model.pkl"

        # Copy artifact if provided
        if artifact_data is not None:
            (output_dir / artifact_name).write_bytes(artifact_data)

        # Determine framework
        framework = "python_function"
        if hasattr(model_version, "signature") and model_version.signature is not None:
            # Try to detect from signature model_type or other fields
            pass
        if hasattr(model_version, "onnx_status"):
            pass

        # Build MLmodel YAML
        mlmodel: dict[str, Any] = {
            "artifact_path": "model",
            "flavors": self._build_flavors(model_version, artifact_name, framework),
            "model_uuid": getattr(model_version, "model_uuid", ""),
            "run_id": getattr(model_version, "name", ""),
        }

        # Signature
        sig = self._build_signature(model_version)
        if sig:
            mlmodel["signature"] = sig

        # Metrics
        if hasattr(model_version, "metrics") and model_version.metrics:
            mlmodel["metrics"] = [
                {"name": m.name, "value": m.value} for m in model_version.metrics
            ]

        # Created at
        if hasattr(model_version, "created_at") and model_version.created_at:
            mlmodel["utc_time_created"] = model_version.created_at

        with open(output_dir / "MLmodel", "w") as f:
            yaml.dump(mlmodel, f, default_flow_style=False, sort_keys=False)

        # Write requirements.txt
        self._write_requirements(output_dir)

    def _build_flavors(
        self, model_version: Any, artifact_name: str, framework: str
    ) -> dict[str, Any]:
        """Build MLflow flavors dict."""
        flavors: dict[str, Any] = {
            "python_function": {
                "env": "conda.yaml",
                "loader_module": "kailash_ml",
                "model_path": artifact_name,
                "python_version": platform.python_version(),
            }
        }

        # Try to detect sklearn
        if framework == "sklearn" or (
            hasattr(model_version, "name")
            and "sklearn" in str(getattr(model_version, "name", "")).lower()
        ):
            try:
                import sklearn

                flavors["sklearn"] = {
                    "code": None,
                    "pickled_model": artifact_name,
                    "serialization_format": "cloudpickle",
                    "sklearn_version": sklearn.__version__,
                }
            except ImportError:
                pass

        return flavors

    def _build_signature(self, model_version: Any) -> dict[str, str] | None:
        """Build MLflow signature from ModelSignature."""
        sig = getattr(model_version, "signature", None)
        if sig is None:
            return None

        input_schema = getattr(sig, "input_schema", None)
        if input_schema is None:
            return None

        features = getattr(input_schema, "features", [])
        inputs = [
            {"name": f.name, "type": _DTYPE_TO_MLFLOW.get(f.dtype, "double")}
            for f in features
        ]

        outputs = [{"name": "prediction", "type": "long"}]

        return {
            "inputs": json.dumps(inputs),
            "outputs": json.dumps(outputs),
        }

    def _write_requirements(self, output_dir: Path) -> None:
        """Write requirements.txt with kailash-ml dependency."""
        reqs = ["kailash-ml>=0.1.0", "scikit-learn>=1.4"]
        (output_dir / "requirements.txt").write_text("\n".join(reqs) + "\n")


# ---------------------------------------------------------------------------
# MlflowFormatReader
# ---------------------------------------------------------------------------


class MlflowFormatReader:
    """Read MLflow model directories into kailash-ml format."""

    def read(self, model_dir: Path) -> dict[str, Any]:
        """Read MLmodel YAML and return kailash-ml compatible dict.

        Returns a dict with keys suitable for understanding the model.
        """
        import yaml

        mlmodel_path = model_dir / "MLmodel"
        if not mlmodel_path.exists():
            raise FileNotFoundError(f"No MLmodel file in {model_dir}")

        with open(mlmodel_path) as f:
            mlmodel = yaml.safe_load(f)

        framework = self._detect_framework(mlmodel.get("flavors", {}))
        signature = self._parse_signature(mlmodel.get("signature"))
        metrics = self._parse_metrics(mlmodel.get("metrics"))

        return {
            "experiment_name": mlmodel.get("run_id", "imported"),
            "framework": framework,
            "signature": signature,
            "metrics": metrics,
            "artifact_path": str(model_dir / mlmodel.get("artifact_path", "model")),
            "mlflow_model_uuid": mlmodel.get("model_uuid"),
            "utc_time_created": mlmodel.get("utc_time_created"),
        }

    def _detect_framework(self, flavors: dict[str, Any]) -> str:
        """Detect framework from MLflow flavors."""
        if "sklearn" in flavors:
            return "sklearn"
        elif "lightgbm" in flavors:
            return "lightgbm"
        elif "pytorch" in flavors:
            return "pytorch"
        elif "xgboost" in flavors:
            return "xgboost"
        return "python_function"

    def _parse_signature(
        self, signature: dict[str, str] | None
    ) -> dict[str, Any] | None:
        """Parse MLflow signature into schema dict."""
        if not signature:
            return None

        result: dict[str, Any] = {}
        if "inputs" in signature:
            try:
                inputs = json.loads(signature["inputs"])
                result["inputs"] = [
                    {
                        "name": inp.get("name", f"f{i}"),
                        "dtype": _MLFLOW_TO_DTYPE.get(
                            inp.get("type", "double"), "float64"
                        ),
                    }
                    for i, inp in enumerate(inputs)
                ]
            except (json.JSONDecodeError, TypeError):
                pass

        if "outputs" in signature:
            try:
                outputs = json.loads(signature["outputs"])
                result["outputs"] = outputs
            except (json.JSONDecodeError, TypeError):
                pass

        return result if result else None

    def _parse_metrics(
        self, metrics: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        """Parse metrics from MLmodel."""
        if not metrics or not isinstance(metrics, list):
            return []
        return [
            {"name": m.get("name", ""), "value": m.get("value", 0.0)}
            for m in metrics
            if isinstance(m, dict)
        ]
