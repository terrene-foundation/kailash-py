# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PreprocessingPipeline -- automatic data preprocessing for ML workflows.

PyCaret equivalent: ``setup()``.  Auto-detects task type, encodes categoricals,
scales numerics, imputes missing values, and splits train/test.

All data handling uses polars internally; conversion to numpy/sklearn happens
at the sklearn boundary via ``interop.py``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)

__all__ = [
    "PreprocessingPipeline",
    "SetupResult",
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SetupResult:
    """Result of ``PreprocessingPipeline.setup()``.

    Contains the transformed train/test splits, detected column metadata,
    fitted transformer objects (for later ``transform`` / ``inverse_transform``),
    and a human-readable summary.
    """

    train_data: pl.DataFrame
    test_data: pl.DataFrame
    target_column: str
    task_type: str  # "classification" or "regression"
    numeric_columns: list[str]
    categorical_columns: list[str]
    transformers: dict[str, Any]  # fitted sklearn transformers
    original_shape: tuple[int, int]
    transformed_shape: tuple[int, int]
    summary: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _detect_task_type(series: pl.Series) -> str:
    """Detect whether a target column represents classification or regression.

    Classification is inferred when the column is boolean, categorical,
    string, or numeric with 20 or fewer unique non-null values.
    """
    dtype = series.dtype
    if dtype in (pl.Boolean, pl.Categorical, pl.Utf8, pl.String):
        return "classification"
    n_unique = series.drop_nulls().n_unique()
    if n_unique <= 20:
        return "classification"
    return "regression"


def _identify_column_types(
    data: pl.DataFrame, target: str
) -> tuple[list[str], list[str]]:
    """Partition feature columns into numeric and categorical lists."""
    from kailash_ml.engines._shared import NUMERIC_DTYPES as _NUMERIC_DTYPES

    numeric: list[str] = []
    categorical: list[str] = []
    for col in data.columns:
        if col == target:
            continue
        if data[col].dtype in _NUMERIC_DTYPES:
            numeric.append(col)
        elif data[col].dtype in (
            pl.Boolean,
            pl.Categorical,
            pl.Utf8,
            pl.String,
        ):
            categorical.append(col)
        # Other dtypes (Date, Datetime, etc.) are skipped -- users should
        # pre-process them via FeatureEngineer.
    return numeric, categorical


# ---------------------------------------------------------------------------
# PreprocessingPipeline
# ---------------------------------------------------------------------------


class PreprocessingPipeline:
    """[P1: Production with Caveats] Automatic data preprocessing pipeline.

    PyCaret equivalent: ``setup()``.  Auto-detects task type, encodes
    categoricals, scales numerics, imputes missing values, and splits
    train/test.

    Usage::

        pipeline = PreprocessingPipeline()
        result = pipeline.setup(data, target="price", normalize=True)
        # result.train_data, result.test_data are ready for model training

        # At inference time:
        new_transformed = pipeline.transform(new_data)
    """

    def __init__(self) -> None:
        self._fitted: bool = False
        self._config: dict[str, Any] = {}
        # Fitted transformers -- keyed by purpose
        self._transformers: dict[str, Any] = {}
        # Column metadata from setup
        self._numeric_columns: list[str] = []
        self._categorical_columns: list[str] = []
        self._target_column: str = ""
        self._task_type: str = ""
        self._encoding: str = ""
        self._normalize: bool = False
        self._normalize_method: str = "zscore"
        self._imputation_strategy: str = ""
        self._impute_n_neighbors: int = 5
        # For inverse_transform of target encoding
        self._target_encoding_maps: dict[str, dict[int, str]] = {}
        # Multicollinearity removal
        self._remove_multicollinearity: bool = False
        self._multicollinearity_threshold: float = 0.9
        # Class imbalance handling
        self._fix_imbalance: bool = False
        self._imbalance_method: str = "smote"
        self._use_balanced_class_weight: bool = False

    def setup(
        self,
        data: pl.DataFrame,
        target: str,
        *,
        train_size: float = 0.8,
        seed: int = 42,
        normalize: bool = True,
        normalize_method: str = "zscore",
        categorical_encoding: str = "onehot",
        imputation_strategy: str = "mean",
        impute_n_neighbors: int = 5,
        remove_outliers: bool = False,
        outlier_threshold: float = 0.05,
        max_cardinality: int = 50,
        exclude_columns: list[str] | None = None,
        remove_multicollinearity: bool = False,
        multicollinearity_threshold: float = 0.9,
        fix_imbalance: bool = False,
        imbalance_method: str = "smote",
    ) -> SetupResult:
        """Auto-configure preprocessing and return transformed data splits.

        Auto-detects:
        - Task type: classification (if target is categorical/bool) vs regression
        - Numeric vs categorical columns
        - Missing value patterns

        Applies (in order):
        1. Missing value imputation
        2. Categorical encoding (one-hot, ordinal, or target encoding)
        3. Multicollinearity removal (optional, correlation-based)
        4. Numeric scaling (StandardScaler if ``normalize=True``)
        5. Optional outlier removal (IQR-based)
        6. Train/test split
        7. Class imbalance correction (optional, training data only)

        Parameters
        ----------
        data:
            Polars DataFrame with features and target.
        target:
            Name of the target column.
        train_size:
            Fraction of data used for training (0 < train_size < 1).
        seed:
            Random seed for reproducibility.
        normalize:
            Whether to apply scaling to numeric columns.
        normalize_method:
            Scaling method: ``"zscore"`` (StandardScaler), ``"minmax"``
            (MinMaxScaler), ``"robust"`` (RobustScaler), or ``"maxabs"``
            (MaxAbsScaler).
        categorical_encoding:
            ``"onehot"``, ``"ordinal"``, or ``"target"``.
        imputation_strategy:
            ``"mean"``, ``"median"``, ``"mode"``, ``"drop"``, ``"knn"``,
            or ``"iterative"``.
        impute_n_neighbors:
            Number of neighbors for KNN imputation (only used when
            ``imputation_strategy="knn"``).
        remove_outliers:
            Whether to remove outliers using IQR method.
        outlier_threshold:
            IQR multiplier for outlier detection (fraction of data that
            can be considered outlier).  Lower values are more aggressive.
        max_cardinality:
            Maximum number of unique values for one-hot encoding.
            Categorical columns exceeding this threshold are automatically
            downgraded to ordinal encoding.  Only applies when
            ``categorical_encoding="onehot"``.
        exclude_columns:
            Column names to exclude from categorical encoding.  Excluded
            columns are left as-is (no encoding applied).  All names must
            exist in *data*.
        remove_multicollinearity:
            Whether to remove highly correlated feature columns.  When
            enabled, pairs with absolute Pearson correlation above
            ``multicollinearity_threshold`` are detected and the column
            with lower absolute correlation to the target is dropped.
        multicollinearity_threshold:
            Absolute Pearson correlation threshold for multicollinearity
            detection.  Column pairs exceeding this value trigger removal.
            Must be between 0 and 1.
        fix_imbalance:
            Whether to apply class imbalance correction on the training
            split.  Only applies for classification tasks.
        imbalance_method:
            Strategy for fixing class imbalance: ``"smote"`` (Synthetic
            Minority Oversampling), ``"adasyn"`` (Adaptive Synthetic
            Sampling), or ``"class_weight"`` (flag for downstream
            consumers to use balanced class weights instead of
            resampling).  ``"smote"`` and ``"adasyn"`` require the
            ``kailash-ml[imbalance]`` extra.
        """
        if target not in data.columns:
            raise ValueError(f"Target column '{target}' not found in data.")
        if data.height == 0:
            raise ValueError("Input data is empty.")
        if not 0 < train_size < 1:
            raise ValueError(f"train_size must be between 0 and 1, got {train_size}.")
        if categorical_encoding not in ("onehot", "ordinal", "target"):
            raise ValueError(
                f"categorical_encoding must be 'onehot', 'ordinal', or 'target', "
                f"got '{categorical_encoding}'."
            )
        _valid_normalize = ("zscore", "minmax", "robust", "maxabs")
        if normalize_method not in _valid_normalize:
            raise ValueError(
                f"normalize_method must be one of {_valid_normalize}, "
                f"got '{normalize_method}'."
            )
        _valid_impute = ("mean", "median", "mode", "drop", "knn", "iterative")
        if imputation_strategy not in _valid_impute:
            raise ValueError(
                f"imputation_strategy must be one of {_valid_impute}, "
                f"got '{imputation_strategy}'."
            )
        if exclude_columns is not None:
            invalid_cols = [c for c in exclude_columns if c not in data.columns]
            if invalid_cols:
                msg = (
                    f"exclude_columns contains columns not in DataFrame: {invalid_cols}"
                )
                raise ValueError(msg)
        if remove_multicollinearity and not (0.0 < multicollinearity_threshold <= 1.0):
            raise ValueError(
                f"multicollinearity_threshold must be in (0, 1], got {multicollinearity_threshold}."
            )
        _valid_imbalance = ("smote", "adasyn", "class_weight")
        if imbalance_method not in _valid_imbalance:
            raise ValueError(
                f"imbalance_method must be one of {_valid_imbalance}, "
                f"got '{imbalance_method}'."
            )

        original_shape = (data.height, data.width)

        # Detect task type
        task_type = _detect_task_type(data[target])
        numeric_cols, categorical_cols = _identify_column_types(data, target)

        # Store config
        self._target_column = target
        self._task_type = task_type
        self._numeric_columns = numeric_cols
        self._categorical_columns = categorical_cols
        self._encoding = categorical_encoding
        self._normalize = normalize
        self._normalize_method = normalize_method
        self._imputation_strategy = imputation_strategy
        self._impute_n_neighbors = impute_n_neighbors
        self._remove_multicollinearity = remove_multicollinearity
        self._multicollinearity_threshold = multicollinearity_threshold
        self._fix_imbalance = fix_imbalance
        self._imbalance_method = imbalance_method
        self._use_balanced_class_weight = False
        self._config = {
            "target": target,
            "task_type": task_type,
            "train_size": train_size,
            "seed": seed,
            "normalize": normalize,
            "normalize_method": normalize_method,
            "categorical_encoding": categorical_encoding,
            "imputation_strategy": imputation_strategy,
            "impute_n_neighbors": impute_n_neighbors,
            "remove_outliers": remove_outliers,
            "outlier_threshold": outlier_threshold,
            "numeric_columns": list(numeric_cols),
            "categorical_columns": list(categorical_cols),
            "remove_multicollinearity": remove_multicollinearity,
            "multicollinearity_threshold": multicollinearity_threshold,
            "fix_imbalance": fix_imbalance,
            "imbalance_method": imbalance_method,
        }

        # Reset transformers
        self._transformers = {}
        self._target_encoding_maps = {}

        # 1. Impute missing values
        result_df = self._impute(
            data, numeric_cols, categorical_cols, imputation_strategy
        )

        # 2. Encode categoricals
        result_df = self._encode_categoricals(
            result_df,
            categorical_cols,
            target,
            categorical_encoding,
            max_cardinality=max_cardinality,
            exclude_columns=exclude_columns,
        )

        # 3. Remove multicollinear features (after encoding, before scaling)
        if remove_multicollinearity:
            result_df = self._remove_multicollinear_features(
                result_df, target, multicollinearity_threshold
            )

        # 4. Normalize numerics
        if normalize and numeric_cols:
            result_df = self._scale_numerics(result_df, numeric_cols)

        # 5. Outlier removal (before split, so we don't lose test data shape)
        if remove_outliers and numeric_cols:
            result_df = self._remove_outliers(
                result_df, numeric_cols, outlier_threshold
            )

        # 6. Train/test split
        train_df, test_df = self._split(result_df, train_size, seed)

        # 7. Class imbalance correction (on training data only)
        if fix_imbalance and task_type == "classification":
            train_df = self._apply_imbalance_correction(
                train_df, target, imbalance_method, seed
            )

        transformed_shape = (result_df.height, result_df.width)
        self._fitted = True

        # Build summary
        multicollinear_dropped = self._transformers.get("multicollinear_dropped", [])
        summary_lines = [
            f"Task type: {task_type}",
            f"Original shape: {original_shape[0]} rows x {original_shape[1]} cols",
            f"Transformed shape: {transformed_shape[0]} rows x {transformed_shape[1]} cols",
            f"Numeric features: {len(numeric_cols)}",
            f"Categorical features: {len(categorical_cols)}",
            f"Encoding: {categorical_encoding}",
            f"Normalization: {'yes' if normalize else 'no'}",
            f"Imputation: {imputation_strategy}",
            f"Outlier removal: {'yes (threshold={:.2f})'.format(outlier_threshold) if remove_outliers else 'no'}",
            f"Multicollinearity removal: {'yes (dropped {})'.format(multicollinear_dropped) if remove_multicollinearity and multicollinear_dropped else 'no'}",
            f"Imbalance correction: {imbalance_method if fix_imbalance and task_type == 'classification' else 'no'}",
            f"Train size: {train_df.height} rows",
            f"Test size: {test_df.height} rows",
        ]
        summary = "\n".join(summary_lines)

        return SetupResult(
            train_data=train_df,
            test_data=test_df,
            target_column=target,
            task_type=task_type,
            numeric_columns=numeric_cols,
            categorical_columns=categorical_cols,
            transformers=dict(self._transformers),
            original_shape=original_shape,
            transformed_shape=transformed_shape,
            summary=summary,
        )

    def get_config(self) -> dict[str, Any]:
        """Return current preprocessing configuration.

        Raises ``RuntimeError`` if ``setup()`` has not been called.
        """
        if not self._fitted:
            raise RuntimeError("Pipeline has not been fitted. Call setup() first.")
        return dict(self._config)

    def transform(self, data: pl.DataFrame) -> pl.DataFrame:
        """Apply fitted transforms to new data (inference time).

        Applies the same imputation, encoding, multicollinearity removal,
        and scaling that were fitted during ``setup()``.

        Raises ``RuntimeError`` if ``setup()`` has not been called.
        """
        if not self._fitted:
            raise RuntimeError("Pipeline has not been fitted. Call setup() first.")

        result_df = data

        # 1. Impute
        result_df = self._apply_fitted_imputation(result_df)

        # 2. Encode categoricals
        result_df = self._apply_fitted_encoding(result_df)

        # 3. Drop multicollinear columns
        multicollinear_dropped = self._transformers.get("multicollinear_dropped", [])
        if multicollinear_dropped:
            cols_to_drop = [c for c in multicollinear_dropped if c in result_df.columns]
            if cols_to_drop:
                result_df = result_df.drop(cols_to_drop)

        # 4. Scale numerics
        if self._normalize and self._numeric_columns:
            result_df = self._apply_fitted_scaling(result_df)

        return result_df

    def inverse_transform(self, data: pl.DataFrame) -> pl.DataFrame:
        """Reverse transforms (for interpretability).

        Currently supports inverse scaling. Categorical inverse transform
        is best-effort (ordinal encoding can be reversed; one-hot cannot
        without the original column names).

        Raises ``RuntimeError`` if ``setup()`` has not been called.
        """
        if not self._fitted:
            raise RuntimeError("Pipeline has not been fitted. Call setup() first.")

        result_df = data

        # Inverse scale
        if self._normalize and "scaler" in self._transformers:
            scaler = self._transformers["scaler"]
            cols_present = [c for c in self._numeric_columns if c in result_df.columns]
            if cols_present:
                arr = result_df.select(cols_present).to_numpy()
                # scaler was fitted on these columns in order
                col_indices = [
                    self._numeric_columns.index(c)
                    for c in cols_present
                    if c in self._numeric_columns
                ]
                # Build the full-width array for inverse_transform
                full_arr = np.zeros((arr.shape[0], len(self._numeric_columns)))
                for out_idx, col_idx in enumerate(col_indices):
                    full_arr[:, col_idx] = arr[:, out_idx]
                inversed = scaler.inverse_transform(full_arr)
                for out_idx, col_idx in enumerate(col_indices):
                    result_df = result_df.with_columns(
                        pl.Series(cols_present[out_idx], inversed[:, col_idx])
                    )

        return result_df

    # ------------------------------------------------------------------
    # Private: imputation
    # ------------------------------------------------------------------

    def _impute(
        self,
        data: pl.DataFrame,
        numeric_cols: list[str],
        categorical_cols: list[str],
        strategy: str,
    ) -> pl.DataFrame:
        """Impute missing values and store fitted statistics."""
        if strategy == "drop":
            all_cols = numeric_cols + categorical_cols + [self._target_column]
            cols_in_data = [c for c in all_cols if c in data.columns]
            result = data.drop_nulls(subset=cols_in_data)
            self._transformers["imputer_strategy"] = "drop"
            return result

        # KNN / iterative: sklearn-based imputation for numeric columns
        if strategy in ("knn", "iterative"):
            return self._impute_sklearn(data, numeric_cols, categorical_cols, strategy)

        result = data
        imputer_stats: dict[str, Any] = {}

        # Numeric imputation
        for col in numeric_cols:
            if col not in data.columns:
                continue
            null_count = data[col].null_count()
            if null_count == 0:
                continue

            if strategy == "mean":
                fill_val = data[col].mean()
            elif strategy == "median":
                fill_val = data[col].median()
            elif strategy == "mode":
                mode_series = data[col].drop_nulls().mode()
                fill_val = mode_series[0] if len(mode_series) > 0 else 0.0
            else:
                fill_val = 0.0

            if fill_val is None:
                fill_val = 0.0
            imputer_stats[col] = fill_val
            result = result.with_columns(pl.col(col).fill_null(fill_val))

        # Categorical imputation: always use mode
        for col in categorical_cols:
            if col not in data.columns:
                continue
            null_count = data[col].null_count()
            if null_count == 0:
                continue
            mode_series = data[col].drop_nulls().mode()
            fill_val = mode_series[0] if len(mode_series) > 0 else "unknown"
            imputer_stats[col] = fill_val
            result = result.with_columns(pl.col(col).fill_null(fill_val))

        self._transformers["imputer_stats"] = imputer_stats
        self._transformers["imputer_strategy"] = strategy
        return result

    def _impute_sklearn(
        self,
        data: pl.DataFrame,
        numeric_cols: list[str],
        categorical_cols: list[str],
        strategy: str,
    ) -> pl.DataFrame:
        """Impute numeric columns using sklearn KNN or Iterative imputer.

        Categorical columns still receive mode imputation (KNN and iterative
        imputers are numeric-only).
        """
        result = data

        # Numeric imputation via sklearn
        cols_present = [c for c in numeric_cols if c in data.columns]
        if cols_present:
            arr = data.select(cols_present).to_numpy().astype(np.float64)

            if strategy == "knn":
                from sklearn.impute import KNNImputer

                imputer = KNNImputer(n_neighbors=self._impute_n_neighbors)
            else:  # "iterative"
                from sklearn.experimental import enable_iterative_imputer  # noqa: F401
                from sklearn.impute import IterativeImputer

                imputer = IterativeImputer(random_state=42)

            imputed = imputer.fit_transform(arr)
            self._transformers["sklearn_imputer"] = imputer
            self._transformers["sklearn_imputer_cols"] = cols_present

            for i, col in enumerate(cols_present):
                result = result.with_columns(pl.Series(col, imputed[:, i]))

        # Categorical imputation: always use mode
        cat_stats: dict[str, Any] = {}
        for col in categorical_cols:
            if col not in data.columns:
                continue
            null_count = data[col].null_count()
            if null_count == 0:
                continue
            mode_series = data[col].drop_nulls().mode()
            fill_val = mode_series[0] if len(mode_series) > 0 else "unknown"
            cat_stats[col] = fill_val
            result = result.with_columns(pl.col(col).fill_null(fill_val))

        self._transformers["imputer_stats"] = cat_stats
        self._transformers["imputer_strategy"] = strategy
        return result

    def _apply_fitted_imputation(self, data: pl.DataFrame) -> pl.DataFrame:
        """Apply previously fitted imputation to new data."""
        strategy = self._transformers.get("imputer_strategy", "mean")
        if strategy == "drop":
            all_cols = (
                self._numeric_columns
                + self._categorical_columns
                + [self._target_column]
            )
            cols_in_data = [c for c in all_cols if c in data.columns]
            return data.drop_nulls(subset=cols_in_data)

        result = data

        # sklearn-based imputers (knn / iterative)
        if strategy in ("knn", "iterative") and "sklearn_imputer" in self._transformers:
            imputer = self._transformers["sklearn_imputer"]
            cols = self._transformers.get("sklearn_imputer_cols", [])
            cols_present = [c for c in cols if c in result.columns]
            if cols_present:
                arr = result.select(cols_present).to_numpy().astype(np.float64)
                imputed = imputer.transform(arr)
                for i, col in enumerate(cols_present):
                    result = result.with_columns(pl.Series(col, imputed[:, i]))

        # Simple stats-based imputation (mean/median/mode or categorical mode)
        stats = self._transformers.get("imputer_stats", {})
        for col, fill_val in stats.items():
            if col in result.columns:
                result = result.with_columns(pl.col(col).fill_null(fill_val))
        return result

    # ------------------------------------------------------------------
    # Private: encoding
    # ------------------------------------------------------------------

    def _encode_categoricals(
        self,
        data: pl.DataFrame,
        categorical_cols: list[str],
        target: str,
        encoding: str,
        *,
        max_cardinality: int = 50,
        exclude_columns: list[str] | None = None,
    ) -> pl.DataFrame:
        """Encode categorical columns and store fitted mappings."""
        if not categorical_cols:
            return data

        # Filter out excluded columns
        cols_to_encode = [
            c for c in categorical_cols if c not in (exclude_columns or [])
        ]
        cols_present = [c for c in cols_to_encode if c in data.columns]
        if not cols_present:
            return data

        if encoding == "onehot":
            # Split by cardinality: low-cardinality -> onehot, high -> ordinal
            low_card_cols: list[str] = []
            high_card_cols: list[str] = []
            for col in cols_present:
                n_unique = data[col].drop_nulls().n_unique()
                if n_unique > max_cardinality:
                    logger.warning(
                        "Column '%s' has %d unique values (> max_cardinality=%d), "
                        "using ordinal encoding",
                        col,
                        n_unique,
                        max_cardinality,
                    )
                    high_card_cols.append(col)
                else:
                    low_card_cols.append(col)

            result = data
            if low_card_cols:
                result = self._onehot_encode(result, low_card_cols)
            if high_card_cols:
                result = self._ordinal_encode_overflow(result, high_card_cols)
            return result
        elif encoding == "ordinal":
            return self._ordinal_encode(data, cols_present)
        elif encoding == "target":
            return self._target_encode(data, cols_present, target)
        return data

    def _onehot_encode(self, data: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
        """One-hot encode categorical columns using polars."""
        result = data
        onehot_mappings: dict[str, list[str]] = {}

        for col in cols:
            if col not in result.columns:
                continue
            # Cast to string for uniform handling
            col_series = result[col]
            if col_series.dtype == pl.Boolean:
                col_series = col_series.cast(pl.Utf8)
                result = result.with_columns(col_series.alias(col))

            categories = (
                result[col].drop_nulls().cast(pl.Utf8).unique().sort().to_list()
            )
            onehot_mappings[col] = categories

            for cat in categories:
                new_col_name = f"{col}_{cat}"
                result = result.with_columns(
                    (result[col].cast(pl.Utf8) == str(cat))
                    .cast(pl.Float64)
                    .alias(new_col_name)
                )
            result = result.drop(col)

        self._transformers["onehot_mappings"] = onehot_mappings
        return result

    def _ordinal_encode(self, data: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
        """Ordinal encode categorical columns."""
        result = data
        ordinal_mappings: dict[str, dict[str, int]] = {}

        for col in cols:
            if col not in result.columns:
                continue
            categories = (
                result[col].drop_nulls().cast(pl.Utf8).unique().sort().to_list()
            )
            mapping = {cat: i for i, cat in enumerate(categories)}
            ordinal_mappings[col] = mapping

            result = result.with_columns(
                result[col]
                .cast(pl.Utf8)
                .replace_strict(mapping, default=-1)
                .cast(pl.Float64)
                .alias(col)
            )

        self._transformers["ordinal_mappings"] = ordinal_mappings
        return result

    def _ordinal_encode_overflow(
        self,
        data: pl.DataFrame,
        cols: list[str],
    ) -> pl.DataFrame:
        """Ordinal-encode columns that exceeded the cardinality threshold.

        Mappings are stored separately from explicit ordinal encoding
        to preserve backward compatibility of the transformers dict.
        """
        result = data
        overflow_mappings: dict[str, dict[str, int]] = {}
        for col in cols:
            if col not in result.columns:
                continue
            categories = (
                result[col].drop_nulls().cast(pl.Utf8).unique().sort().to_list()
            )
            mapping = {cat: i for i, cat in enumerate(categories)}
            overflow_mappings[col] = mapping
            result = result.with_columns(
                pl.col(col)
                .cast(pl.Utf8)
                .replace_strict(
                    {k: str(v) for k, v in mapping.items()},
                    default="-1",
                )
                .cast(pl.Int64)
                .alias(col)
            )
        self._transformers["ordinal_overflow_mappings"] = overflow_mappings
        return result

    def _target_encode(
        self, data: pl.DataFrame, cols: list[str], target: str
    ) -> pl.DataFrame:
        """Target encode categorical columns (mean of target per category)."""
        result = data
        target_mappings: dict[str, dict[str, float]] = {}

        global_mean = data[target].mean()
        if global_mean is None:
            global_mean = 0.0

        for col in cols:
            if col not in result.columns:
                continue
            # Compute mean target per category
            group_stats = (
                data.select([pl.col(col).cast(pl.Utf8), pl.col(target)])
                .group_by(col)
                .agg(pl.col(target).mean().alias("_target_mean"))
            )
            mapping: dict[str, float] = {}
            for row in group_stats.iter_rows():
                cat_val, mean_val = row
                if cat_val is not None and mean_val is not None:
                    mapping[str(cat_val)] = float(mean_val)

            target_mappings[col] = mapping

            result = result.with_columns(
                result[col]
                .cast(pl.Utf8)
                .replace_strict(mapping, default=global_mean)
                .cast(pl.Float64)
                .alias(col)
            )

        self._transformers["target_mappings"] = target_mappings
        self._transformers["target_global_mean"] = global_mean
        return result

    def _apply_fitted_encoding(self, data: pl.DataFrame) -> pl.DataFrame:
        """Apply previously fitted encoding to new data.

        Uses separate ``if`` blocks (not ``elif``) so that mixed encoding
        (onehot + ordinal overflow) can coexist in the same pipeline.
        """
        result = data

        if "onehot_mappings" in self._transformers:
            mappings = self._transformers["onehot_mappings"]
            for col, categories in mappings.items():
                if col not in result.columns:
                    continue
                for cat in categories:
                    new_col_name = f"{col}_{cat}"
                    result = result.with_columns(
                        (result[col].cast(pl.Utf8) == str(cat))
                        .cast(pl.Float64)
                        .alias(new_col_name)
                    )
                result = result.drop(col)

        if "ordinal_overflow_mappings" in self._transformers:
            overflow = self._transformers["ordinal_overflow_mappings"]
            for col, mapping in overflow.items():
                if col not in result.columns:
                    continue
                result = result.with_columns(
                    pl.col(col)
                    .cast(pl.Utf8)
                    .replace_strict(
                        {k: str(v) for k, v in mapping.items()},
                        default="-1",
                    )
                    .cast(pl.Int64)
                    .alias(col)
                )

        if "ordinal_mappings" in self._transformers:
            mappings = self._transformers["ordinal_mappings"]
            for col, mapping in mappings.items():
                if col not in result.columns:
                    continue
                result = result.with_columns(
                    result[col]
                    .cast(pl.Utf8)
                    .replace_strict(mapping, default=-1)
                    .cast(pl.Float64)
                    .alias(col)
                )

        if "target_mappings" in self._transformers:
            mappings = self._transformers["target_mappings"]
            global_mean = self._transformers.get("target_global_mean", 0.0)
            for col, mapping in mappings.items():
                if col not in result.columns:
                    continue
                result = result.with_columns(
                    result[col]
                    .cast(pl.Utf8)
                    .replace_strict(mapping, default=global_mean)
                    .cast(pl.Float64)
                    .alias(col)
                )

        return result

    # ------------------------------------------------------------------
    # Private: multicollinearity removal
    # ------------------------------------------------------------------

    def _remove_multicollinear_features(
        self,
        data: pl.DataFrame,
        target: str,
        threshold: float,
    ) -> pl.DataFrame:
        """Remove features with high pairwise Pearson correlation.

        For each pair where ``|r| > threshold``, the column with lower
        absolute correlation to the target is dropped.  Dropped column
        names are stored in ``self._transformers["multicollinear_dropped"]``.
        """
        from kailash_ml.engines._shared import NUMERIC_DTYPES as _NUMERIC_DTYPES

        # Identify numeric feature columns currently in the DataFrame
        numeric_feature_cols = [
            col
            for col in data.columns
            if col != target and data[col].dtype in _NUMERIC_DTYPES
        ]
        if len(numeric_feature_cols) < 2:
            self._transformers["multicollinear_dropped"] = []
            return data

        # Build numpy correlation matrix
        arr = data.select(numeric_feature_cols).to_numpy().astype(np.float64)
        corr_matrix = np.corrcoef(arr, rowvar=False)

        # Compute absolute correlation of each feature with the target
        target_dtype = data[target].dtype
        if target_dtype in (pl.Utf8, pl.String, pl.Categorical):
            # Target is non-numeric; skip target-aware dropping and drop
            # the higher-indexed feature from each correlated pair
            logger.debug(
                "Target '%s' is non-numeric (%s); using index-based "
                "multicollinearity removal.",
                target,
                target_dtype,
            )
            dropped: set[str] = set()
            n = len(numeric_feature_cols)
            for i in range(n):
                if numeric_feature_cols[i] in dropped:
                    continue
                for j in range(i + 1, n):
                    if numeric_feature_cols[j] in dropped:
                        continue
                    if abs(corr_matrix[i, j]) > threshold:
                        dropped.add(numeric_feature_cols[j])
            self._transformers["multicollinear_dropped"] = list(dropped)
            return data.drop(list(dropped))
        target_arr = data[target].to_numpy().astype(np.float64)
        target_corrs: dict[str, float] = {}
        for i, col in enumerate(numeric_feature_cols):
            col_arr = arr[:, i]
            # Handle constant columns (correlation undefined)
            if np.std(col_arr) == 0.0 or np.std(target_arr) == 0.0:
                target_corrs[col] = 0.0
            else:
                r = np.corrcoef(col_arr, target_arr)[0, 1]
                target_corrs[col] = abs(r) if np.isfinite(r) else 0.0

        # Find columns to drop
        dropped: set[str] = set()
        n = len(numeric_feature_cols)
        for i in range(n):
            if numeric_feature_cols[i] in dropped:
                continue
            for j in range(i + 1, n):
                if numeric_feature_cols[j] in dropped:
                    continue
                r = corr_matrix[i, j]
                if not np.isfinite(r):
                    continue
                if abs(r) > threshold:
                    col_i = numeric_feature_cols[i]
                    col_j = numeric_feature_cols[j]
                    # Drop the one with lower target correlation
                    if target_corrs[col_i] >= target_corrs[col_j]:
                        drop_col = col_j
                    else:
                        drop_col = col_i
                    dropped.add(drop_col)
                    logger.info(
                        "Multicollinearity: dropping '%s' (|r|=%.3f with '%s', "
                        "target_corr=%.3f vs %.3f)",
                        drop_col,
                        abs(r),
                        col_j if drop_col == col_i else col_i,
                        target_corrs[drop_col],
                        target_corrs[col_j if drop_col == col_i else col_i],
                    )

        dropped_list = sorted(dropped)
        self._transformers["multicollinear_dropped"] = dropped_list

        if dropped_list:
            data = data.drop(dropped_list)
        return data

    # ------------------------------------------------------------------
    # Private: scaling
    # ------------------------------------------------------------------

    def _scale_numerics(
        self, data: pl.DataFrame, numeric_cols: list[str]
    ) -> pl.DataFrame:
        """Fit a scaler on numeric columns and transform data.

        The scaler type is determined by ``self._normalize_method``:
        ``"zscore"`` -> StandardScaler, ``"minmax"`` -> MinMaxScaler,
        ``"robust"`` -> RobustScaler, ``"maxabs"`` -> MaxAbsScaler.
        """
        from sklearn.preprocessing import (
            MaxAbsScaler,
            MinMaxScaler,
            RobustScaler,
            StandardScaler,
        )

        cols_present = [c for c in numeric_cols if c in data.columns]
        if not cols_present:
            return data

        scaler_classes = {
            "zscore": StandardScaler,
            "minmax": MinMaxScaler,
            "robust": RobustScaler,
            "maxabs": MaxAbsScaler,
        }
        scaler_cls = scaler_classes[self._normalize_method]

        arr = data.select(cols_present).to_numpy().astype(np.float64)
        scaler = scaler_cls()
        scaled = scaler.fit_transform(arr)
        self._transformers["scaler"] = scaler

        result = data
        for i, col in enumerate(cols_present):
            result = result.with_columns(pl.Series(col, scaled[:, i]))
        return result

    def _apply_fitted_scaling(self, data: pl.DataFrame) -> pl.DataFrame:
        """Apply previously fitted scaler to new data."""
        if "scaler" not in self._transformers:
            return data
        scaler = self._transformers["scaler"]
        cols_present = [c for c in self._numeric_columns if c in data.columns]
        if not cols_present:
            return data

        arr = data.select(cols_present).to_numpy().astype(np.float64)
        scaled = scaler.transform(arr)

        result = data
        for i, col in enumerate(cols_present):
            result = result.with_columns(pl.Series(col, scaled[:, i]))
        return result

    # ------------------------------------------------------------------
    # Private: outlier removal
    # ------------------------------------------------------------------

    def _remove_outliers(
        self,
        data: pl.DataFrame,
        numeric_cols: list[str],
        threshold: float,
    ) -> pl.DataFrame:
        """Remove outliers using IQR method.

        For each numeric column, rows where values fall outside
        [Q1 - iqr_mult * IQR, Q3 + iqr_mult * IQR] are removed.
        ``iqr_mult`` is derived from the threshold: lower threshold means
        more aggressive removal.
        """
        # Map threshold to IQR multiplier: 0.05 -> 1.5 (aggressive), 0.25 -> 3.0 (lenient)
        iqr_mult = 1.5 + (threshold - 0.05) * (3.0 - 1.5) / (0.25 - 0.05)
        iqr_mult = max(1.0, min(iqr_mult, 5.0))

        result = data
        for col in numeric_cols:
            if col not in result.columns:
                continue
            q1 = result[col].quantile(0.25)
            q3 = result[col].quantile(0.75)
            if q1 is None or q3 is None:
                continue
            iqr = q3 - q1
            lower = q1 - iqr_mult * iqr
            upper = q3 + iqr_mult * iqr
            result = result.filter(
                (pl.col(col) >= lower) & (pl.col(col) <= upper) | pl.col(col).is_null()
            )

        n_removed = data.height - result.height
        if n_removed > 0:
            logger.info(
                "Removed %d outlier rows (%.1f%% of data)",
                n_removed,
                100 * n_removed / data.height,
            )
        return result

    # ------------------------------------------------------------------
    # Private: class imbalance correction
    # ------------------------------------------------------------------

    def _apply_imbalance_correction(
        self,
        train_df: pl.DataFrame,
        target: str,
        method: str,
        seed: int,
    ) -> pl.DataFrame:
        """Apply class imbalance correction to training data.

        ``"class_weight"`` sets a flag for downstream consumers (e.g.
        ``TrainingPipeline``).  ``"smote"`` and ``"adasyn"`` perform
        actual oversampling and require ``imbalanced-learn``.
        """
        if method == "class_weight":
            self._use_balanced_class_weight = True
            logger.info(
                "Imbalance correction: using balanced class weights "
                "(no resampling applied)"
            )
            return train_df

        # SMOTE / ADASYN -- require imbalanced-learn
        try:
            if method == "smote":
                from imblearn.over_sampling import SMOTE

                sampler = SMOTE(random_state=seed)
            else:  # "adasyn"
                from imblearn.over_sampling import ADASYN

                sampler = ADASYN(random_state=seed)
        except ImportError:
            raise ImportError(
                f"imbalanced-learn is required for imbalance_method='{method}'. "
                "Install it with: pip install kailash-ml[imbalance]"
            ) from None

        feature_cols = [c for c in train_df.columns if c != target]
        X = train_df.select(feature_cols).to_numpy().astype(np.float64)
        y = train_df[target].to_numpy()

        original_height = train_df.height
        X_res, y_res = sampler.fit_resample(X, y)

        # Rebuild polars DataFrame
        result_data: dict[str, list[Any]] = {}
        for i, col in enumerate(feature_cols):
            result_data[col] = X_res[:, i].tolist()
        result_data[target] = y_res.tolist()
        result_df = pl.DataFrame(result_data)

        # Preserve original dtypes
        cast_exprs = []
        for col in result_df.columns:
            if col in train_df.columns:
                orig_dtype = train_df[col].dtype
                if result_df[col].dtype != orig_dtype:
                    cast_exprs.append(pl.col(col).cast(orig_dtype))
        if cast_exprs:
            result_df = result_df.with_columns(cast_exprs)

        logger.info(
            "Imbalance correction (%s): %d -> %d training samples",
            method,
            original_height,
            result_df.height,
        )
        return result_df

    # ------------------------------------------------------------------
    # Private: splitting
    # ------------------------------------------------------------------

    def _split(
        self, data: pl.DataFrame, train_size: float, seed: int
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Deterministic shuffle + split into train/test."""
        n = data.height
        split_idx = int(n * train_size)
        rng = np.random.RandomState(seed)
        indices = np.arange(n)
        rng.shuffle(indices)
        train_idx = indices[:split_idx].tolist()
        test_idx = indices[split_idx:].tolist()
        return data[train_idx], data[test_idx]
