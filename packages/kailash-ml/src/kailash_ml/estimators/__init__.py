# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""sklearn-compatible Pipeline / FeatureUnion / ColumnTransformer primitives
with an explicit ``register_estimator()`` registry for custom estimators.

Resolves kailash-py#479 and kailash-py#488 (cross-SDK alignment with
kailash-rs#402 commit ``5429928c``). Built-in ``sklearn`` estimators are
accepted unconditionally; any other class MUST be explicitly registered
via ``register_estimator`` before it can participate in a composite
pipeline. This preserves the Foundation's agent-reasoning principle of
"explicit intent, no duck-type allowlist opening".

Public surface:

.. code-block:: python

    import kailash_ml as kml

    @kml.register_estimator
    class MyCustomHead:
        def fit(self, X, y=None): return self
        def predict(self, X): return X
        def transform(self, X): return X

    pipe = kml.Pipeline([
        ("scaler", kml.StandardScaler()),
        ("head", MyCustomHead()),
    ])
"""
from __future__ import annotations

from kailash_ml.estimators.column_transformer import ColumnTransformer
from kailash_ml.estimators.feature_union import FeatureUnion
from kailash_ml.estimators.pipeline import Pipeline
from kailash_ml.estimators.registry import (
    is_registered_estimator,
    register_estimator,
    registered_estimators,
    unregister_estimator,
)

# Re-export the stock sklearn primitives that tests and users routinely
# compose with registered custom estimators. Importing from kailash_ml
# gives a single canonical name — users don't have to remember that
# ``StandardScaler`` is sklearn-native.
from sklearn.preprocessing import StandardScaler

__all__ = [
    "ColumnTransformer",
    "FeatureUnion",
    "Pipeline",
    "StandardScaler",
    "is_registered_estimator",
    "register_estimator",
    "registered_estimators",
    "unregister_estimator",
]
