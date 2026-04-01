# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Centralized polars conversion module for kailash-ml.

This is the ONLY place in kailash-ml where polars data is converted
to/from formats required by sklearn, LightGBM, HuggingFace, pandas,
and Arrow.  All converters handle categorical types, null values, and
dtype preservation.

Optional dependencies (``lightgbm``, ``datasets``, ``pyarrow``, ``pandas``)
are imported lazily so that ``import kailash_ml`` never fails due to
missing extras.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import polars as pl
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

__all__ = [
    "to_sklearn_input",
    "from_sklearn_output",
    "to_lgb_dataset",
    "to_hf_dataset",
    "polars_to_arrow",
    "to_pandas",
    "from_pandas",
    "polars_to_dict_records",
]


# ---------------------------------------------------------------------------
# 1. sklearn
# ---------------------------------------------------------------------------


def to_sklearn_input(
    df: pl.DataFrame,
    feature_columns: list[str] | None = None,
    target_column: str | None = None,
) -> tuple[NDArray, NDArray | None, dict[str, Any]]:
    """Convert a polars DataFrame to sklearn-compatible numpy arrays.

    Returns
    -------
    (X, y, column_info)
        *X* is a 2-D float64 array of features.  *y* is a 1-D array of
        targets (or ``None`` when *target_column* is not given).
        *column_info* records dtype metadata so that
        :func:`from_sklearn_output` can restore column names and decode
        categoricals.

    Raises
    ------
    ValueError
        If the DataFrame contains ``pl.Utf8``/``pl.String`` columns that
        have not been cast to ``pl.Categorical`` first, or if any column
        is entirely null.
    """
    if feature_columns is None:
        if target_column is not None:
            feature_columns = [c for c in df.columns if c != target_column]
        else:
            feature_columns = list(df.columns)

    column_info: dict[str, Any] = {"feature_columns": feature_columns}
    cat_mappings: dict[str, list[str]] = {}

    arrays: list[NDArray] = []
    for col_name in feature_columns:
        col = df[col_name]
        dtype = col.dtype

        if dtype == pl.Null:
            raise ValueError(
                f"Column '{col_name}' is entirely null -- cannot convert to numpy."
            )
        if dtype in (pl.Utf8, pl.String):
            raise ValueError(
                f"Column '{col_name}' is Utf8/String -- cast to pl.Categorical first."
            )

        if dtype == pl.Categorical:
            # Encode as integer codes; store category mapping for decoding
            categories = col.cat.get_categories().to_list()
            cat_mappings[col_name] = categories
            # physical codes; nulls become -1 via fill_null
            codes = col.to_physical().fill_null(-1).to_numpy().astype(np.float64)
            arrays.append(codes)
        elif dtype == pl.Boolean:
            arrays.append(col.cast(pl.Int8).fill_null(0).to_numpy().astype(np.float64))
        else:
            # Numeric columns -- nulls become NaN
            arrays.append(col.fill_null(float("nan")).to_numpy().astype(np.float64))

    X = (
        np.column_stack(arrays)
        if arrays
        else np.empty((df.height, 0), dtype=np.float64)
    )
    column_info["cat_mappings"] = cat_mappings

    y: NDArray | None = None
    if target_column is not None:
        target_col = df[target_column]
        if target_col.dtype == pl.Categorical:
            categories = target_col.cat.get_categories().to_list()
            column_info["target_cat_mapping"] = categories
            y = target_col.to_physical().fill_null(-1).to_numpy().astype(np.float64)
        else:
            y = target_col.fill_null(float("nan")).to_numpy().astype(np.float64)

    return X, y, column_info


def from_sklearn_output(
    predictions: NDArray,
    column_info: dict[str, Any],
    output_columns: list[str] | None = None,
) -> pl.DataFrame:
    """Convert sklearn predictions back to a polars DataFrame.

    Uses *column_info* from :func:`to_sklearn_input` to restore column
    names.  If *predictions* is 1-D it is treated as a single column
    whose name defaults to ``"prediction"``.
    """
    if predictions.ndim == 1:
        predictions = predictions.reshape(-1, 1)

    if output_columns is not None:
        col_names = output_columns
    else:
        feature_columns = column_info.get("feature_columns", [])
        if predictions.shape[1] == len(feature_columns):
            col_names = feature_columns
        else:
            col_names = [f"prediction_{i}" for i in range(predictions.shape[1])]

    data: dict[str, Any] = {}
    for i, name in enumerate(col_names):
        data[name] = predictions[:, i]

    return pl.DataFrame(data)


# ---------------------------------------------------------------------------
# 2. LightGBM
# ---------------------------------------------------------------------------


