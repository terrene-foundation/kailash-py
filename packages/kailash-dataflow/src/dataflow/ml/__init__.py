# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DataFlow × kailash-ml integration bridge.

Ships in kailash-dataflow 2.1.0. Consumed by kailash-ml 1.0.0.

Public surface (per ``specs/dataflow-ml-integration.md`` § 1.1):

* :func:`ml_feature_source` — materialize a ``FeatureGroup`` as a
  ``polars.LazyFrame`` (§ 2).
* :func:`transform`          — apply a polars expression to a feature
  source with lineage + classification propagation (§ 3).
* :func:`hash`               — stable SHA-256 content fingerprint of a
  polars frame for lineage provenance (§ 4).
* :class:`TrainingContext`   — frozen dataclass carrying
  ``(run_id, tenant_id, dataset_hash, actor_id)``.
* :func:`on_train_start` / :func:`on_train_end` — DataFlow event bus
  subscribers for ML training lifecycle events.
* :func:`emit_train_start` / :func:`emit_train_end` — helpers for
  kailash-ml training engines to publish the same events.

Error hierarchy (§ 5): all errors inherit from
:class:`dataflow.exceptions.DataFlowError` so existing ``except
DataFlowError`` callers continue to work.

Cross-SDK parity (§ 7): ``ml_feature_source`` / ``transform`` / ``hash``
mirror the kailash-rs ``dataflow::ml_feature_source`` / ``transform`` /
``hash`` surfaces; the SHA-256 lineage hash is byte-identical for the
same canonicalized polars Arrow IPC stream across languages.
"""

from __future__ import annotations

from dataflow.ml._classify import _kml_classify_actions
from dataflow.ml._context import TrainingContext
from dataflow.ml._errors import (
    DataFlowMLIntegrationError,
    DataFlowTransformError,
    FeatureSourceError,
    LineageHashError,
    MLTenantRequiredError,
)
from dataflow.ml._events import (
    ML_TRAIN_END_EVENT,
    ML_TRAIN_START_EVENT,
    emit_train_end,
    emit_train_start,
    on_train_end,
    on_train_start,
)
from dataflow.ml._feature_source import build_cache_key, ml_feature_source
from dataflow.ml._hash import hash
from dataflow.ml._transform import transform

__all__ = [
    # Primary surface
    "ml_feature_source",
    "transform",
    "hash",
    "TrainingContext",
    # Event surface
    "ML_TRAIN_START_EVENT",
    "ML_TRAIN_END_EVENT",
    "emit_train_start",
    "emit_train_end",
    "on_train_start",
    "on_train_end",
    # Classification bridge (internal; prefixed with _kml_)
    "_kml_classify_actions",
    # Cache key helper (exposed for tenant-scoped invalidation callers)
    "build_cache_key",
    # Error taxonomy
    "DataFlowMLIntegrationError",
    "FeatureSourceError",
    "DataFlowTransformError",
    "LineageHashError",
    "MLTenantRequiredError",
]
