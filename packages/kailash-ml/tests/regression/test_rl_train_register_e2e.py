# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: W6-015 (F-E1-38) — RLTrainingResult schema parity.

Per ``specs/ml-rl-core.md`` §3.2 ``RLTrainingResult ⊂ TrainingResult`` —
a `km.rl_train(...) → registered = ...` pipeline MUST execute end-to-end
against real SB3 + Gymnasium and the returned envelope MUST carry every
spec-required field:

* ``algorithm``, ``env_spec``, ``total_timesteps`` (RL-required)
* ``episode_reward_mean``, ``episode_reward_std``, ``episode_length_mean``
* ``policy_entropy``, ``value_loss``, ``kl_divergence``,
  ``explained_variance``, ``replay_buffer_size`` (algorithm-dependent — None
  when not applicable, never hallucinated zero per
  ``rules/zero-tolerance.md`` Rule 2)
* ``total_env_steps``
* ``episodes`` (list[EpisodeRecord]) — non-empty when at least one
  rollout completed
* ``eval_history`` (list[EvalRecord])
* ``policy_artifact`` (PolicyArtifactRef) — path + SHA + algorithm

The Tier-2 contract: real SB3 PPO on CartPole-v1; minimal timesteps
(2048 = one rollout) so the test runs in ~5–10s. This is the DOCS-EXACT
canonical pipeline regression — per ``rules/testing.md`` §
"End-to-End Pipeline Regression", the pipeline is exercised through the
public surface, not through the internal trainer class.

Failure modes this test catches:

* The advertised RL training pipeline ships missing one or more of the
  8 fields F-E1-38 enumerated, breaking every downstream registry /
  lineage / dashboard consumer that reads them.
* The kailash-align bridge construction sites drift from the canonical
  spec §3.2 schema and start passing legacy ``mean_reward`` /
  ``std_reward`` / ``env_name`` only.
* The 8 spec-required fields are accepted but populated with zero
  defaults instead of None (Rule 2 violation — fake data).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("stable_baselines3")
pytest.importorskip("gymnasium")


@pytest.mark.regression
def test_w6_015_rl_train_returns_spec_3_2_compliant_result(tmp_path) -> None:
    """Spec §3.2 — ``km.rl_train`` returns RLTrainingResult ⊂ TrainingResult.

    Asserts EVERY spec-required field is present on the returned envelope
    AND populated correctly per the spec's "MAY be None when not
    applicable; MUST NOT be hallucinated zero" invariant.
    """
    from kailash_ml.rl import EpisodeRecord, RLTrainingResult, rl_train
    from kailash_ml.rl.protocols import PolicyArtifactRef

    result = rl_train(
        "CartPole-v1",
        algo="ppo",
        total_timesteps=2048,
        hyperparameters={"n_steps": 512},
        seed=42,
        register_as="w6-015-regression-ppo",
        root_dir=str(tmp_path / "artifacts"),
    )

    # --- Type identity --------------------------------------------------
    assert isinstance(result, RLTrainingResult)

    # --- Spec §3.2 RL-required fields (typed, not in metrics dict) ------
    assert result.algorithm == "ppo"
    assert result.env_spec == "CartPole-v1"
    assert result.total_timesteps == 2048

    # episode_reward_* / episode_length_mean populated from eval rollout
    # + ep_info_buffer. Finite floats; reward_std MAY be 0 for fully-
    # converged eval but is not None.
    assert isinstance(result.episode_reward_mean, float)
    assert isinstance(result.episode_reward_std, float)
    assert isinstance(result.episode_length_mean, float)
    assert result.episode_length_mean >= 0.0

    # total_env_steps reflects model.num_timesteps post-training.
    assert isinstance(result.total_env_steps, int)
    assert result.total_env_steps >= 2048

    # --- Spec §3.2 algorithm-dependent fields (None when N/A) -----------
    # PPO is on-policy actor-critic — kl_divergence + value_loss SHOULD
    # be populated after at least one update fires; replay_buffer_size
    # MUST be None (PPO has no replay buffer per spec).
    assert (
        result.kl_divergence is not None
    ), "PPO should populate kl_divergence after at least one update"
    assert isinstance(result.kl_divergence, float)
    # replay_buffer_size MUST be None for on-policy algos per spec §3.2
    # ("MUST NOT be hallucinated zero" — None signals N/A explicitly).
    assert result.replay_buffer_size is None, (
        "on-policy PPO must report replay_buffer_size=None, not 0 — "
        "spec §3.2 invariant 3 (Rule 2 — no fake data)."
    )
    # policy_entropy / value_loss / explained_variance: SB3 PPO logs
    # these intermittently; they MAY be None on very short runs OR
    # populated as floats.
    assert result.policy_entropy is None or isinstance(result.policy_entropy, float)
    assert result.value_loss is None or isinstance(result.value_loss, float)
    assert result.explained_variance is None or isinstance(
        result.explained_variance, float
    )

    # --- Spec §3.2 typed records ----------------------------------------
    # episodes MUST be non-empty when at least one rollout completed
    # (CartPole episodes are short, several complete within 2048 steps).
    assert isinstance(result.episodes, list)
    assert len(result.episodes) >= 1, (
        "at least one EpisodeRecord must be present when a rollout "
        "completed — spec §3.2 invariant 1 (Rule 2 violation otherwise)."
    )
    for ep in result.episodes:
        assert isinstance(ep, EpisodeRecord)
        assert isinstance(ep.episode_index, int)
        assert isinstance(ep.reward, float)
        assert isinstance(ep.length, int)
        assert ep.length > 0
        assert isinstance(ep.timestamp, datetime)

    # eval_history is a list (may be empty for very short runs without
    # eval_freq elapsing — the trainer doesn't currently wire EvalCallback).
    assert isinstance(result.eval_history, list)

    # policy_artifact: spec §3.2 — path + SHA + algorithm
    assert (
        result.policy_artifact is not None
    ), "policy_artifact must be populated when artifact_path is set"
    assert isinstance(result.policy_artifact, PolicyArtifactRef)
    assert isinstance(result.policy_artifact.path, Path)
    assert result.policy_artifact.algorithm == "ppo"
    assert isinstance(result.policy_artifact.sha, str)
    assert len(result.policy_artifact.sha) == 64  # sha256 hex digest

    # --- Spec §3.2 inherited TrainingResult fields ----------------------
    # (RLTrainingResult ⊂ TrainingResult — these fields are the inherited
    # surface per the spec's subset relationship.)
    assert isinstance(result.metrics, dict)
    assert isinstance(result.elapsed_seconds, float)
    assert result.elapsed_seconds >= 0.0
    assert isinstance(result.artifact_uris, dict)
    assert "sb3" in result.artifact_uris


