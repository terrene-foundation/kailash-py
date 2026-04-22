# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Framework autolog — auto-instrumentation for ML / DL training loops.

Implements ``specs/ml-autolog.md`` — a single ``km.autolog()`` entry
point that auto-logs metrics, params, artifacts, and models from
popular ML / DL frameworks into the ambient ``km.track()`` run. See
the spec for the full design; this docstring is the public API index.

Public surface (eager per ``rules/orphan-detection.md §6`` — every
``__all__`` entry is resolvable via module-scope import, never lazy
``__getattr__``)::

    from kailash_ml.autolog import (
        autolog,               # async context manager (primary)
        autolog_fn,            # decorator form
        AutologConfig,         # frozen config dataclass
        AutologHandle,         # yielded runtime handle
        FrameworkIntegration,  # ABC for W23.b-d integrations
        register_integration,  # third-party registration API
        unregister_integration,
    )

W23.a (this module) ships the scaffolding only — no concrete framework
integrations. Framework-specific hooks (sklearn, lightgbm, Lightning,
transformers, xgboost, statsmodels, polars) land in W23.b-d per the
wave plan at
``workspaces/kailash-ml-audit/todos/active/W23-autolog.md``.
"""
from __future__ import annotations

from kailash_ml.autolog._context import autolog, autolog_fn
from kailash_ml.autolog._registry import (
    FrameworkIntegration,
    register_integration,
    registered_integration_names,
    unregister_integration,
)
from kailash_ml.autolog.config import AutologConfig, AutologHandle


__all__ = [
    "AutologConfig",
    "AutologHandle",
    "FrameworkIntegration",
    "autolog",
    "autolog_fn",
    "register_integration",
    "registered_integration_names",
    "unregister_integration",
]