def to_lgb_dataset(
    df: pl.DataFrame,
    feature_columns: list[str],
    target_column: str,
    *,
    categorical_columns: list[str] | None = None,
) -> Any:
    """Convert a polars DataFrame to a LightGBM Dataset.

    This is the ONE place in kailash-ml that touches pandas internally.
    LightGBM's native categorical support requires ``pandas.Categorical``.
    For non-categorical data, numpy arrays are used (near zero-copy from
    polars).

    Raises
    ------
    ImportError
        If ``lightgbm`` is not installed.
    """
    try:
        import lightgbm as lgb
    except ImportError as exc:
        raise ImportError(
            "lightgbm is required for to_lgb_dataset(). "
            "Install it with: pip install lightgbm"
        ) from exc

    label = df[target_column].to_numpy().astype(np.float64)

    cat_cols = categorical_columns or []
    has_cats = bool(cat_cols)

    if has_cats:
        # Minimal pandas conversion for categorical columns only
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                "pandas is required for LightGBM categorical support. "
                "Install it with: pip install pandas"
            ) from exc

        feature_df = df.select(feature_columns)
        pdf = feature_df.to_pandas()
        for col in cat_cols:
            if col in pdf.columns:
                pdf[col] = pdf[col].astype("category")
        return lgb.Dataset(
            pdf, label=label, categorical_feature=cat_cols, free_raw_data=False
        )
    else:
        # Pure numpy path -- no pandas
        X, _, _ = to_sklearn_input(df, feature_columns=feature_columns)
        return lgb.Dataset(X, label=label, free_raw_data=False)


# ---------------------------------------------------------------------------
# 3. HuggingFace datasets
# ---------------------------------------------------------------------------


def to_hf_dataset(df: pl.DataFrame) -> Any:
    """Convert a polars DataFrame to a HuggingFace ``datasets.Dataset``.

    Uses the Arrow zero-copy path for maximum efficiency.

    Raises
    ------
    ImportError
        If the ``datasets`` library is not installed.
    """
    try:
        import datasets
    except ImportError as exc:
        raise ImportError(
            "The 'datasets' library is required for to_hf_dataset(). "
            "Install it with: pip install datasets"
        ) from exc

    arrow_table = df.to_arrow()
    return datasets.Dataset(arrow_table)


# ---------------------------------------------------------------------------
# 4. Arrow
# ---------------------------------------------------------------------------


def polars_to_arrow(
    df: pl.DataFrame,
    *,
    validate_schema: bool = False,
    expected_schema: Any | None = None,
) -> Any:
    """Convert a polars DataFrame to a ``pyarrow.Table``.

    Near zero-copy for most dtypes (polars is Arrow-native internally).

    Parameters
    ----------
    validate_schema:
        When *True*, compare the resulting schema against
        *expected_schema* and raise ``ValueError`` on mismatch.
    expected_schema:
        A ``pyarrow.Schema`` to validate against.

    Raises
    ------
    ImportError
        If ``pyarrow`` is not installed.
    ValueError
        If schema validation is requested and the schemas do not match.
    """
    try:
        import pyarrow as pa  # noqa: F841
    except ImportError as exc:
        raise ImportError(
            "pyarrow is required for polars_to_arrow(). "
            "Install it with: pip install pyarrow"
        ) from exc

    table = df.to_arrow()

    if validate_schema and expected_schema is not None:
        if table.schema != expected_schema:
            raise ValueError(
                f"Schema mismatch.\n"
                f"  Expected: {expected_schema}\n"
                f"  Got:      {table.schema}"
            )

    return table


# ---------------------------------------------------------------------------
# 5. pandas
# ---------------------------------------------------------------------------


def to_pandas(df: pl.DataFrame) -> Any:
    """Convert a polars DataFrame to a pandas DataFrame.

    For third-party library interop (SHAP, yellowbrick, matplotlib).

    Preserves:
      - ``pl.Categorical`` -> ``pd.Categorical``
      - ``pl.Date``/``pl.Datetime`` -> ``pd.Timestamp``
      - ``pl.Null`` -> ``pd.NA``
    """
    try:
        import pandas  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "pandas is required for to_pandas(). " "Install it with: pip install pandas"
        ) from exc

    return df.to_pandas()


def from_pandas(pdf: Any) -> pl.DataFrame:
    """Convert a pandas DataFrame to a polars DataFrame.

    Preserves:
      - ``pd.Categorical`` -> ``pl.Categorical``
      - ``pd.Timestamp`` -> ``pl.Datetime``
      - ``pd.NA`` / ``np.nan`` -> ``null``
    """
    return pl.from_pandas(pdf)


# ---------------------------------------------------------------------------
# 6. Dict records (for DataFlow Express API)
# ---------------------------------------------------------------------------


def polars_to_dict_records(
    df: pl.DataFrame,
    *,
    max_rows: int = 5000,
) -> list[dict[str, Any]]:
    """Convert a polars DataFrame to a list of dicts.

    Intended for the DataFlow Express API.  For bulk data (>5000 rows),
    prefer the Arrow path via :func:`polars_to_arrow`.

    Raises
    ------
    ValueError
        If *df* has more than *max_rows* rows.
    """
    if df.height > max_rows:
        raise ValueError(
            f"DataFrame has {df.height} rows, exceeding the max_rows limit "
            f"of {max_rows}. Use the Arrow path (polars_to_arrow) for bulk data."
        )
    return df.to_dicts()
