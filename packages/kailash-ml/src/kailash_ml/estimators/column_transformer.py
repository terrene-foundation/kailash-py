# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""kailash_ml.ColumnTransformer — sklearn.ColumnTransformer with registered-estimator support."""
from __future__ import annotations

from typing import Any, List, Tuple

from sklearn.compose import ColumnTransformer as _SKColumnTransformer

from kailash_ml.estimators._protocol import check_transformer_step

__all__ = ["ColumnTransformer"]

# sklearn sentinels that bypass the transformer protocol check entirely.
_PASSTHROUGH = {"passthrough", "drop"}


class ColumnTransformer(_SKColumnTransformer):
    """``sklearn.compose.ColumnTransformer`` that accepts registered custom
    transformers on each column subset.
    """

    def __init__(
        self,
        transformers: List[Tuple[str, Any, Any]],
        *,
        remainder: Any = "drop",
        sparse_threshold: float = 0.3,
        n_jobs: Any = None,
        transformer_weights: Any = None,
        verbose: bool = False,
        verbose_feature_names_out: bool = True,
    ) -> None:
        if not isinstance(transformers, list) or not transformers:
            raise TypeError(
                "ColumnTransformer requires a non-empty list of "
                "(name, transformer, columns) tuples"
            )
        for idx, entry in enumerate(transformers):
            if not (isinstance(entry, tuple) and len(entry) == 3):
                raise TypeError(
                    f"ColumnTransformer entry {idx} must be a "
                    "(name, transformer, columns) tuple"
                )
            name, step, _cols = entry
            if not isinstance(name, str) or not name:
                raise TypeError(
                    f"ColumnTransformer entry {idx} name must be a non-empty str"
                )
            if isinstance(step, str) and step in _PASSTHROUGH:
                continue
            check_transformer_step(name, step)
        super().__init__(
            transformers=transformers,
            remainder=remainder,
            sparse_threshold=sparse_threshold,
            n_jobs=n_jobs,
            transformer_weights=transformer_weights,
            verbose=verbose,
            verbose_feature_names_out=verbose_feature_names_out,
        )
