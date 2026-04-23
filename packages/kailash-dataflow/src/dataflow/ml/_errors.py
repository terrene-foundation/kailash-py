# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Error taxonomy for the DataFlow × kailash-ml bridge.

All ML-bridge errors inherit from :class:`DataFlowError` so existing
``except DataFlowError`` handlers continue to work for callers upgrading
to 2.1.0. See ``specs/dataflow-ml-integration.md`` § 5.
"""

from __future__ import annotations

from dataflow.exceptions import DataFlowError

__all__ = [
    "DataFlowMLIntegrationError",
    "FeatureSourceError",
    "DataFlowTransformError",
    "LineageHashError",
    "MLTenantRequiredError",
]


class DataFlowMLIntegrationError(DataFlowError):
    """Base for every error raised from ``dataflow.ml``.

    Subclasses distinguish the three ML-bridge entry points
    (``ml_feature_source`` / ``transform`` / ``hash``). Callers that only
    need to catch any ML-bridge failure use this base class.
    """


class FeatureSourceError(DataFlowMLIntegrationError):
    """Raised when ``ml_feature_source`` cannot materialize a feature group.

    Typical causes:

    * ``kailash-ml`` is not installed (spec § 2.2).
    * The feature group's backing table does not exist.
    * Schema mismatch between the declared feature group and the
      persisted rows.
    """


class DataFlowTransformError(DataFlowMLIntegrationError):
    """Raised when ``dataflow.transform`` cannot apply the polars expression.

    Typical causes:

    * The expression references a column absent from the source.
    * Type mismatch between the expression's expected inputs and the
      source schema.
    * Tenant mismatch: the source and the caller's tenant differ.
    """


class LineageHashError(DataFlowMLIntegrationError):
    """Raised when ``dataflow.hash`` cannot produce a stable hash.

    Typical causes:

    * The frame contains a cell whose polars dtype is not hashable in
      the canonical form (e.g. object-typed Python dicts with unordered
      keys).
    * Unsupported canonicalization request.
    """


class MLTenantRequiredError(DataFlowMLIntegrationError):
    """Raised when a multi_tenant=True feature group is accessed without
    a ``tenant_id``.

    This is the ML-bridge-specific sibling of
    :class:`dataflow.core.multi_tenancy.TenantRequiredError` — raising it
    keeps the ML-bridge's error hierarchy self-contained while
    preserving the ``rules/tenant-isolation.md`` § 2 contract (missing
    tenant is a typed error, never a silent default).
    """
