# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash-ml 1.0.0 features package — polars-native, DataFlow-integrated.

Public surface of the 1.0.0 FeatureStore primitive lives here. Legacy
``kailash_ml.engines.feature_store`` remains untouched for 0.x callers.

See ``specs/ml-feature-store.md`` + ``specs/dataflow-ml-integration.md §1.1``.
"""
from __future__ import annotations

from kailash_ml.features.cache_keys import (
    CANONICAL_SINGLE_TENANT_SENTINEL,
    make_feature_cache_key,
    make_feature_group_wildcard,
)
from kailash_ml.features.schema import FeatureField, FeatureSchema
from kailash_ml.features.store import FeatureStore

__all__ = [
    "CANONICAL_SINGLE_TENANT_SENTINEL",
    "FeatureField",
    "FeatureSchema",
    "FeatureStore",
    "make_feature_cache_key",
    "make_feature_group_wildcard",
]