@pytest.mark.regression
def test_w6_015_back_compat_aliases_resolve_to_canonical_fields() -> None:
    """Spec-rename back-compat — pre-1.2.0 callers using mean_reward /
    std_reward / training_time_seconds / env_name continue to read
    correct values via the dataclass back-compat properties.

    Closes the "construction-sites swept but readers stale" bug class
    per ``rules/security.md`` § "Multi-Site Kwarg Plumbing".
    """
    from kailash_ml.rl import RLTrainingResult

    # Construct with canonical kwargs (post-W6-015 callers).
    canonical = RLTrainingResult(
        algorithm="ppo",
        env_spec="CartPole-v1",
        total_timesteps=100,
        episode_reward_mean=42.5,
        episode_reward_std=3.2,
        episode_length_mean=200.0,
        elapsed_seconds=1.25,
    )
    # Legacy readers see the same values.
    assert canonical.mean_reward == 42.5
    assert canonical.std_reward == 3.2
    assert canonical.training_time_seconds == 1.25
    assert canonical.env_name == "CartPole-v1"

    # Construct with legacy kwargs (pre-W6-015 callers).
    legacy = RLTrainingResult(
        policy_name="legacy-policy",
        algorithm="dpo",
        total_timesteps=50,
        mean_reward=7.0,
        std_reward=0.5,
        training_time_seconds=2.0,
        env_name="text:preferences",
    )
    # Canonical readers see the same values.
    assert legacy.episode_reward_mean == 7.0
    assert legacy.episode_reward_std == 0.5
    assert legacy.elapsed_seconds == 2.0
    assert legacy.env_spec == "text:preferences"


@pytest.mark.regression
def test_w6_015_to_dict_carries_canonical_and_back_compat_keys() -> None:
    """Wire-format parity — to_dict() emits canonical spec §3.2 keys
    AND back-compat aliases so cross-SDK consumers (kailash-rs, kailash-
    align registry readers) see both surfaces during the transition.
    """
    from kailash_ml.rl import RLTrainingResult

    result = RLTrainingResult(
        algorithm="ppo",
        env_spec="CartPole-v1",
        total_timesteps=100,
        episode_reward_mean=42.0,
        episode_reward_std=3.0,
        episode_length_mean=200.0,
        elapsed_seconds=1.5,
    )
    payload = result.to_dict()
    # Canonical keys per spec §3.2
    assert payload["algorithm"] == "ppo"
    assert payload["env_spec"] == "CartPole-v1"
    assert payload["episode_reward_mean"] == 42.0
    assert payload["episode_reward_std"] == 3.0
    assert payload["episode_length_mean"] == 200.0
    assert payload["elapsed_seconds"] == 1.5
    # Spec §3.2 algorithm-dependent — None means "not applicable"
    assert payload["policy_entropy"] is None
    assert payload["value_loss"] is None
    assert payload["kl_divergence"] is None
    assert payload["explained_variance"] is None
    assert payload["replay_buffer_size"] is None
    # Spec §3.2 typed-record lists (empty by default)
    assert payload["episodes"] == []
    assert payload["eval_history"] == []
    assert payload["policy_artifact"] is None
    # Back-compat keys preserved for cross-SDK consumers during transition
    assert payload["mean_reward"] == 42.0
    assert payload["std_reward"] == 3.0
    assert payload["training_time_seconds"] == 1.5
    assert payload["env_name"] == "CartPole-v1"
