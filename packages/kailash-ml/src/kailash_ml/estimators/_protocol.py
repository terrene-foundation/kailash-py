# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared duck-typed protocol checks for composite steps.

Each of ``Pipeline``, ``FeatureUnion``, and ``ColumnTransformer`` accepts
either a built-in sklearn estimator OR a class registered via
``register_estimator``. The validation below is the single place that
decides "is this step legal?" so the three composites share identical
semantics and error surface.
"""
from __future__ import annotations

from typing import Any

from kailash_ml.estimators.registry import is_registered_estimator

__all__ = ["check_estimator_step", "check_transformer_step"]


def _is_sklearn_native(obj: Any) -> bool:
    cls = obj if isinstance(obj, type) else type(obj)
    module = getattr(cls, "__module__", "") or ""
    return module.startswith("sklearn.") or module == "sklearn"


def _has_transformer_protocol(obj: Any) -> bool:
    return callable(getattr(obj, "fit", None)) and callable(
        getattr(obj, "transform", None)
    )


def _has_estimator_protocol(obj: Any) -> bool:
    return callable(getattr(obj, "fit", None)) and (
        callable(getattr(obj, "predict", None))
        or callable(getattr(obj, "transform", None))
    )


def check_transformer_step(name: str, step: Any) -> None:
    """Raise ``TypeError`` if ``step`` is not a legal transformer step.

    Legal if (a) sklearn-native, OR (b) registered via
    ``register_estimator`` AND duck-typed with ``fit`` + ``transform``.
    """
    if _is_sklearn_native(step):
        return
    if is_registered_estimator(step):
        if not _has_transformer_protocol(step):
            raise TypeError(
                f"step {name!r}: registered class "
                f"{type(step).__qualname__!r} lacks fit/transform"
            )
        return
    raise TypeError(
        f"step {name!r}: class {type(step).__qualname__!r} is not a "
        "registered estimator. Use kailash_ml.register_estimator(cls) "
        "or @kailash_ml.register_estimator as a decorator to register it."
    )


def check_estimator_step(name: str, step: Any) -> None:
    """Raise ``TypeError`` if ``step`` is not a legal pipeline final step.

    Final steps of a ``Pipeline`` need either ``predict`` OR ``transform``.
    """
    if _is_sklearn_native(step):
        return
    if is_registered_estimator(step):
        if not _has_estimator_protocol(step):
            raise TypeError(
                f"step {name!r}: registered class "
                f"{type(step).__qualname__!r} lacks fit + predict/transform"
            )
        return
    raise TypeError(
        f"step {name!r}: class {type(step).__qualname__!r} is not a "
        "registered estimator. Use kailash_ml.register_estimator(cls) "
        "or @kailash_ml.register_estimator as a decorator to register it."
    )
