# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for ``RLDiagnostics``.

Tests the class surface in isolation (no SB3 required):

  - Constructor validation (window / run_id / collapse-fraction bounds).
  - Metric-namespace schema — every ``record_*`` path emits the exact
    spec §8.5 key names.
  - ``record_policy_update(clip_fraction=None)`` MUST NOT emit
    ``rl.policy.clip_fraction`` (§ 8.2.5 "never hallucinate zero").
  - ``report()`` surfaces an ``episode_reward_collapse`` CRIT finding
    when the rolling window drops from peak.
  - ``Diagnostic`` Protocol conformance via ``isinstance``.

Tier 2 wiring against a real SB3 PPO rollout lives in
``tests/integration/test_rl_diagnostics_wiring.py`` per
``rules/orphan-detection.md §2`` + ``facade-manager-detection.md §2``.
"""
from __future__ import annotations

from typing import Any

import pytest

from kailash.diagnostics.protocols import Diagnostic

# Import through the facade — NOT ``kailash_ml.diagnostics.rl`` — so the
# wiring test catches an orphan facade attribute if the public surface
# drifts (rules/orphan-detection.md §1).
from kailash_ml.diagnostics import RLDiagnostics, RLDiagnosticFinding


class _RecordingTracker:
    """Deterministic-adapter tracker for Tier-1 tests.

    Not a mock — this is a real implementation of the duck-typed
    ``log_metric(key, value, *, step=None)`` contract that RLDiagnostics
    accepts.  Pure data recorder with no decision logic; satisfies the
    Tier-2 "Protocol-satisfying deterministic adapter" carve-out from
    ``rules/testing.md`` when reused in wiring tests.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, float, Any]] = []

    def log_metric(self, key: str, value: float, *, step: Any = None) -> None:
        self.calls.append((key, value, step))


# ---------------------------------------------------------------------------
# Construction + Protocol conformance
# ---------------------------------------------------------------------------


def test_rl_diagnostics_satisfies_diagnostic_protocol() -> None:
    """Protocol conformance is part of the cross-SDK contract (issue #567)."""
    diag = RLDiagnostics(algo="ppo")
    assert isinstance(diag, Diagnostic)
    assert diag.run_id  # non-empty string
    with diag:
        assert isinstance(diag.report(), dict)


def test_rl_diagnostics_rejects_window_below_two() -> None:
    with pytest.raises(ValueError, match="window must be >= 2"):
        RLDiagnostics(window=1)


def test_rl_diagnostics_rejects_empty_run_id() -> None:
    with pytest.raises(ValueError, match="run_id"):
        RLDiagnostics(run_id="")


def test_rl_diagnostics_rejects_out_of_range_collapse_fraction() -> None:
    with pytest.raises(ValueError, match="collapse_drop_fraction"):
        RLDiagnostics(collapse_drop_fraction=1.5)
    with pytest.raises(ValueError, match="collapse_peak_fraction"):
        RLDiagnostics(collapse_peak_fraction=0.0)


def test_rl_diagnostics_algo_lowercased() -> None:
    """Allows case-insensitive construction; normalised for downstream filters."""
    diag = RLDiagnostics(algo="PPO")
    assert diag.algo == "ppo"


# ---------------------------------------------------------------------------
# Metric namespace — spec §8.5
# ---------------------------------------------------------------------------


def test_record_episode_emits_reward_and_length_keys() -> None:
    tracker = _RecordingTracker()
    diag = RLDiagnostics(tracker=tracker)
    diag.record_episode(reward=1.0, length=50)
    keys = {call[0] for call in tracker.calls}
    assert "rl.episode.reward" in keys
    assert "rl.episode.length" in keys


def test_record_policy_update_omits_clip_fraction_when_none() -> None:
    """PPO's clip_fraction MUST NOT be hallucinated for non-PPO algos (§8.2.5)."""
    tracker = _RecordingTracker()
    diag = RLDiagnostics(algo="sac", tracker=tracker)
    diag.record_policy_update(loss=0.1, kl=0.02, entropy=0.5, clip_fraction=None)
    keys = [call[0] for call in tracker.calls]
    assert "rl.policy.loss" in keys
    assert "rl.policy.kl_from_ref" in keys
    assert "rl.policy.entropy" in keys
    assert "rl.policy.clip_fraction" not in keys


