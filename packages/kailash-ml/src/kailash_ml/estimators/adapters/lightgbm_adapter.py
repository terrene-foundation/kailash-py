# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""LightGBM Lightning adapter — W9.

Thin Lightning-routed wrapper over the existing
:class:`kailash_ml.trainable.LightGBMTrainable`. Adds the W9
construction-time NaN/Inf hyperparameter validation and the consistent
``*LightningAdapter`` naming.
"""
from __future__ import annotations

from typing import Any, Mapping

from kailash_ml.estimators.adapters._base import validate_hyperparameters
from kailash_ml.trainable import LightGBMTrainable

__all__ = ["LightGBMLightningAdapter"]


class LightGBMLightningAdapter(LightGBMTrainable):
    """LightGBM Lightning-routed adapter (W9 family=lightgbm)."""

    family_name = "lightgbm"

    def __init__(
        self,
        estimator: Any = None,
        *,
        hyperparameters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        validated = validate_hyperparameters(hyperparameters, family=self.family_name)
        super().__init__(estimator=estimator, **kwargs)
        self._w9_hyperparameters = validated
