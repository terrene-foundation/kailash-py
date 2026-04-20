# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for ``AlignmentDiagnostics``.

Per ``rules/orphan-detection.md`` §1 these tests import the adapter via
the package facade (``from kailash_align.diagnostics import
AlignmentDiagnostics``) and exercise a realistic training-session
sequence end-to-end against real polars + plotly — no mocks.

See ``rules/testing.md`` § "Tier 2 (Integration): Real infrastructure
recommended".
"""
from __future__ import annotations

import math

import polars as pl
import pytest

from kailash.diagnostics.protocols import Diagnostic
from kailash_align.diagnostics import AlignmentDiagnostics


@pytest.mark.integration
def test_facade_import_protocol_conformance() -> None:
    """The facade import path MUST return a Diagnostic-conforming object."""
    diag = AlignmentDiagnostics(label="integ_run")
    assert isinstance(diag, Diagnostic)
    assert diag.run_id and isinstance(diag.run_id, str)


@pytest.mark.integration
def test_full_session_end_to_end() -> None:
    """Exercise evaluate_pair → track_training → detect_reward_hacking →
    report() in a single session and assert each externally-observable
    effect survives the round-trip."""
    # Realistic fixture — 16 tokens per example, 3 preference pairs.
    base_policy = [[-0.4, -0.3, -0.5, -0.6] * 4 for _ in range(3)]
    tuned_policy = [[-0.5, -0.4, -0.4, -0.5] * 4 for _ in range(3)]
    preferences = [
        {"chosen_reward": 0.8, "rejected_reward": 0.2, "chosen_won": True},
        {"chosen_reward": 0.6, "rejected_reward": 0.5, "chosen_won": True},
        {"chosen_reward": 0.4, "rejected_reward": 0.7, "chosen_won": False},
    ]

    # Crafted training stream with a late reward-hacking spike.
    training = [
        {"step": i, "reward": 0.5 + 0.01 * i, "kl": 0.05, "loss": 1.0 / (i + 1)}
        for i in range(20)
    ]
    training.append({"step": 20, "reward": 8.0, "kl": 4.0, "loss": 0.05})

    with AlignmentDiagnostics(label="integ_run") as diag:
        pair_df = diag.evaluate_pair(base_policy, tuned_policy, preferences)
        tr_df = diag.track_training(training)
        finds = diag.detect_reward_hacking(threshold=2.0)
        report = diag.report()

    # evaluate_pair emitted one reading
    assert pair_df.height == 1
    assert pair_df["kl_divergence"][0] >= 0.0
    # track_training captured every step
    assert tr_df.height == 21
    # detect_reward_hacking caught the crafted spike
    assert finds.height >= 1
    # report() contains session correlation + counts
    assert report["run_id"] == diag.run_id
    assert report["pairs"] >= 1
    assert report["training_steps"] >= 20
    assert report["reward_hacking_findings"] >= 1


@pytest.mark.integration
def test_accessors_return_polars_dataframes() -> None:
    diag = AlignmentDiagnostics()
    diag.track_training(
        [{"step": i, "reward": 0.5, "kl": 0.1, "loss": 1.0} for i in range(5)]
    )
    assert isinstance(diag.training_df(), pl.DataFrame)
    assert isinstance(diag.pair_df(), pl.DataFrame)
    assert isinstance(diag.findings_df(), pl.DataFrame)


@pytest.mark.integration
def test_plot_training_curves_returns_plotly_figure() -> None:
    """``plot_training_curves`` returns a plotly Figure that survives
    the empty-data path without raising."""
    import plotly.graph_objects as go

    diag = AlignmentDiagnostics()
    # Empty case — should return titled placeholder figure
    empty_fig = diag.plot_training_curves()
    assert isinstance(empty_fig, go.Figure)

    # Non-empty case
    diag.track_training(
        [{"step": i, "reward": 0.5, "kl": 0.1, "loss": 1.0} for i in range(4)]
    )
    fig = diag.plot_training_curves()
    assert isinstance(fig, go.Figure)
    # Two traces — reward + kl
    assert len(list(fig.data)) == 2


@pytest.mark.integration
def test_identical_policy_yields_zero_kl() -> None:
    """Sanity check on the math end-to-end through real polars."""
    diag = AlignmentDiagnostics()
    base = [[-0.7, -0.8, -0.9] for _ in range(5)]
    df = diag.evaluate_pair(base, base, preferences=[])
    assert df["kl_divergence"][0] == pytest.approx(0.0, abs=1e-9)
    # Empty preferences → NaN margin + win_rate
    assert math.isnan(df["win_rate"][0])


@pytest.mark.integration
def test_run_id_correlation_surfaces_in_report() -> None:
    diag = AlignmentDiagnostics(run_id="explicit-integ-run-xyz")
    assert diag.run_id == "explicit-integ-run-xyz"
    report = diag.report()
    assert report["run_id"] == "explicit-integ-run-xyz"
