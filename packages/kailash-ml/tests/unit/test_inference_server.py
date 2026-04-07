# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for InferenceServer feature validation (strict mode).

Covers the fix for #335: silent 0.0 default for missing features.
Tier 1 (unit) -- mocking allowed for registry/model internals.
"""
from __future__ import annotations

import logging
import pickle
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from kailash_ml.engines.inference_server import (
    InferenceServer,
    PredictionResult,
    _CachedModel,
)
from kailash_ml.types import FeatureField, FeatureSchema, ModelSignature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signature(*feature_names: str) -> ModelSignature:
    """Build a minimal ModelSignature with the given feature names."""
    return ModelSignature(
        input_schema=FeatureSchema(
            "input",
            [FeatureField(name, "float64") for name in feature_names],
            "id",
        ),
        output_columns=["prediction"],
        output_dtypes=["int64"],
        model_type="classifier",
    )


def _make_trained_model() -> RandomForestClassifier:
    """Return a tiny trained RF for testing."""
    model = RandomForestClassifier(n_estimators=5, random_state=42)
    X = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
    y = np.array([0, 1, 0, 1])
    model.fit(X, y)
    return model


def _make_cached_entry(
    model: Any,
    signature: ModelSignature,
    name: str = "test_model",
) -> _CachedModel:
    return _CachedModel(
        model=model,
        onnx_session=None,
        version=1,
        name=name,
        signature=signature,
        framework="sklearn",
        inference_path="native",
    )


def _make_server_with_model(model: Any, signature: ModelSignature) -> InferenceServer:
    """Create an InferenceServer backed by a mock registry that returns
    the given model and signature."""
    entry = _make_cached_entry(model, signature)
    registry = MagicMock()
    server = InferenceServer(registry, cache_size=5)
    # Pre-populate cache so _get_model never hits the registry
    server._cache.put(f"test_model:v1", entry)
    # Mock _get_model to return our cached entry directly
    server._get_model = AsyncMock(return_value=entry)
    return server


# ---------------------------------------------------------------------------
# _validate_features (static method -- no async needed)
# ---------------------------------------------------------------------------


class TestValidateFeatures:
    """Direct tests for the static _validate_features method."""

    def test_complete_features_passes(self) -> None:
        """No error when all features present with numeric values."""
        InferenceServer._validate_features(
            {"a": 1.0, "b": 2.0}, ["a", "b"], strict=True
        )

    def test_missing_features_strict_raises(self) -> None:
        """strict=True raises ValueError listing missing features."""
        with pytest.raises(ValueError, match="Missing required features.*feature_b"):
            InferenceServer._validate_features(
                {"feature_a": 1.0}, ["feature_a", "feature_b"], strict=True
            )

    def test_missing_multiple_features_strict_lists_all(self) -> None:
        """Error message lists all missing features, not just the first."""
        with pytest.raises(ValueError, match="feature_b") as exc_info:
            InferenceServer._validate_features(
                {"feature_a": 1.0},
                ["feature_a", "feature_b", "feature_c"],
                strict=True,
            )
        assert "feature_c" in str(exc_info.value)

    def test_missing_features_nonstrict_logs_warning(self, caplog) -> None:
        """strict=False logs a warning instead of raising."""
        with caplog.at_level(logging.WARNING):
            InferenceServer._validate_features(
                {"feature_a": 1.0},
                ["feature_a", "feature_b"],
                strict=False,
            )
        assert "Missing required features" in caplog.text
        assert "feature_b" in caplog.text
        assert "substituting 0.0" in caplog.text

    def test_non_numeric_value_strict_raises(self) -> None:
        """strict=True raises ValueError for non-numeric values."""
        with pytest.raises(ValueError, match="Non-numeric feature values.*feature_a"):
            InferenceServer._validate_features(
                {"feature_a": "not_a_number", "feature_b": 2.0},
                ["feature_a", "feature_b"],
                strict=True,
            )

    def test_non_numeric_value_nonstrict_logs_warning(self, caplog) -> None:
        """strict=False logs a warning for non-numeric values."""
        with caplog.at_level(logging.WARNING):
            InferenceServer._validate_features(
                {"feature_a": "bad", "feature_b": 2.0},
                ["feature_a", "feature_b"],
                strict=False,
            )
        assert "Non-numeric feature values" in caplog.text

    def test_none_value_strict_raises(self) -> None:
        """None is not numeric -- strict=True raises."""
        with pytest.raises(ValueError, match="Non-numeric"):
            InferenceServer._validate_features(
                {"a": None, "b": 2.0}, ["a", "b"], strict=True
            )

    def test_int_values_accepted(self) -> None:
        """Integer values are valid numeric input."""
        InferenceServer._validate_features({"a": 1, "b": 2}, ["a", "b"], strict=True)

    def test_bool_values_accepted(self) -> None:
        """Boolean values are valid (bool is subclass of int in Python)."""
        InferenceServer._validate_features(
            {"a": True, "b": False}, ["a", "b"], strict=True
        )

    def test_numpy_scalar_accepted(self) -> None:
        """numpy scalars are valid numeric input."""
        InferenceServer._validate_features(
            {"a": np.float64(1.5), "b": np.int32(3)}, ["a", "b"], strict=True
        )

    def test_string_numeric_accepted(self) -> None:
        """String that can be parsed as float is accepted (e.g. '1.5')."""
        InferenceServer._validate_features(
            {"a": "1.5", "b": 2.0}, ["a", "b"], strict=True
        )

    def test_record_index_in_error(self) -> None:
        """record_index is included in the error message for batch diagnostics."""
        with pytest.raises(ValueError, match="record index 3"):
            InferenceServer._validate_features(
                {"feature_a": 1.0},
                ["feature_a", "feature_b"],
                strict=True,
                record_index=3,
            )

    def test_empty_features_raises(self) -> None:
        """Empty feature dict with non-empty expected list raises."""
        with pytest.raises(ValueError, match="Missing required features"):
            InferenceServer._validate_features(
                {}, ["feature_a", "feature_b"], strict=True
            )

    def test_extra_features_ignored(self) -> None:
        """Extra features beyond expected are silently ignored (no error)."""
        InferenceServer._validate_features(
            {"a": 1.0, "b": 2.0, "extra": 3.0}, ["a", "b"], strict=True
        )

    def test_list_value_strict_raises(self) -> None:
        """List values are non-numeric."""
        with pytest.raises(ValueError, match="Non-numeric"):
            InferenceServer._validate_features(
                {"a": [1, 2, 3], "b": 2.0}, ["a", "b"], strict=True
            )


# ---------------------------------------------------------------------------
# _resolve_feature_names
# ---------------------------------------------------------------------------


class TestResolveFeatureNames:
    """Tests for feature name resolution from model signature."""

    def test_with_signature(self) -> None:
        sig = _make_signature("x", "y", "z")
        entry = _make_cached_entry(None, sig)
        names = InferenceServer._resolve_feature_names(entry, {"a": 1})
        assert names == ["x", "y", "z"]

    def test_without_signature_uses_feature_keys(self) -> None:
        entry = _CachedModel(
            model=None,
            onnx_session=None,
            version=1,
            name="test",
            signature=None,
            framework="sklearn",
            inference_path="native",
        )
        names = InferenceServer._resolve_feature_names(
            entry, {"col_a": 1.0, "col_b": 2.0}
        )
        assert names == ["col_a", "col_b"]


# ---------------------------------------------------------------------------
# predict() end-to-end (async, with mock registry)
# ---------------------------------------------------------------------------


class TestPredictStrict:
    """Test predict() with strict=True (default)."""

    @pytest.fixture
    def server(self) -> InferenceServer:
        model = _make_trained_model()
        sig = _make_signature("feature_a", "feature_b")
        return _make_server_with_model(model, sig)

    @pytest.mark.asyncio
    async def test_complete_features_succeeds(self, server) -> None:
        result = await server.predict(
            "test_model", {"feature_a": 1.0, "feature_b": 2.0}
        )
        assert isinstance(result, PredictionResult)
        assert result.prediction in (0, 1)
        assert result.model_name == "test_model"

    @pytest.mark.asyncio
    async def test_missing_feature_raises_valueerror(self, server) -> None:
        with pytest.raises(ValueError, match="Missing required features.*feature_b"):
            await server.predict("test_model", {"feature_a": 1.0})

    @pytest.mark.asyncio
    async def test_non_numeric_feature_raises_valueerror(self, server) -> None:
        with pytest.raises(ValueError, match="Non-numeric"):
            await server.predict("test_model", {"feature_a": "bad", "feature_b": 2.0})

    @pytest.mark.asyncio
    async def test_empty_features_raises_valueerror(self, server) -> None:
        with pytest.raises(ValueError, match="Missing required features"):
            await server.predict("test_model", {})


class TestPredictNonStrict:
    """Test predict() with strict=False (legacy behaviour)."""

    @pytest.fixture
    def server(self) -> InferenceServer:
        model = _make_trained_model()
        sig = _make_signature("feature_a", "feature_b")
        return _make_server_with_model(model, sig)

    @pytest.mark.asyncio
    async def test_missing_feature_falls_back_to_zero(self, server, caplog) -> None:
        """Missing feature produces a prediction (using 0.0 fallback)."""
        with caplog.at_level(logging.WARNING):
            result = await server.predict(
                "test_model", {"feature_a": 1.0}, strict=False
            )
        assert isinstance(result, PredictionResult)
        assert result.prediction in (0, 1)
        assert "Missing required features" in caplog.text

    @pytest.mark.asyncio
    async def test_complete_features_still_works(self, server) -> None:
        result = await server.predict(
            "test_model",
            {"feature_a": 1.0, "feature_b": 2.0},
            strict=False,
        )
        assert isinstance(result, PredictionResult)


# ---------------------------------------------------------------------------
# predict_batch() end-to-end
# ---------------------------------------------------------------------------


class TestPredictBatchStrict:
    """Test predict_batch() with strict=True (default)."""

    @pytest.fixture
    def server(self) -> InferenceServer:
        model = _make_trained_model()
        sig = _make_signature("feature_a", "feature_b")
        return _make_server_with_model(model, sig)

    @pytest.mark.asyncio
    async def test_complete_batch_succeeds(self, server) -> None:
        records = [
            {"feature_a": 1.0, "feature_b": 2.0},
            {"feature_a": 3.0, "feature_b": 4.0},
        ]
        results = await server.predict_batch("test_model", records)
        assert len(results) == 2
        for r in results:
            assert isinstance(r, PredictionResult)

    @pytest.mark.asyncio
    async def test_missing_feature_in_batch_raises(self, server) -> None:
        records = [
            {"feature_a": 1.0, "feature_b": 2.0},
            {"feature_a": 3.0},  # missing feature_b
        ]
        with pytest.raises(ValueError, match="record index 1"):
            await server.predict_batch("test_model", records)

    @pytest.mark.asyncio
    async def test_non_numeric_in_batch_raises(self, server) -> None:
        records = [
            {"feature_a": "bad", "feature_b": 2.0},
        ]
        with pytest.raises(ValueError, match="Non-numeric"):
            await server.predict_batch("test_model", records)

    @pytest.mark.asyncio
    async def test_empty_batch_returns_empty(self, server) -> None:
        results = await server.predict_batch("test_model", [])
        assert results == []


class TestPredictBatchNonStrict:
    """Test predict_batch() with strict=False."""

    @pytest.fixture
    def server(self) -> InferenceServer:
        model = _make_trained_model()
        sig = _make_signature("feature_a", "feature_b")
        return _make_server_with_model(model, sig)

    @pytest.mark.asyncio
    async def test_missing_feature_falls_back(self, server, caplog) -> None:
        records = [
            {"feature_a": 1.0},  # missing feature_b
            {"feature_a": 3.0, "feature_b": 4.0},
        ]
        with caplog.at_level(logging.WARNING):
            results = await server.predict_batch("test_model", records, strict=False)
        assert len(results) == 2
        assert "Missing required features" in caplog.text
