# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W23.g Tier-2 wiring test — statsmodels autolog end-to-end.

Per ``specs/ml-autolog.md §8.1`` MUST + §3.1 row 6:

- Fit a TOY OLS model (small, CPU-only, ≤1 second).
- File-backed SQLite (NOT ``:memory:``) so ``list_metrics`` +
  ``list_artifacts`` exercise the full write/read round-trip.
- Assert metrics (rsquared/aic/bic/llf/f_pvalue) + params
  (statsmodels.params) + HTML artifact are emitted.
- Verify ``RegressionResults.summary`` is restored on CM exit
  (detach discipline per §3.2 + §1.3 non-goal).
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
    be = SqliteTrackerStore(tmp_path / "autolog_statsmodels_tracker.db")
    await be.initialize()
    try:
        yield be
    finally:
        await be.close()


@pytest.fixture
def toy_ols_data():
    """Deterministic linear dataset so rsquared ≈ 1.0."""
    rng = np.random.default_rng(seed=42)
    X = rng.standard_normal((50, 3))
    # Perfect linear relationship with small noise.
    y = 1.5 * X[:, 0] - 0.8 * X[:, 1] + 0.3 * X[:, 2] + 0.01 * rng.standard_normal(50)
    return X, y


async def test_statsmodels_autolog_emits_metrics_params_and_html(
    backend: SqliteTrackerStore,
    toy_ols_data,
) -> None:
    """OLS.fit().summary() inside km.autolog("statsmodels") emits
    rsquared/aic/bic/llf/f_pvalue metrics + serialized params +
    HTML summary artifact per §3.1 row 6 + §8.1.
    """
    import statsmodels.api as sm

    X, y = toy_ols_data

    async with track("w23g-statsmodels-wiring", backend=backend) as run:
        async with autolog("statsmodels") as handle:
            assert handle.attached_integrations == ("statsmodels",)

            X_const = sm.add_constant(X)
            model = sm.OLS(y, X_const)
            results = model.fit()
            # Trigger the wrapped summary() — metrics fire on call.
            summary_obj = results.summary()
            assert summary_obj is not None
        run_id = run.run_id

    metrics = await backend.list_metrics(run_id)
    artifacts = await backend.list_artifacts(run_id)
    run_row = await backend.get_run(run_id)
    assert run_row is not None
    params = run_row.get("params") or {}

    # Metrics — at minimum rsquared + aic + bic for OLS.
    metric_keys = {row["key"] for row in metrics}
    assert "rsquared" in metric_keys, f"expected rsquared metric, got {metric_keys}"
    assert "aic" in metric_keys, f"expected aic metric, got {metric_keys}"
    assert "bic" in metric_keys, f"expected bic metric, got {metric_keys}"
    # OLS has llf + f_pvalue for non-trivial models.
    assert (
        "llf" in metric_keys or "f_pvalue" in metric_keys
    ), f"expected llf or f_pvalue metric, got {metric_keys}"

    # Params — serialized array under statsmodels.params.
    assert (
        "statsmodels.params" in params
    ), f"expected statsmodels.params key, got {sorted(params.keys())[:10]}"

    # Artifact — HTML summary.
    artifact_names = {row["name"] for row in artifacts}
    assert (
        "statsmodels.summary.html" in artifact_names
    ), f"expected statsmodels.summary.html artifact, got {artifact_names}"


async def test_statsmodels_autolog_restores_summary_on_exit(
    backend: SqliteTrackerStore,
) -> None:
    """Per §3.2 + §1.3: detach MUST restore ``RegressionResults.summary``."""
    from statsmodels.regression.linear_model import RegressionResults

    original_summary = RegressionResults.__dict__["summary"]

    async with track("w23g-statsmodels-restore", backend=backend):
        async with autolog("statsmodels"):
            assert (
                RegressionResults.__dict__["summary"] is not original_summary
            ), "StatsmodelsIntegration.attach did NOT replace RegressionResults.summary"
    assert (
        RegressionResults.__dict__["summary"] is original_summary
    ), "StatsmodelsIntegration.detach did NOT restore RegressionResults.summary; class-level patch LEAKED per §1.3"


async def test_statsmodels_autolog_restores_summary_even_when_body_raises(
    backend: SqliteTrackerStore,
) -> None:
    """Per §8.5 + §3.2: detach runs in ``finally:`` even when the
    wrapped block raises.
    """
    from statsmodels.regression.linear_model import RegressionResults

    original_summary = RegressionResults.__dict__["summary"]

    async with track("w23g-statsmodels-restore-on-raise", backend=backend):
        with pytest.raises(ValueError, match="user body error"):
            async with autolog("statsmodels"):
                raise ValueError("user body error")
    assert (
        RegressionResults.__dict__["summary"] is original_summary
    ), "StatsmodelsIntegration.detach did NOT restore RegressionResults.summary after raising body"