def test_record_policy_update_ppo_emits_clip_fraction() -> None:
    tracker = _RecordingTracker()
    diag = RLDiagnostics(algo="ppo", tracker=tracker)
    diag.record_policy_update(loss=0.1, kl=0.02, entropy=0.5, clip_fraction=0.18)
    assert ("rl.policy.clip_fraction", 0.18, 0) in tracker.calls


def test_record_value_and_q_updates_emit_correct_keys() -> None:
    tracker = _RecordingTracker()
    diag = RLDiagnostics(tracker=tracker)
    diag.record_policy_update(loss=0.1)  # advances update counter
    diag.record_value_update(loss=0.05, explained_variance=0.6)
    diag.record_q_update(loss=0.2, overestimation_gap=0.04)
    keys = {call[0] for call in tracker.calls}
    assert "rl.value.loss" in keys
    assert "rl.value.explained_variance" in keys
    assert "rl.q.loss" in keys
    assert "rl.q.overestimation_gap" in keys


def test_record_replay_emits_size_key() -> None:
    tracker = _RecordingTracker()
    diag = RLDiagnostics(tracker=tracker)
    diag.record_replay(size=4096)
    assert ("rl.replay.size", 4096.0, 0) in tracker.calls


def test_record_eval_rollout_emits_reward_and_length() -> None:
    tracker = _RecordingTracker()
    diag = RLDiagnostics(tracker=tracker)
    diag.record_eval_rollout(reward=200.0, length=500, deterministic=True)
    keys = {call[0] for call in tracker.calls}
    assert "rl.eval.reward" in keys
    assert "rl.eval.length" in keys


def test_record_eval_stochastic_emits_warn(caplog: pytest.LogCaptureFixture) -> None:
    """§8.2.8 — stochastic eval MUST emit WARN for dashboard drill-down."""
    diag = RLDiagnostics()
    with caplog.at_level("WARNING", logger="kailash_ml.diagnostics.rl"):
        diag.record_eval_rollout(reward=1.0, length=10, deterministic=False)
    assert any("stochastic_eval_warning" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Reward-collapse finding — spec §8.7 + RLHF parity §6
# ---------------------------------------------------------------------------


def test_report_flags_reward_collapse_as_crit() -> None:
    """Rolling-window drop from peak + below-peak threshold → CRIT finding.

    Reward-collapse at CRIT matches kailash-align's RLHF reward-hacking
    finding (``specs/ml-rl-align-unification.md §6``) so one dashboard
    alert filter catches both classical and RLHF training failures.
    """
    diag = RLDiagnostics(
        window=10, collapse_drop_fraction=0.5, collapse_peak_fraction=0.1
    )
    # Fill window: peak at 200, then collapse to 5 (below 10% of peak).
    for _ in range(5):
        diag.record_episode(reward=200.0, length=500)
    for _ in range(5):
        diag.record_episode(reward=5.0, length=20)
    report = diag.report()
    findings = report["findings"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "CRIT"
    assert findings[0]["category"] == "episode_reward_collapse"


def test_report_no_collapse_when_window_not_full() -> None:
    diag = RLDiagnostics(window=100)
    for _ in range(10):
        diag.record_episode(reward=1.0, length=5)
    report = diag.report()
    assert report["findings"] == []


def test_report_schema_stable_empty() -> None:
    """``report()`` MUST NOT raise on an empty session."""
    diag = RLDiagnostics()
    report = diag.report()
    assert report["run_id"] == diag.run_id
    assert report["kind"] == "rl"
    assert report["metrics"]["episode_count"] == 0
    assert report["findings"] == []


def test_rl_diagnostic_finding_is_frozen() -> None:
    f = RLDiagnosticFinding(severity="CRIT", category="x", message="y")
    with pytest.raises(Exception):
        f.severity = "HIGH"  # type: ignore[misc]
