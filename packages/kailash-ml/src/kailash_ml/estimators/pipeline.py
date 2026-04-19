# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""kailash_ml.Pipeline — sklearn.Pipeline with registered-estimator support.

This is a thin wrapper around ``sklearn.pipeline.Pipeline`` that enforces
the kailash-ml "explicit registration" rule: every non-sklearn step MUST
be registered via ``register_estimator`` before it can participate in a
pipeline. The rule preserves explicit-intent (per `rules/agent-reasoning.md`)
while still permitting domain-specific heads (BOCPD, HRP, regime classifiers)
to compose with framework primitives like ``StandardScaler``.
"""
from __future__ import annotations

from typing import Any, List, Tuple

from sklearn.pipeline import Pipeline as _SKPipeline

from kailash_ml.estimators._protocol import (
    check_estimator_step,
    check_transformer_step,
)

__all__ = ["Pipeline"]


class Pipeline(_SKPipeline):
    """``sklearn.pipeline.Pipeline`` that accepts registered custom estimators.

    Every non-final step must satisfy ``check_transformer_step``; the final
    step must satisfy ``check_estimator_step``. Both checks accept sklearn
    natives unconditionally and accept any class registered via
    ``register_estimator`` that implements the duck-typed protocol.
    """

    def __init__(
        self, steps: List[Tuple[str, Any]], *, memory: Any = None, verbose: bool = False
    ) -> None:
        if not isinstance(steps, list) or not steps:
            raise TypeError(
                "Pipeline requires a non-empty list of (name, estimator) tuples"
            )
        for idx, entry in enumerate(steps):
            if not (isinstance(entry, tuple) and len(entry) == 2):
                raise TypeError(
                    f"Pipeline step {idx} must be a (name, estimator) tuple"
                )
            name, step = entry
            if not isinstance(name, str) or not name:
                raise TypeError(f"Pipeline step {idx} name must be a non-empty str")
            if idx < len(steps) - 1:
                check_transformer_step(name, step)
            else:
                check_estimator_step(name, step)
        super().__init__(steps=steps, memory=memory, verbose=verbose)
