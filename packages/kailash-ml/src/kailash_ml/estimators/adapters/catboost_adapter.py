# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""CatBoost Lightning adapter — W9.

Per ``pyproject.toml`` the catboost integration ships as an optional
extra (``catboost = ["catboost>=1.2"]``). This adapter follows
``rules/dependencies.md`` § "Optional Extras with Loud Failure":
importing it when the extra is missing raises :class:`ImportError`
with an actionable message naming the extra.

When catboost IS installed, the adapter wraps the CatBoost learner
in a Lightning-routed shim so the ``L.Trainer`` fit path applies
uniformly across the four W9 families (per W9 invariant 1).

The implementation is intentionally minimal (DoD item 4 requires
construction-time NaN/Inf validation + family_name + pickle round-trip).
Full single-epoch Lightning training-step routing for CatBoost lives
in a follow-up shard tracked against ``ml-engines-v2-addendum §E5``.
"""
from __future__ import annotations

from typing import Any, Mapping

from kailash_ml.errors import UnsupportedTrainerError
from kailash_ml.estimators.adapters._base import validate_hyperparameters

try:  # optional extra per dependencies.md
    import catboost as _catboost  # type: ignore[import]
except ImportError:  # pragma: no cover — exercised only without the extra
    _catboost = None

__all__ = ["CatBoostLightningAdapter"]


class CatBoostLightningAdapter:
    """CatBoost Lightning-routed adapter (W9 family=catboost).

    Construction requires the ``catboost`` extra. Hyperparameters are
    validated for NaN/Inf per W9 invariant 6.

    See ``pyproject.toml`` extras: ``pip install kailash-ml[catboost]``.
    """

    family_name = "catboost"

    def __init__(
        self,
        estimator: Any = None,
        *,
        task: str = "classification",
        target: str = "target",
        hyperparameters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if _catboost is None:
            raise ImportError(
                "CatBoostLightningAdapter requires the [catboost] extra: "
                "pip install kailash-ml[catboost]"
            )
        self._hyperparameters = validate_hyperparameters(
            hyperparameters, family=self.family_name
        )
        if estimator is None:
            defaults = {
                "iterations": 20,
                "depth": 3,
                "random_seed": 42,
                "verbose": False,
            }
            defaults.update(kwargs)
            if task == "classification":
                estimator = _catboost.CatBoostClassifier(**defaults)
            else:
                estimator = _catboost.CatBoostRegressor(**defaults)
        self._estimator = estimator
        self._task = task
        self._target = target
        self._is_fitted = False

    def to_lightning_module(self) -> Any:
        """Return the Lightning-routed single-epoch module.

        CatBoost's iterative boosting loop is wrapped in a Lightning
        ``LightningModule`` by the engine-side routing layer; calling
        this method before :meth:`fit` or without Lightning installed
        raises :class:`UnsupportedTrainerError` with the guidance from
        Decision 8.
        """
        raise UnsupportedTrainerError(
            "CatBoostLightningAdapter.to_lightning_module() requires a "
            "Lightning-routed fit call; use MLEngine.fit(trainable=...) "
            "rather than instantiating the module directly. "
            "Raw training loops are BLOCKED per Decision 8."
        )

    def get_param_distribution(self) -> dict[str, Any]:
        """Return an empty hyperparameter search space.

        The default CatBoost adapter does not expose a curated HP space;
        users can override by subclassing or by passing explicit
        ``hyperparameters=`` to :class:`AutoMLEngine`.
        """
        return {}

    # ------------------------------------------------------------------
    # Pickle support (W9 Tier-1 DoD)
    # ------------------------------------------------------------------

    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        return state

    def __setstate__(self, state: Mapping[str, Any]) -> None:
        self.__dict__.update(state)
