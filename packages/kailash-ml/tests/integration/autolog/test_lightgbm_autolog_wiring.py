# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.c Tier-2 wiring test — lightgbm autolog end-to-end.

Per ``specs/ml-autolog.md §8.1`` MUST:

- Fit a TOY model (small, CPU-only, ≤1 second).
- File-backed SQLite (NOT ``:memory:``) so ``list_metrics`` +
  ``list_artifacts`` exercise the full write/read round-trip.
- Assert ≥3 metrics + 1 artifact emitted under the ambient run.
- Verify ``lgb.train`` is restored on CM exit (detach discipline
  per §3.2 + §1.3 non-goal).

Per ``rules/testing.md §Tier 2`` — real lightgbm, real disk SQLite,
no mocks. The only non-real bit is the toy dataset shape (32 rows × 4
features over 5 boosting rounds), chosen so ``lgb.train`` completes
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
    be = SqliteTrackerStore(tmp_path / "autolog_lightgbm_tracker.db")
    await be.initialize()
    try:
        yield be
    finally:
        await be.close()


@pytest.fixture
def toy_classification_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Tiny deterministic binary classification set — 32 rows × 4 feats
    with an 8-row held-out valid split so ``valid_sets=[train, valid]``
    emits both ``training_*`` and ``valid_*`` metrics."""
    rng = np.random.default_rng(seed=42)
    X = rng.standard_normal((40, 4))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    return X[:32], y[:32], X[32:], y[32:]


async def test_lightgbm_autolog_emits_metrics_params_and_artifact(
    backend: SqliteTrackerStore,
    toy_classification_data: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> None:
    """lgb.train inside km.autolog("lightgbm") emits metrics + params +
    artifacts to the ambient run per §3.1 row 5 + §8.1.
    """
    import lightgbm as lgb

    X_train, y_train, X_val, y_val = toy_classification_data

    async with track("w23c-lightgbm-wiring", backend=backend) as run:
        async with autolog("lightgbm") as handle:
            assert handle.attached_integrations == ("lightgbm",)

            train_set = lgb.Dataset(X_train, label=y_train)
            val_set = lgb.Dataset(X_val, label=y_val, reference=train_set)

            params = {
                "objective": "binary",
                "metric": "binary_logloss",
                "num_leaves": 7,
                "learning_rate": 0.1,
                "verbosity": -1,
            }
            booster = lgb.train(
                params,
                train_set,
                num_boost_round=5,
                valid_sets=[train_set, val_set],
                valid_names=["training", "valid"],
            )
            assert booster is not None, "lgb.train returned None"
        run_id = run.run_id

    # Assertions per §8.1 MUST — metrics + params + artifacts all
    # round-tripped through real on-disk SQLite.
    metrics = await backend.list_metrics(run_id)
    artifacts = await backend.list_artifacts(run_id)
    run_row = await backend.get_run(run_id)
    assert run_row is not None, "run row should exist post-exit"
    persisted_params = run_row.get("params") or {}

    # Metrics — expect per-iteration training_ + valid_ keys.
    metric_keys = {row["key"] for row in metrics}
    assert any(
        k.startswith("training_") for k in metric_keys
    ), f"expected training_* metrics, got {metric_keys}"
    assert any(
        k.startswith("valid_") for k in metric_keys
    ), f"expected valid_* metrics, got {metric_keys}"
    # ≥3 metric ROWS across 5 boosting rounds × 2 datasets = 10 rows.
    assert len(metrics) >= 3, f"expected ≥3 metric rows per §8.1, got {len(metrics)}"

    # Params — prefixed with `lgb_params.` per spec.
    param_keys = set(persisted_params.keys())
    assert any(
        k.startswith("lgb_params.") for k in param_keys
    ), f"expected lgb_params.* params, got {sorted(param_keys)[:10]}"
    assert (
        "lgb_params.objective" in param_keys
    ), f"lgb_params.objective missing from {sorted(param_keys)[:10]}"

    # Artifacts — model + feature-importance figure.
    artifact_names = {row["name"] for row in artifacts}
    assert (
        "lightgbm.model.txt" in artifact_names
    ), f"expected lightgbm.model.txt artifact, got {artifact_names}"
    assert (
        "lightgbm.feature_importance" in artifact_names
    ), f"expected feature_importance figure, got {artifact_names}"


async def test_lightgbm_autolog_restores_train_on_exit(
    backend: SqliteTrackerStore,
) -> None:
    """Per §3.2 + §1.3: detach MUST restore ``lightgbm.train``.

    Module-level wrap means ``lgb.train`` becomes a different callable
    during the block; detach restores the identity. This guards against
    the cross-test contamination failure mode called out in §1.3.
    """
    import lightgbm as lgb

    original_train = lgb.train

    async with track("w23c-lightgbm-restore", backend=backend):
        async with autolog("lightgbm"):
            # Inside the block, lgb.train is the wrapper — verify the
            # wrap was actually installed (not a no-op).
            assert (
                lgb.train is not original_train
            ), "LightgbmIntegration.attach did NOT replace lgb.train; wrap is a no-op"
    # After exit, lgb.train is restored.
    assert (
        lgb.train is original_train
    ), "LightgbmIntegration.detach did NOT restore lgb.train; module-level patch LEAKED per §1.3"


async def test_lightgbm_autolog_restores_train_even_when_body_raises(
    backend: SqliteTrackerStore,
) -> None:
    """Per §8.5 + §3.2: detach runs in ``finally:`` even when the
    wrapped block raises, and lgb.train is still restored.
    """
    import lightgbm as lgb

    original_train = lgb.train

    async with track("w23c-lightgbm-restore-on-raise", backend=backend):
        with pytest.raises(ValueError, match="user body error"):
            async with autolog("lightgbm"):
                raise ValueError("user body error")
    assert (
        lgb.train is original_train
    ), "LightgbmIntegration.detach did NOT restore lgb.train after raising body"
