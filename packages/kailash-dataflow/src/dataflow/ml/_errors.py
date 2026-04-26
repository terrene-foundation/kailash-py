# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Error taxonomy for the DataFlow × kailash-ml bridge.

All ML-bridge errors inherit from :class:`DataFlowError` so existing
``except DataFlowError`` handlers continue to work for callers upgrading
to 2.1.0. See ``specs/dataflow-ml-integration.md`` § 5.
"""

from __future__ import annotations

import warnings

from dataflow.exceptions import DataFlowError

__all__ = [
    "DataFlowMLIntegrationError",
    "FeatureSourceError",
    "DataFlowTransformError",
    "LineageHashError",
    "TenantRequiredError",
    # ``MLTenantRequiredError`` is an intentional back-compat alias —
    # see :func:`__getattr__` below. It is intentionally absent from
    # ``__all__`` so ``from dataflow.ml._errors import *`` only picks up
    # the canonical name, but ``from dataflow.ml._errors import
    # MLTenantRequiredError`` still resolves (with a DeprecationWarning).
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


class TenantRequiredError(DataFlowMLIntegrationError):
    """Raised when a multi_tenant=True feature group is accessed without
    a ``tenant_id``.

    This is the ML-bridge-specific sibling of
    :class:`dataflow.core.multi_tenancy.TenantRequiredError` — raising it
    keeps the ML-bridge's error hierarchy self-contained while
    preserving the ``rules/tenant-isolation.md`` § 2 contract (missing
    tenant is a typed error, never a silent default).

    .. note::
       Renamed from ``MLTenantRequiredError`` in kailash-dataflow 2.3.2
       to match ``specs/dataflow-ml-integration.md`` § 5 canonical name.
       The old name remains as a deprecated back-compat alias slated for
       removal in v3.0; access emits a ``DeprecationWarning`` once per
       process. Closes finding F-B-23.
    """


def __getattr__(name: str):
    """Module-level ``__getattr__`` for the deprecated alias.

    The ``MLTenantRequiredError`` alias resolves to
    :class:`TenantRequiredError` and emits a ``DeprecationWarning`` on
    first access per process. Any other unknown attribute raises
    ``AttributeError`` so the alias does NOT silently mask typos.
    """
    if name == "MLTenantRequiredError":
        warnings.warn(
            "MLTenantRequiredError is deprecated; use TenantRequiredError. "
            "Alias will be removed in kailash-dataflow v3.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return TenantRequiredError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
