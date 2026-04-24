# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Sklearn Lightning adapter — W9.

Thin Lightning-routed wrapper over the existing
:class:`kailash_ml.trainable.SklearnTrainable`. The legacy class
continues to work; this adapter adds the W9 construction-time
NaN/Inf hyperparameter validation (shared via :mod:`_base`) and
re-exports the same surface under the consistent ``*LightningAdapter``
naming used by the MLEngine routing layer.

All fit paths ultimately route through ``L.Trainer`` via the parent
SklearnTrainable's ``to_lightning_module()`` method.
"""
from __future__ import annotations

from typing import Any, Mapping

from kailash_ml.estimators.adapters._base import validate_hyperparameters
from kailash_ml.trainable import SklearnTrainable

__all__ = ["SklearnLightningAdapter"]


class SklearnLightningAdapter(SklearnTrainable):
    """Sklearn Lightning-routed adapter (W9 family=sklearn).

    Hyperparameters supplied at construction time are validated for
    NaN/Inf (raises :class:`ParamValueError`) per W9 invariant 6. The
    validated dict is stashed on ``self._w9_hyperparameters`` for
    downstream use by the engine routing layer and can be passed to
    :meth:`fit` via the ``hyperparameters=`` keyword argument.
    """

    family_name = "sklearn"

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
