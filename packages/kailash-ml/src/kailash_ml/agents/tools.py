# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Dumb data endpoint tools for ML agents.

Per the LLM-first rule: tools fetch/write data, the LLM reasons.
No decision logic in any tool function.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "profile_data",
    "get_column_stats",
    "check_correlation",
    "sample_rows",
    "compute_feature",
    "check_target_correlation",
    "get_feature_importance",
    "list_available_trainers",
    "get_model_metadata",
    "get_trial_details",
    "compare_trials",
    "get_drift_history",
    "get_feature_distribution",
    "get_prediction_accuracy",
    "trigger_retraining",
    "get_model_versions",
    "rollback_model",
]


# ---------------------------------------------------------------------------
# DataScientist tools
# ---------------------------------------------------------------------------


async def profile_data(data: Any) -> dict[str, Any]:
    """Return statistical profile of a dataset. No decisions."""
    import polars as pl

    if not isinstance(data, pl.DataFrame):
        return {"error": "Expected polars DataFrame"}
    return {
        "n_rows": data.height,
        "n_columns": data.width,
        "columns": [
            {
                "name": col,
                "dtype": str(data[col].dtype),
                "null_count": data[col].null_count(),
                "n_unique": data[col].n_unique(),
            }
            for col in data.columns
        ],
    }


async def get_column_stats(data: Any, column: str) -> dict[str, Any]:
    """Return detailed stats for a single column. No decisions."""
    import polars as pl

    if not isinstance(data, pl.DataFrame) or column not in data.columns:
        return {"error": f"Column '{column}' not found"}
    series = data[column]
    stats: dict[str, Any] = {
        "name": column,
        "dtype": str(series.dtype),
        "null_count": series.null_count(),
        "n_unique": series.n_unique(),
    }
    if series.dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
        import numpy as np

        arr = series.drop_nulls().to_numpy()
        if len(arr) > 0:
            stats["mean"] = float(np.mean(arr))
            stats["std"] = float(np.std(arr))
            stats["min"] = float(np.min(arr))
            stats["max"] = float(np.max(arr))
            stats["median"] = float(np.median(arr))
    return stats


async def check_correlation(data: Any, col_a: str, col_b: str) -> dict[str, Any]:
    """Return Pearson correlation between two columns. No decisions."""
    import polars as pl

    if not isinstance(data, pl.DataFrame):
        return {"error": "Expected polars DataFrame"}
    try:
        corr_df = data.select(
            pl.corr(
                pl.col(col_a).fill_null(0.0).cast(pl.Float64),
                pl.col(col_b).fill_null(0.0).cast(pl.Float64),
            ).alias("corr")
        )
        corr = corr_df["corr"][0]
        return {"col_a": col_a, "col_b": col_b, "correlation": float(corr or 0.0)}
    except Exception as exc:
        return {"error": str(exc)}


async def sample_rows(data: Any, n: int = 5) -> list[dict[str, Any]]:
    """Return n sample rows as dicts. No decisions."""
    import polars as pl

    if not isinstance(data, pl.DataFrame):
        return []
    return data.head(min(n, data.height)).to_dicts()


# ---------------------------------------------------------------------------
# FeatureEngineer tools
# ---------------------------------------------------------------------------


async def compute_feature(data: Any, expression: str) -> dict[str, Any]:
    """Compute a polars expression on data. Returns stats of result."""
    import polars as pl

    if not isinstance(data, pl.DataFrame):
        return {"error": "Expected polars DataFrame"}
    try:
        result = data.select(pl.lit(expression).alias("computed"))
        return {"n_values": result.height, "sample": result.head(3).to_dicts()}
    except Exception as exc:
        return {"error": str(exc)}


async def check_target_correlation(
    data: Any, feature: str, target: str
) -> dict[str, Any]:
    """Return correlation between feature and target. No decisions."""
    return await check_correlation(data, feature, target)


async def get_feature_importance(model: Any) -> dict[str, Any]:
    """Extract feature importances from a fitted model. No decisions."""
    try:
        importances = model.feature_importances_
        return {"importances": [float(x) for x in importances]}
    except AttributeError:
        return {"error": "Model does not support feature_importances_"}


# ---------------------------------------------------------------------------
# ModelSelector tools
# ---------------------------------------------------------------------------


async def list_available_trainers() -> list[str]:
    """List available model trainer classes. No decisions."""
    return [
        "sklearn.ensemble.RandomForestClassifier",
        "sklearn.ensemble.RandomForestRegressor",
        "sklearn.ensemble.GradientBoostingClassifier",
        "sklearn.ensemble.GradientBoostingRegressor",
        "sklearn.linear_model.LogisticRegression",
        "sklearn.linear_model.Ridge",
        "sklearn.linear_model.Lasso",
        "lightgbm.LGBMClassifier",
        "lightgbm.LGBMRegressor",
    ]


