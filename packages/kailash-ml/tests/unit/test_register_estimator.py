# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for kailash_ml.register_estimator + composites (#479 #488).

Ports the 6 regression tests from kailash-rs
``bindings/kailash-python/tests/regression/test_issue_402_custom_estimators.py``.
"""
from __future__ import annotations

import numpy as np
import pytest
from sklearn.base import BaseEstimator, TransformerMixin

import kailash_ml as kml


class _BocpdStub(BaseEstimator):
    """Sklearn-shaped custom head for the regression-suite tests.

    Inherits BaseEstimator so sklearn >=1.6 `__sklearn_tags__` resolution
    works inside Pipeline/FeatureUnion fit/predict. The *validation* that
    kailash_ml performs does NOT require BaseEstimator inheritance — it
    only requires registration + the duck-typed protocol — but sklearn
    itself now requires __sklearn_tags__ for all Pipeline tail steps.
    """

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def fit(self, X, y=None):
        self.is_fitted_ = True  # sklearn convention: trailing _ = fitted state
        return self

    def predict(self, X):
        return np.zeros(np.asarray(X).shape[0])

    def transform(self, X):
        return np.asarray(X)


class _SquareTransformer(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        self.is_fitted_ = True
        return self

    def transform(self, X):
        return np.asarray(X) ** 2


# ---------------------------------------------------------------------------
# Registry behavior
# ---------------------------------------------------------------------------


def test_unregistered_class_rejected_with_named_error():
    class _Unregistered:
        def fit(self, X, y=None):
            return self

        def predict(self, X):
            return X

    with pytest.raises(TypeError, match="_Unregistered") as exc:
        kml.Pipeline([("head", _Unregistered())])
    assert "register_estimator" in str(exc.value)


def test_register_as_function_then_compose():
    kml.register_estimator(_BocpdStub)
    try:
        pipe = kml.Pipeline(
            [("scaler", kml.StandardScaler()), ("bocpd", _BocpdStub(threshold=0.7))]
        )
        assert pipe.steps[-1][0] == "bocpd"
    finally:
        kml.unregister_estimator(_BocpdStub)


def test_register_as_decorator():
    @kml.register_estimator
    class _RegDec:
        def fit(self, X, y=None):
            return self

        def predict(self, X):
            return X

    try:
        pipe = kml.Pipeline([("head", _RegDec())])
        assert pipe.steps[0][0] == "head"
    finally:
        kml.unregister_estimator(_RegDec)


def test_unregister_round_trip():
    kml.register_estimator(_BocpdStub)
    assert kml.is_registered_estimator(_BocpdStub) is True
    removed = kml.unregister_estimator(_BocpdStub)
    assert removed is True
    assert kml.is_registered_estimator(_BocpdStub) is False
    with pytest.raises(TypeError, match="_BocpdStub"):
        kml.Pipeline([("head", _BocpdStub())])


def test_register_idempotent():
    kml.register_estimator(_BocpdStub)
    kml.register_estimator(_BocpdStub)
    assert _BocpdStub in kml.registered_estimators()
    kml.unregister_estimator(_BocpdStub)


def test_register_rejects_instance():
    with pytest.raises(TypeError, match="expects a class"):
        kml.register_estimator(_BocpdStub())


# ---------------------------------------------------------------------------
# Pipeline / FeatureUnion / ColumnTransformer acceptance
# ---------------------------------------------------------------------------


def test_pipeline_with_registered_final_step_fits_and_predicts():
    kml.register_estimator(_BocpdStub)
    try:
        pipe = kml.Pipeline([("scaler", kml.StandardScaler()), ("bocpd", _BocpdStub())])
        X = np.array([[1.0], [2.0], [3.0]])
        pipe.fit(X)
        out = pipe.predict(X)
        assert out.shape == (3,)
    finally:
        kml.unregister_estimator(_BocpdStub)


def test_feature_union_with_registered_transformer():
    kml.register_estimator(_SquareTransformer)
    try:
        union = kml.FeatureUnion(
            [("sq", _SquareTransformer()), ("scaler", kml.StandardScaler())]
        )
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        out = union.fit_transform(X)
        assert out.shape[0] == 3
    finally:
        kml.unregister_estimator(_SquareTransformer)


def test_column_transformer_with_registered_transformer():
    kml.register_estimator(_SquareTransformer)
    try:
        ct = kml.ColumnTransformer(
            [
                ("sq", _SquareTransformer(), [0]),
                ("scaler", kml.StandardScaler(), [1]),
            ]
        )
        X = np.array([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]])
        out = ct.fit_transform(X)
        assert out.shape[0] == 3
    finally:
        kml.unregister_estimator(_SquareTransformer)


def test_column_transformer_passthrough_bypasses_registration():
    ct = kml.ColumnTransformer(
        [("keep", "passthrough", [0]), ("scaler", kml.StandardScaler(), [1])]
    )
    X = np.array([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]])
    out = ct.fit_transform(X)
    assert out.shape[0] == 3


# ---------------------------------------------------------------------------
# Validator surface
# ---------------------------------------------------------------------------


def test_pipeline_rejects_non_list_steps():
    with pytest.raises(TypeError, match="non-empty list"):
        kml.Pipeline([])


def test_feature_union_rejects_malformed_entry():
    with pytest.raises(TypeError, match="must be a .name, transformer. tuple"):
        kml.FeatureUnion([("only-one",)])  # type: ignore[list-item]


def test_column_transformer_rejects_malformed_entry():
    with pytest.raises(TypeError, match="must be a"):
        kml.ColumnTransformer([("two-elem", kml.StandardScaler())])  # type: ignore[list-item]


def test_registered_class_missing_protocol_still_rejected():
    class _Empty:
        pass

    kml.register_estimator(_Empty)
    try:
        with pytest.raises(TypeError, match="lacks"):
            kml.Pipeline([("head", _Empty())])
    finally:
        kml.unregister_estimator(_Empty)
