# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""XGBoost Lightning adapter — W9.

Thin Lightning-routed wrapper over the existing
:class:`kailash_ml.trainable.XGBoostTrainable`. Adds the W9
construction-time NaN/Inf hyperparameter validation and the consistent
``*LightningAdapter`` naming.
"""
from __future__ import annotations

from typing import Any, Mapping

from kailash_ml.estimators.adapters._base import validate_hyperparameters
from kailash_ml.trainable import XGBoostTrainable

__all__ = ["XGBoostLightningAdapter"]


class XGBoostLightningAdapter(XGBoostTrainable):
    """XGBoost Lightning-routed adapter (W9 family=xgboost)."""

    family_name = "xgboost"

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
