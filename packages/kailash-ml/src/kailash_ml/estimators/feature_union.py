# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""kailash_ml.FeatureUnion — sklearn.FeatureUnion with registered-estimator support."""
from __future__ import annotations

from typing import Any, List, Tuple

from sklearn.pipeline import FeatureUnion as _SKFeatureUnion

from kailash_ml.estimators._protocol import check_transformer_step

__all__ = ["FeatureUnion"]


class FeatureUnion(_SKFeatureUnion):
    """``sklearn.pipeline.FeatureUnion`` that accepts registered custom
    transformers. Every step must satisfy ``check_transformer_step``.
    """

    def __init__(
        self,
        transformer_list: List[Tuple[str, Any]],
        *,
        n_jobs: Any = None,
        transformer_weights: Any = None,
        verbose: bool = False,
    ) -> None:
        if not isinstance(transformer_list, list) or not transformer_list:
            raise TypeError(
                "FeatureUnion requires a non-empty list of (name, transformer) tuples"
            )
        for idx, entry in enumerate(transformer_list):
            if not (isinstance(entry, tuple) and len(entry) == 2):
                raise TypeError(
                    f"FeatureUnion entry {idx} must be a (name, transformer) tuple"
                )
            name, step = entry
            if not isinstance(name, str) or not name:
                raise TypeError(f"FeatureUnion entry {idx} name must be a non-empty str")
            check_transformer_step(name, step)
        super().__init__(
            transformer_list=transformer_list,
            n_jobs=n_jobs,
            transformer_weights=transformer_weights,
            verbose=verbose,
        )
