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

# Framework integrations — W23.b onwards. Each module registers its
# concrete integration class via @register_integration at module
# scope (orphan-detection.md §1 — production call site is the CM's
# auto-detect + explicit-name resolver). Framework imports live
# inside each module's attach()/flush() so importing this package
# does NOT pull sklearn / lightgbm / lightning into sys.modules.
from kailash_ml.autolog import _lightgbm  # noqa: F401 — registration side-effect
from kailash_ml.autolog import _lightning  # noqa: F401 — registration side-effect
from kailash_ml.autolog import _polars  # noqa: F401 — registration side-effect
from kailash_ml.autolog import _sklearn  # noqa: F401 — registration side-effect
from kailash_ml.autolog import _statsmodels  # noqa: F401 — registration side-effect
from kailash_ml.autolog import _transformers  # noqa: F401 — registration side-effect
from kailash_ml.autolog import _xgboost  # noqa: F401 — registration side-effect


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
