# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for ``AlignmentDiagnostics``.

Direct behavioural assertions on the adapter's math + Protocol conformance.
Mocking is permitted at Tier 1 (see ``rules/testing.md``).
"""
from __future__ import annotations

import math

import pytest

from kailash.diagnostics.protocols import Diagnostic
from kailash_align.diagnostics import AlignmentDiagnostics


def test_protocol_conformance() -> None:
    """Every adapter exported via ``kailash_align.diagnostics`` MUST pass
    ``isinstance(_, Diagnostic)`` at runtime (the Protocol is
    ``@runtime_checkable``). See ``rules/orphan-detection.md`` §1."""
    diag = AlignmentDiagnostics()
    assert isinstance(diag, Diagnostic)


def test_context_manager() -> None:
    with AlignmentDiagnostics(label="smoke") as diag:
        assert isinstance(diag, AlignmentDiagnostics)
        assert isinstance(diag.run_id, str) and diag.run_id


def test_init_validates_arguments() -> None:
    with pytest.raises(ValueError):
        AlignmentDiagnostics(label="")
    with pytest.raises(ValueError):
        AlignmentDiagnostics(window=0)
    with pytest.raises(ValueError):
        AlignmentDiagnostics(run_id="")


def test_evaluate_pair_length_mismatch_raises() -> None:
    diag = AlignmentDiagnostics()
    with pytest.raises(ValueError):
        diag.evaluate_pair([[0.0]], [[0.0], [0.0]], preferences=[])


def test_evaluate_pair_zero_kl_on_identical_policies() -> None:
    diag = AlignmentDiagnostics()
    df = diag.evaluate_pair(
        base_policy=[[-0.5, -0.5], [-0.3, -0.3]],
        tuned_policy=[[-0.5, -0.5], [-0.3, -0.3]],
        preferences=[
            {"chosen_reward": 1.0, "rejected_reward": 0.5, "chosen_won": True}
        ],
    )
    assert df.height == 1
    assert df["kl_divergence"][0] == pytest.approx(0.0, abs=1e-9)
    assert df["win_rate"][0] == pytest.approx(1.0)
    assert df["reward_margin"][0] == pytest.approx(0.5, abs=1e-9)


def test_evaluate_pair_nonzero_kl_when_policies_diverge() -> None:
    diag = AlignmentDiagnostics()
    df = diag.evaluate_pair(
        base_policy=[[-0.5, -0.5]],
        tuned_policy=[[-1.5, -1.5]],
        preferences=[],
    )
    assert df["kl_divergence"][0] > 0.0
    assert math.isnan(df["win_rate"][0])
    assert math.isnan(df["reward_margin"][0])


def test_win_rate_empty_returns_nan() -> None:
    diag = AlignmentDiagnostics()
    assert math.isnan(diag.win_rate([]))


def test_win_rate_half() -> None:
    diag = AlignmentDiagnostics()
    prefs = [{"chosen_won": True}, {"chosen_won": False}]
    assert diag.win_rate(prefs) == pytest.approx(0.5)


def test_track_training_ingests_dicts() -> None:
    diag = AlignmentDiagnostics(window=100)
    stream = [
        {"step": i, "reward": float(i), "kl": 0.1 * i, "loss": 1.0 / (i + 1)}
        for i in range(10)
    ]
    df = diag.track_training(stream)
    assert df.height == 10
    assert set(df.columns) == {"step", "reward", "kl", "loss"}


def test_track_training_accepts_metrics_stream_object() -> None:
    class FakePipeline:
        def __init__(self, steps: list[dict]) -> None:
            self._steps = steps

        def metrics_stream(self):
            return iter(self._steps)

    diag = AlignmentDiagnostics()
    pipeline = FakePipeline([{"step": 0, "reward": 0.5, "kl": 0.01, "loss": 2.0}])
    df = diag.track_training(pipeline)
    assert df.height == 1


def test_track_training_bounded_window_evicts_old() -> None:
    diag = AlignmentDiagnostics(window=3)
    diag.track_training(
        [{"step": i, "reward": 0.0, "kl": 0.0, "loss": 0.0} for i in range(10)]
    )
    df = diag.training_df()
    # window=3 — oldest evicted
    assert df.height == 3
    assert df["step"].to_list() == [7, 8, 9]


def test_detect_reward_hacking_threshold_must_be_positive() -> None:
    diag = AlignmentDiagnostics()
    with pytest.raises(ValueError):
        diag.detect_reward_hacking(threshold=0)


def test_detect_reward_hacking_empty_history_returns_empty_df() -> None:
    diag = AlignmentDiagnostics()
    df = diag.detect_reward_hacking(history=[])
    assert df.height == 0


def test_detect_reward_hacking_flags_crafted_spike() -> None:
    """Synthetic history: stable rewards + low KL, then a massive reward
    spike co-occurring with KL blow-up. The detector MUST flag it."""
    history = [
        {"step": 0, "reward": 0.1, "kl": 0.01, "loss": 1.0},
        {"step": 1, "reward": 0.12, "kl": 0.01, "loss": 1.0},
        {"step": 2, "reward": 0.11, "kl": 0.01, "loss": 1.0},
        {"step": 3, "reward": 0.13, "kl": 0.01, "loss": 1.0},
        # Spike + KL blowup co-occurrence
        {"step": 4, "reward": 5.0, "kl": 2.5, "loss": 0.1},
    ]
    diag = AlignmentDiagnostics()
    findings = diag.detect_reward_hacking(history=history, threshold=2.0)
    assert findings.height >= 1
    assert 4 in findings["step"].to_list()


def test_report_never_raises_on_empty_state() -> None:
    diag = AlignmentDiagnostics()
    report = diag.report()
    assert isinstance(report, dict)
    assert report["run_id"] == diag.run_id


def test_report_shape_after_full_exercise() -> None:
    diag = AlignmentDiagnostics()
    diag.evaluate_pair([[-0.5]], [[-0.4]], preferences=[{"chosen_won": True}])
    diag.track_training(
        [{"step": i, "reward": 0.5, "kl": 0.05, "loss": 1.0} for i in range(5)]
    )
    report = diag.report()
    assert {"run_id", "pairs", "training_steps"}.issubset(report.keys())
    assert report["pairs"] >= 1
    assert report["training_steps"] >= 5
