# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.d Tier-2 wiring test — xgboost autolog end-to-end.

Per ``specs/ml-autolog.md §8.1`` MUST:

- Fit a TOY model (small, CPU-only, ≤1 second).
- File-backed SQLite (NOT ``:memory:``) so ``list_metrics`` +
  ``list_artifacts`` exercise the full write/read round-trip.
- Assert ≥3 metrics + 1 artifact emitted under the ambient run.
- Verify ``xgb.train`` is restored on CM exit (detach discipline
  per §3.2 + §1.3 non-goal).

Per ``rules/testing.md §Tier 2`` — real xgboost, real disk SQLite,
no mocks. The only non-real bit is the toy dataset shape (32 rows × 4
features over 5 boosting rounds), chosen so ``xgb.train`` completes
in well under 1 second on CPU.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from kailash_ml.autolog import autolog
from kailash_ml.tracking import SqliteTrackerStore, track


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def backend(tmp_path: Path):
    """File-backed SqliteTrackerStore per spec §8.1 MUST."""
    be = SqliteTrackerStore(tmp_path / "autolog_xgboost_tracker.db")
    await be.initialize()
    try:
        yield be
    finally:
        await be.close()


@pytest.fixture
def toy_classification_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Tiny deterministic binary classification set — 32 rows × 4 feats
    with an 8-row held-out eval split so ``evals=[(train, "train"),
    (eval, "eval")]`` emits both ``train_*`` and ``eval_*`` metrics."""
    rng = np.random.default_rng(seed=42)
    X = rng.standard_normal((40, 4))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    return X[:32], y[:32], X[32:], y[32:]


async def test_xgboost_autolog_emits_metrics_params_and_artifact(
    backend: SqliteTrackerStore,
    toy_classification_data: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> None:
    """xgb.train inside km.autolog("xgboost") emits metrics + params +
    artifacts to the ambient run per §3.1 row 4 + §8.1.
    """
    import xgboost as xgb

    X_train, y_train, X_eval, y_eval = toy_classification_data

    async with track("w23d-xgboost-wiring", backend=backend) as run:
        async with autolog("xgboost") as handle:
            assert handle.attached_integrations == ("xgboost",)

            dtrain = xgb.DMatrix(X_train, label=y_train)
            deval = xgb.DMatrix(X_eval, label=y_eval)

            params = {
                "objective": "binary:logistic",
                "eval_metric": "logloss",
                "max_depth": 3,
                "learning_rate": 0.1,
                "verbosity": 0,
            }
            booster = xgb.train(
                params,
                dtrain,
                num_boost_round=5,
                evals=[(dtrain, "train"), (deval, "eval")],
            )
            assert booster is not None, "xgb.train returned None"
        run_id = run.run_id

    # Assertions per §8.1 MUST — metrics + params + artifacts all
    # round-tripped through real on-disk SQLite.
    metrics = await backend.list_metrics(run_id)
    artifacts = await backend.list_artifacts(run_id)
    run_row = await backend.get_run(run_id)
    assert run_row is not None, "run row should exist post-exit"
    persisted_params = run_row.get("params") or {}

    # Metrics — expect per-round train_ + eval_ keys.
    metric_keys = {row["key"] for row in metrics}
    assert any(
        k.startswith("train_") for k in metric_keys
    ), f"expected train_* metrics, got {metric_keys}"
    assert any(
        k.startswith("eval_") for k in metric_keys
    ), f"expected eval_* metrics, got {metric_keys}"
    # ≥3 metric ROWS across 5 rounds × 2 datasets = 10 rows.
    assert len(metrics) >= 3, f"expected ≥3 metric rows per §8.1, got {len(metrics)}"

    # Params — prefixed with `xgb_params.` per spec.
    param_keys = set(persisted_params.keys())
    assert any(
        k.startswith("xgb_params.") for k in param_keys
    ), f"expected xgb_params.* params, got {sorted(param_keys)[:10]}"
    assert (
        "xgb_params.objective" in param_keys
    ), f"xgb_params.objective missing from {sorted(param_keys)[:10]}"

    # Artifacts — model + feature-importance figure.
    artifact_names = {row["name"] for row in artifacts}
    assert (
        "xgboost.model.ubj" in artifact_names
    ), f"expected xgboost.model.ubj artifact, got {artifact_names}"
    assert (
        "xgboost.feature_importance" in artifact_names
    ), f"expected feature_importance figure, got {artifact_names}"


async def test_xgboost_autolog_restores_train_on_exit(
    backend: SqliteTrackerStore,
) -> None:
    """Per §3.2 + §1.3: detach MUST restore ``xgboost.train``.

    Module-level wrap means ``xgb.train`` becomes a different callable
    during the block; detach restores the identity. This guards against
    the cross-test contamination failure mode called out in §1.3.
    """
    import xgboost as xgb

    original_train = xgb.train

    async with track("w23d-xgboost-restore", backend=backend):
        async with autolog("xgboost"):
            # Inside the block, xgb.train is the wrapper — verify the
            # wrap was actually installed (not a no-op).
            assert (
                xgb.train is not original_train
            ), "XgboostIntegration.attach did NOT replace xgb.train; wrap is a no-op"
    # After exit, xgb.train is restored.
    assert (
        xgb.train is original_train
    ), "XgboostIntegration.detach did NOT restore xgb.train; module-level patch LEAKED per §1.3"


async def test_xgboost_autolog_restores_train_even_when_body_raises(
    backend: SqliteTrackerStore,
) -> None:
    """Per §8.5 + §3.2: detach runs in ``finally:`` even when the
    wrapped block raises, and xgb.train is still restored.
    """
    import xgboost as xgb

    original_train = xgb.train

    async with track("w23d-xgboost-restore-on-raise", backend=backend):
        with pytest.raises(ValueError, match="user body error"):
            async with autolog("xgboost"):
                raise ValueError("user body error")
    assert (
        xgb.train is original_train
    ), "XgboostIntegration.detach did NOT restore xgb.train after raising body"