async def get_model_metadata(model_type: str) -> dict[str, Any]:
    """Return metadata about a model type. No decisions."""
    metadata: dict[str, dict[str, Any]] = {
        "RandomForest": {
            "type": "ensemble",
            "handles_missing": False,
            "interpretable": True,
            "training_speed": "medium",
        },
        "GradientBoosting": {
            "type": "ensemble",
            "handles_missing": False,
            "interpretable": False,
            "training_speed": "slow",
        },
        "LightGBM": {
            "type": "gbdt",
            "handles_missing": True,
            "interpretable": False,
            "training_speed": "fast",
        },
    }
    for key, val in metadata.items():
        if key.lower() in model_type.lower():
            return val
    return {"type": "unknown", "model_type": model_type}


# ---------------------------------------------------------------------------
# ExperimentInterpreter tools
# ---------------------------------------------------------------------------


async def get_trial_details(
    trials: list[dict[str, Any]], trial_id: int
) -> dict[str, Any]:
    """Fetch details for a specific trial. No decisions."""
    if 0 <= trial_id < len(trials):
        return trials[trial_id]
    return {"error": f"Trial {trial_id} not found"}


async def compare_trials(
    trials: list[dict[str, Any]], trial_ids: list[int]
) -> list[dict[str, Any]]:
    """Fetch multiple trials for comparison. No decisions."""
    return [trials[i] for i in trial_ids if 0 <= i < len(trials)]


# ---------------------------------------------------------------------------
# DriftAnalyst tools
# ---------------------------------------------------------------------------


async def get_drift_history(
    monitor: Any, model_name: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Fetch drift history from DriftMonitor. No decisions."""
    return await monitor.get_drift_history(model_name, limit=limit)


async def get_feature_distribution(data: Any, feature: str) -> dict[str, Any]:
    """Return distribution stats for a feature. No decisions."""
    return await get_column_stats(data, feature)


async def get_prediction_accuracy(predictions: Any, actuals: Any) -> dict[str, float]:
    """Compute accuracy metrics. No decisions."""
    from sklearn.metrics import accuracy_score, mean_squared_error

    import numpy as np

    try:
        y_pred = np.array(predictions)
        y_true = np.array(actuals)
        return {
            "accuracy": float(accuracy_score(y_true, y_pred)),
        }
    except Exception:
        try:
            y_pred = np.array(predictions, dtype=float)
            y_true = np.array(actuals, dtype=float)
            return {"mse": float(mean_squared_error(y_true, y_pred))}
        except Exception as exc:
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# RetrainingDecision tools
# ---------------------------------------------------------------------------


async def trigger_retraining(
    pipeline: Any, model_name: str, spec: dict[str, Any]
) -> dict[str, Any]:
    """Trigger model retraining via pipeline. No decisions.

    Calls ``pipeline.retrain()`` if available, otherwise returns a
    pending request for the orchestrating agent to handle.
    """
    if pipeline is not None and hasattr(pipeline, "retrain"):
        try:
            result = await pipeline.retrain(
                model_name=model_name,
                schema=spec.get("schema"),
                model_spec=spec.get("model_spec"),
                eval_spec=spec.get("eval_spec"),
                data=spec.get("data"),
            )
            return {
                "model_name": model_name,
                "status": "completed",
                "result": str(result),
            }
        except Exception as exc:
            logger.warning("Retraining for '%s' failed: %s", model_name, exc)
            return {"model_name": model_name, "status": "failed", "error": str(exc)}
    logger.info("Retraining requested for '%s' (no pipeline provided).", model_name)
    return {"model_name": model_name, "status": "pending", "spec": spec}


async def get_model_versions(registry: Any, model_name: str) -> list[dict[str, Any]]:
    """List model versions from registry. No decisions."""
    versions = await registry.list_versions(model_name)
    return [v if isinstance(v, dict) else {"version": str(v)} for v in versions]


async def rollback_model(
    registry: Any, model_name: str, version: str
) -> dict[str, Any]:
    """Rollback model to a specific version via promote(). No decisions."""
    if registry is not None and hasattr(registry, "promote_model"):
        try:
            await registry.promote_model(model_name, int(version), "production")
            return {
                "model_name": model_name,
                "rolled_back_to": version,
                "status": "completed",
            }
        except Exception as exc:
            logger.warning(
                "Rollback of '%s' to v%s failed: %s", model_name, version, exc
            )
            return {
                "model_name": model_name,
                "rolled_back_to": version,
                "status": "failed",
                "error": str(exc),
            }
    logger.info(
        "Rollback requested for '%s' to v%s (no registry provided).",
        model_name,
        version,
    )
    return {"model_name": model_name, "rolled_back_to": version, "status": "pending"}
