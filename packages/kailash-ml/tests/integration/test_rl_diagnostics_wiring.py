# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for ``RLDiagnostics``.

Per ``rules/orphan-detection.md §1`` + ``rules/facade-manager-detection.md
§2``, this file imports ``RLDiagnostics`` through the
``kailash_ml.diagnostics`` facade (NOT the concrete module path) and
drives a real Stable-Baselines3 PPO rollout against a real
``gymnasium.CartPole-v1`` env so we assert externally-observable
effects of the SB3 callback wiring rather than mocked internals.

The file also checks Protocol conformance at runtime — the whole
point of the PR is for ``isinstance(diag, Diagnostic)`` to hold, so a
plain unit test of the class in isolation would prove the class-shape
contract but NOT the Protocol-conformance + SB3-integration contract
that downstream consumers rely on.

Requires the ``[rl]`` extra: ``pip install kailash-ml[rl]``.
"""
from __future__ import annotations

import pytest

sb3 = pytest.importorskip("stable_baselines3", reason="requires kailash-ml[rl]")
gym = pytest.importorskip("gymnasium", reason="requires kailash-ml[rl]")

from kailash.diagnostics.protocols import Diagnostic  # noqa: E402

# Import through the facade — NOT ``from kailash_ml.diagnostics.rl import ...``
# per orphan-detection §1 (downstream consumers see the public attribute,
# so the wiring test MUST exercise the same surface).
from kailash_ml.diagnostics import RLDiagnostics  # noqa: E402


class _RecordingTracker:
    """Deterministic-adapter tracker satisfying the duck-typed
    ``log_metric(key, value, *, step=None)`` contract.

    Real implementation (not a mock) per ``rules/testing.md`` § Tier 2
    "Protocol-Satisfying Deterministic Adapters Are Not Mocks":
    pure data recorder, no decision logic, produces deterministic
    output from its inputs.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, float, object]] = []

    def log_metric(self, key: str, value: float, *, step: object = None) -> None:
        self.calls.append((key, value, step))


@pytest.mark.integration
def test_rldiagnostics_satisfies_protocol_through_facade() -> None:
    """Orphan gate: ``RLDiagnostics`` MUST be reachable via the facade."""
    diag = RLDiagnostics(algo="ppo")
    assert isinstance(diag, Diagnostic)


@pytest.mark.integration
def test_rldiagnostics_sb3_ppo_rollout_emits_rl_metrics() -> None:
    """Real SB3 PPO rollout writes ``rl.*`` metrics to the tracker.

    Asserts the wiring contract from ``specs/ml-rl-core.md §7.1`` — the
    SB3 ``BaseCallback`` hook drives ``record_episode`` +
    ``record_policy_update`` + ``record_value_update`` end-to-end.
    A miswired callback (e.g. no ``_on_step`` implementation, no
    ``_on_rollout_end``) would leave the tracker's call list empty, so
    this is the orphan-detection structural gate per
    ``rules/facade-manager-detection.md §1``.
    """
    env = gym.make("CartPole-v1")
    tracker = _RecordingTracker()

    with RLDiagnostics(algo="ppo", tracker=tracker) as diag:
        # Tiny PPO — just enough to trigger at least one rollout_end.
        # n_steps=32, n_epochs=1 keeps the test under a few seconds.
        model = sb3.PPO(
            "MlpPolicy", env, n_steps=32, batch_size=32, n_epochs=1, verbose=0
        )
        model.learn(total_timesteps=64, callback=diag.as_sb3_callback())

    keys = {call[0] for call in tracker.calls}
    # Episode metrics land from Monitor wrapper's `infos`.
    assert "rl.episode.reward" in keys
    assert "rl.episode.length" in keys
    # Policy + value updates land at _on_rollout_end.
    assert "rl.policy.loss" in keys
    assert "rl.policy.kl_from_ref" in keys
    assert "rl.policy.entropy" in keys
    assert "rl.policy.clip_fraction" in keys  # PPO-family emits this
    assert "rl.value.loss" in keys

    # Report reflects the accumulated state — episode_count comes from
    # Monitor info events, update_count from _on_rollout_end.
    report = diag.report()
    assert report["kind"] == "rl"
    assert report["algo"] == "ppo"
    assert report["metrics"]["episode_count"] >= 1
    assert report["metrics"]["update_count"] >= 1
    assert report["metrics"]["episode_reward_peak"] is not None


@pytest.mark.integration
def test_rldiagnostics_sb3_off_policy_records_replay_size() -> None:
    """DQN (off-policy) populates replay-buffer size per step.

    The SB3 callback reads ``self.model.replay_buffer.size()`` /
    ``.pos`` inside ``_on_step`` so a real off-policy rollout must
    produce ``rl.replay.size`` emissions — on-policy algorithms
    (PPO / A2C) have no ``replay_buffer`` attribute and the callback
    gracefully skips the emission.
    """
    env = gym.make("CartPole-v1")
    tracker = _RecordingTracker()

    with RLDiagnostics(algo="dqn", tracker=tracker) as diag:
        # Tiny DQN — learning_starts=0 so replay fills immediately.
        model = sb3.DQN(
            "MlpPolicy",
            env,
            buffer_size=1_000,
            learning_starts=0,
            batch_size=32,
            verbose=0,
        )
        model.learn(total_timesteps=64, callback=diag.as_sb3_callback())

    keys = {call[0] for call in tracker.calls}
    assert "rl.replay.size" in keys
    # Replay sizes grow monotonically across steps.
    sizes = [call[1] for call in tracker.calls if call[0] == "rl.replay.size"]
    assert sizes[-1] >= sizes[0]
