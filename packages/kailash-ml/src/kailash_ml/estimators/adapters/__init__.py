# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Lightning adapter surface — W9.

Per `specs/ml-engines-v2.md §3.2 MUST 1-5` + `addendum §E3-§E5`, every
non-RL family MUST fit through a ``L.Trainer`` — no family-specific
dispatch at the engine layer. This package exposes thin Lightning
wrappers for the four first-class tabular / gradient-boosting families:

    SklearnLightningAdapter    — wraps kailash_ml.trainable.SklearnTrainable
    XGBoostLightningAdapter    — wraps kailash_ml.trainable.XGBoostTrainable
    LightGBMLightningAdapter   — wraps kailash_ml.trainable.LightGBMTrainable
    CatBoostLightningAdapter   — minimal CatBoost Lightning wrapper

Each adapter inherits from :class:`LightningAdapterBase`, which enforces
the cross-family invariants in ONE place so the 4 sibling files cannot
drift (per analyst FP-MED-5):

* NaN / Inf hyperparameters raise :class:`ParamValueError` at
  construction time (W9 invariant 6).
* ``family_name: str`` class attribute is mandatory (W9 invariant 7).
* ``to_lightning_module()`` returns a real LightningModule, never a
  mock or a stub (W9 invariant 1 — Decision 8 carve-out applies only to
  RL families, NOT tabular).

The adapters are a forward-facing surface; downstream callers (MLEngine,
km.train) MAY import from here to get the Lightning-routed form without
having to know the legacy ``Trainable`` class names. Legacy imports
(``from kailash_ml.trainable import SklearnTrainable``) continue to work.
"""
from __future__ import annotations

from kailash_ml.estimators.adapters._base import (
    LightningAdapterBase,
    validate_hyperparameters,
)
from kailash_ml.estimators.adapters.catboost_adapter import CatBoostLightningAdapter
from kailash_ml.estimators.adapters.lightgbm_adapter import LightGBMLightningAdapter
from kailash_ml.estimators.adapters.sklearn_adapter import SklearnLightningAdapter
from kailash_ml.estimators.adapters.xgboost_adapter import XGBoostLightningAdapter

__all__ = [
    "LightningAdapterBase",
    "validate_hyperparameters",
    "SklearnLightningAdapter",
    "XGBoostLightningAdapter",
    "LightGBMLightningAdapter",
    "CatBoostLightningAdapter",
]
