# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""InferenceServer engine -- load, cache, serve predictions with Nexus integration.

Loads models from ModelRegistry, caches them in memory (LRU), serves
predictions via predict() and predict_batch(). Nexus import is lazy per R2-13.
"""
from __future__ import annotations

import logging
import pickle
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl
from kailash_ml.types import MLToolProtocol, ModelSignature

from kailash_ml.engines.model_registry import ModelRegistry, ModelVersion
from kailash_ml.interop import to_sklearn_input

logger = logging.getLogger(__name__)

__all__ = [
    "InferenceServer",
    "PredictionResult",
]


# ---------------------------------------------------------------------------
# PredictionResult
# ---------------------------------------------------------------------------


@dataclass
class PredictionResult:
    """Result of a single prediction."""

    prediction: Any  # class label or regression value
    probabilities: list[float] | None  # class probabilities (classification only)
    model_name: str
    model_version: int
    inference_time_ms: float
    inference_path: str  # "onnx" | "native"

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction": self.prediction,
            "probabilities": self.probabilities,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "inference_time_ms": self.inference_time_ms,
            "inference_path": self.inference_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PredictionResult:
        return cls(
            prediction=data["prediction"],
            probabilities=data.get("probabilities"),
            model_name=data["model_name"],
            model_version=data["model_version"],
            inference_time_ms=data["inference_time_ms"],
            inference_path=data["inference_path"],
        )


# ---------------------------------------------------------------------------
# Cached model entry
# ---------------------------------------------------------------------------


@dataclass
class _CachedModel:
    """In-memory cached model entry."""

    model: Any  # deserialized sklearn/lightgbm model
    onnx_session: Any | None  # onnxruntime.InferenceSession or None
    version: int
    name: str
    signature: ModelSignature | None
    framework: str  # "sklearn" | "lightgbm"
    inference_path: str  # "onnx" | "native"


# ---------------------------------------------------------------------------
# LRU Cache
# ---------------------------------------------------------------------------


class _ModelCache:
    """LRU cache for loaded models."""

    def __init__(self, max_size: int = 10) -> None:
        self._cache: OrderedDict[str, _CachedModel] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> _CachedModel | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, model: _CachedModel) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)  # evict LRU
        self._cache[key] = model

    def stats(self) -> dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "models": list(self._cache.keys()),
        }


# ---------------------------------------------------------------------------
# InferenceServer
# ---------------------------------------------------------------------------


class InferenceServer:
    """[P0: Production] Inference server for model serving.

    Parameters
    ----------
    registry:
        ModelRegistry to load models from.
    cache_size:
        Maximum number of models to cache in memory (LRU).
    """

    def __init__(
        self,
        registry: ModelRegistry,
        *,
        cache_size: int = 10,
    ) -> None:
        self._registry = registry
        self._cache = _ModelCache(max_size=cache_size)

    # ------------------------------------------------------------------
    # predict (single record)
    # ------------------------------------------------------------------

    async def predict(
        self,
        model_name: str,
        features: dict[str, Any],
        *,
        version: int | None = None,
        options: dict | None = None,
        strict: bool = True,
    ) -> PredictionResult:
        """Single-record prediction.

        Parameters
        ----------
        model_name:
            Name of the registered model.
        features:
            Feature dict, e.g. {"feature_a": 1.0, "feature_b": 2.0}.
        version:
            Specific version. If None, uses the latest version.
        strict:
            If True (default), raise ValueError when required features are
            missing or contain non-numeric values. If False, log a warning
            and substitute 0.0 for missing features (legacy behaviour).
        """
        model_entry = await self._get_model(model_name, version)

        feature_names = self._resolve_feature_names(model_entry, features)
        self._validate_features(features, feature_names, strict=strict)

        start = time.perf_counter()

        if (
            model_entry.inference_path == "onnx"
            and model_entry.onnx_session is not None
        ):
            result = self._predict_onnx(model_entry.onnx_session, features, model_entry)
        else:
            result = self._predict_native(model_entry.model, features, model_entry)

        inference_ms = (time.perf_counter() - start) * 1000

        return PredictionResult(
            prediction=result["prediction"],
            probabilities=result.get("probabilities"),
            model_name=model_name,
            model_version=model_entry.version,
            inference_time_ms=inference_ms,
            inference_path=model_entry.inference_path,
        )

    # ------------------------------------------------------------------
    # predict_batch
    # ------------------------------------------------------------------

    async def predict_batch(
        self,
        model_name: str,
        records: list[dict[str, Any]],
        *,
        version: int | None = None,
        strict: bool = True,
    ) -> list[PredictionResult]:
        """Batch prediction. Converts records to polars -> numpy for efficiency.

        Parameters
        ----------
        model_name:
            Name of the registered model.
        records:
            List of feature dicts.
        version:
            Specific version. If None, uses the latest version.
        strict:
            If True (default), raise ValueError when required features are
            missing or contain non-numeric values. If False, log a warning
            and substitute 0.0 for missing features (legacy behaviour).
        """
        if not records:
            return []

        model_entry = await self._get_model(model_name, version)

        feature_cols = self._resolve_feature_names(model_entry, records[0])

        # Validate every record in the batch
        for idx, record in enumerate(records):
            self._validate_features(
                record, feature_cols, strict=strict, record_index=idx
            )

        # In non-strict mode, fill missing features with 0.0 so the
        # DataFrame has all expected columns.
        if not strict:
            patched_records: list[dict[str, Any]] = []
            for record in records:
                patched = dict(record)
                for col in feature_cols:
                    if col not in patched:
                        patched[col] = 0.0
                    else:
                        try:
                            patched[col] = float(patched[col])
                        except (TypeError, ValueError):
                            patched[col] = 0.0
                patched_records.append(patched)
            records = patched_records

        # Convert list[dict] -> polars -> numpy in one shot
        df = pl.DataFrame(records)
        X, _, _col_info = to_sklearn_input(df, feature_columns=feature_cols)

        start = time.perf_counter()
        predictions = model_entry.model.predict(X)
        probabilities: list[list[float]] | None = None
        if hasattr(model_entry.model, "predict_proba"):
            try:
                probabilities = model_entry.model.predict_proba(X).tolist()
            except Exception as exc:
                logger.debug("predict_proba failed: %s", exc)
                probabilities = None
        inference_ms = (time.perf_counter() - start) * 1000

        per_record_ms = inference_ms / len(records) if records else 0

        results: list[PredictionResult] = []
        for i, pred in enumerate(predictions):
            prob_row = probabilities[i] if probabilities else None
            results.append(
                PredictionResult(
                    prediction=_to_python(pred),
                    probabilities=prob_row,
                    model_name=model_name,
                    model_version=model_entry.version,
                    inference_time_ms=per_record_ms,
                    inference_path=model_entry.inference_path,
                )
            )
        return results

    # ------------------------------------------------------------------
    # warm_cache
    # ------------------------------------------------------------------

    async def warm_cache(self, model_names: list[str]) -> None:
        """Pre-load models into cache."""
        for name in model_names:
            await self._get_model(name, None)
        logger.info("Warmed cache with models: %s", model_names)

    # ------------------------------------------------------------------
    # MLToolProtocol implementation
    # ------------------------------------------------------------------

    async def get_metrics(
        self,
        model_name: str,
        version: str | None = None,
        *,
        options: dict | None = None,
    ) -> dict[str, Any]:
        """MLToolProtocol: return model metrics from registry."""
        v = int(version) if version else None
        model = await self._registry.get_model(model_name, v)
        return {
            "metrics": {m.name: m.value for m in model.metrics},
            "version": model.version,
        }

    async def get_model_info(
        self,
        model_name: str,
        *,
        options: dict | None = None,
    ) -> dict[str, Any]:
        """MLToolProtocol: return model metadata."""
        versions = await self._registry.get_model_versions(model_name)
        latest = versions[0] if versions else None
        return {
            "name": model_name,
            "stage": latest.stage if latest else None,
            "versions": [v.version for v in versions],
            "signature": (
                latest.signature.to_dict() if latest and latest.signature else None
            ),
        }

    # ------------------------------------------------------------------
    # Nexus integration (lazy import)
    # ------------------------------------------------------------------

    def register_endpoints(self, nexus: Any) -> None:
        """Register prediction endpoints with Nexus. Lazy import."""
        # Lazy import -- only when user calls this method
        from kailash_nexus import NexusHandler  # noqa: F401

        server = self

        @nexus.handler("POST", "/api/predict/{model_name}")
        async def predict_handler(request: Any) -> dict:
            model_name = request.path_params["model_name"]
            features = await request.json()
            result = await server.predict(model_name, features)
            return result.__dict__

        @nexus.handler("POST", "/api/predict_batch/{model_name}")
        async def predict_batch_handler(request: Any) -> list:
            model_name = request.path_params["model_name"]
            records = await request.json()
            results = await server.predict_batch(model_name, records)
            return [r.__dict__ for r in results]

        @nexus.handler("GET", "/api/ml/health")
        async def health_handler(request: Any) -> dict:
            return server._cache.stats()

    # ------------------------------------------------------------------
    # MCP integration (lazy import)
    # ------------------------------------------------------------------

    def register_mcp_tools(self, server: Any, namespace: str = "ml") -> None:
        """Register prediction tools with an MCP server.

        Symmetric with ``register_endpoints()`` for Nexus HTTP.

        Args:
            server: FastMCP server instance.
            namespace: Tool namespace prefix (e.g., "ml").
        """
        inference = self

        @server.tool(name=f"{namespace}.predict")
        async def predict_tool(
            model_name: str,
            features: str,
            version: int | None = None,
        ) -> dict:
            """Run a single prediction on a registered model."""
            import json as _json

            feature_dict = (
                _json.loads(features) if isinstance(features, str) else features
            )
            result = await inference.predict(model_name, feature_dict, version=version)
            return result.__dict__

        @server.tool(name=f"{namespace}.predict_batch")
        async def predict_batch_tool(
            model_name: str,
            records: str,
            version: int | None = None,
        ) -> list:
            """Run batch predictions on a registered model."""
            import json as _json

            records_list = _json.loads(records) if isinstance(records, str) else records
            results = await inference.predict_batch(
                model_name, records_list, version=version
            )
            return [r.__dict__ for r in results]

        @server.tool(name=f"{namespace}.model_info")
        async def model_info_tool(model_name: str) -> dict:
            """Get metadata for a registered model."""
            return inference._cache.stats()

    # ------------------------------------------------------------------
    # Private: feature validation
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_feature_names(
        entry: _CachedModel,
        features: dict[str, Any],
    ) -> list[str]:
        """Return the ordered list of expected feature names."""
        if entry.signature:
            return [f.name for f in entry.signature.input_schema.features]
        return list(features.keys())

    @staticmethod
    def _validate_features(
        features: dict[str, Any],
        feature_names: list[str],
        *,
        strict: bool = True,
        record_index: int | None = None,
    ) -> None:
        """Validate that *features* contains all required names with numeric values.

        Parameters
        ----------
        features:
            The feature dict from the caller.
        feature_names:
            Ordered list of expected feature names (from model signature).
        strict:
            If True, raise ``ValueError`` on problems. If False, log a
            warning and allow the caller to fall back to 0.0.
        record_index:
            If set, included in error/warning messages to identify which
            record in a batch is problematic.
        """
        record_label = (
            f" (record index {record_index})" if record_index is not None else ""
        )

        # --- missing features ---
        missing = [n for n in feature_names if n not in features]
        if missing:
            msg = (
                f"Missing required features{record_label}: {missing}. "
                f"Expected features: {feature_names}"
            )
            if strict:
                raise ValueError(msg)
            logger.warning("Non-strict mode: %s — substituting 0.0", msg)

        # --- type validation (only for keys that are present) ---
        non_numeric: list[str] = []
        for name in feature_names:
            if name not in features:
                continue
            val = features[name]
            # Allow int, float, bool (bool is subclass of int), np scalars
            if isinstance(val, (int, float)):
                continue
            if hasattr(val, "item"):
                # numpy scalar — try conversion
                continue
            try:
                float(val)
            except (TypeError, ValueError):
                non_numeric.append(name)

        if non_numeric:
            bad_pairs = {n: type(features[n]).__name__ for n in non_numeric}
            msg = (
                f"Non-numeric feature values{record_label}: {bad_pairs}. "
                "All feature values must be numeric."
            )
            if strict:
                raise ValueError(msg)
            logger.warning("Non-strict mode: %s — substituting 0.0", msg)

    # ------------------------------------------------------------------
    # Private: model loading
    # ------------------------------------------------------------------

    async def _get_model(self, model_name: str, version: int | None) -> _CachedModel:
        """Load model from cache or registry."""
        # Determine version
        if version is None:
            mv = await self._registry.get_model(model_name)
        else:
            mv = await self._registry.get_model(model_name, version)

        cache_key = f"{model_name}:v{mv.version}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Load artifact and deserialize
        artifact_bytes = await self._registry.load_artifact(
            model_name, mv.version, "model.pkl"
        )
        # SECURITY: pickle deserialization executes arbitrary code.
        # Only load artifacts from TRUSTED sources (models you trained yourself).
        # Do NOT load artifacts from untrusted users or external sources.
        model = pickle.loads(artifact_bytes)

        # Determine framework
        module_name = type(model).__module__
        framework = "lightgbm" if "lightgbm" in module_name else "sklearn"

        # Try ONNX session
        onnx_session = None
        inference_path = "native"
        if mv.onnx_status == "success":
            try:
                onnx_bytes = await self._registry.load_artifact(
                    model_name, mv.version, "model.onnx"
                )
                import onnxruntime as ort

                onnx_session = ort.InferenceSession(onnx_bytes)
                inference_path = "onnx"
                logger.info("Loaded ONNX session for '%s' v%d.", model_name, mv.version)
            except (FileNotFoundError, ImportError) as exc:
                logger.info(
                    "ONNX not available for '%s' v%d, using native: %s",
                    model_name,
                    mv.version,
                    exc,
                )

        entry = _CachedModel(
            model=model,
            onnx_session=onnx_session,
            version=mv.version,
            name=model_name,
            signature=mv.signature,
            framework=framework,
            inference_path=inference_path,
        )
        self._cache.put(cache_key, entry)
        return entry

    # ------------------------------------------------------------------
    # Private: prediction helpers
    # ------------------------------------------------------------------

    def _predict_native(
        self,
        model: Any,
        features: dict[str, Any],
        entry: _CachedModel,
    ) -> dict[str, Any]:
        """Predict using native sklearn/lightgbm model."""
        # Convert single record to numpy
        feature_names = (
            [f.name for f in entry.signature.input_schema.features]
            if entry.signature
            else list(features.keys())
        )
        values = [float(features.get(name, 0.0)) for name in feature_names]
        X = np.array([values], dtype=np.float64)

        prediction = model.predict(X)[0]
        result: dict[str, Any] = {"prediction": _to_python(prediction)}

        if hasattr(model, "predict_proba"):
            try:
                proba = model.predict_proba(X)[0].tolist()
                result["probabilities"] = proba
            except Exception as exc:
                logger.debug("predict_proba failed: %s", exc)

        return result

    def _predict_onnx(
        self,
        session: Any,
        features: dict[str, Any],
        entry: _CachedModel,
    ) -> dict[str, Any]:
        """Predict using ONNX runtime session."""
        feature_names = (
            [f.name for f in entry.signature.input_schema.features]
            if entry.signature
            else list(features.keys())
        )
        values = [float(features.get(name, 0.0)) for name in feature_names]
        X = np.array([values], dtype=np.float32)

        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: X})

        prediction = outputs[0][0]
        result: dict[str, Any] = {"prediction": _to_python(prediction)}

        # If there are probability outputs
        if len(outputs) > 1:
            proba = outputs[1]
            if isinstance(proba, list) and len(proba) > 0:
                if isinstance(proba[0], dict):
                    # ONNX classifiers output [{class: prob, ...}]
                    result["probabilities"] = list(proba[0].values())
                else:
                    result["probabilities"] = list(proba[0])
            elif hasattr(proba, "tolist"):
                result["probabilities"] = proba[0].tolist()

        return result


def _to_python(val: Any) -> Any:
    """Convert numpy scalar to Python native type."""
    if hasattr(val, "item"):
        return val.item()
    return val
