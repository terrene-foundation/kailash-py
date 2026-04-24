# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring — RLTrainer end-to-end through PolicyRegistry.

Per ``rules/facade-manager-detection.md`` §1, every manager-shape class
(RLTrainer, EnvironmentRegistry, PolicyRegistry) requires a Tier-2 test
that:

1. Imports the class through the framework facade (``kailash_ml.rl.*``).
2. Constructs a real env (``gymnasium.make("CartPole-v1")``).
3. Runs a real training loop on real SB3 (no mocks).
4. Asserts the externally-observable effect — an RLTrainingResult with
   populated metrics + a registry row + a saved artifact.

The timestep count is intentionally small (2048 timesteps = 1 PPO rollout +
some updates) so the test completes in ~5-10s on CI. This is a
smoke-level test: we assert metrics parity and wiring, not convergence.
A dedicated convergence test (10K steps, reward > threshold) lives
in ``tests/bench/`` and is triggered by the CI-slow job.
"""
from __future__ import annotations

import pytest

pytest.importorskip("stable_baselines3")
pytest.importorskip("gymnasium")


@pytest.mark.integration
def test_rl_trainer_trains_ppo_and_registers_policy(tmp_path) -> None:
    """End-to-end: RLTrainer + PolicyRegistry + EnvironmentRegistry.

    Exercises every manager-shape class through its facade; asserts the
    externally-observable effects (metrics keys populated, artifact on
    disk, registry version stored).
    """
    from kailash_ml.rl import (
        EnvironmentRegistry,
        PolicyRegistry,
        RLTrainer,
        RLTrainingConfig,
        RLTrainingResult,
    )
    from kailash_ml.rl.trainer import METRIC_KEYS

    env_registry = EnvironmentRegistry(tenant_id="tenant-smoke")
    policy_registry = PolicyRegistry(
        root_dir=tmp_path / "policies", tenant_id="tenant-smoke"
    )
    trainer = RLTrainer(
        env_registry=env_registry,
        policy_registry=policy_registry,
        root_dir=tmp_path / "artifacts",
        tenant_id="tenant-smoke",
    )

    # Minimal config — 2048 steps = 1 PPO rollout so updates fire once.
    # n_eval_episodes=3 keeps the eval loop short.
    config = RLTrainingConfig(
        algorithm="ppo",
        total_timesteps=2048,
        n_eval_episodes=3,
        seed=42,
    )
    result = trainer.train("CartPole-v1", "smoke-ppo", config=config)

    # --- Result shape (W29 invariant #4 — metric parity) -----------------
    assert isinstance(result, RLTrainingResult)
    assert result.algorithm == "ppo"
    assert result.total_timesteps == 2048
    assert result.policy_name == "smoke-ppo"
    assert result.env_name == "CartPole-v1"
    for key in METRIC_KEYS:
        assert key in result.metrics, f"missing metric parity key: {key}"

    # reward_mean MUST be finite (may be pre-training-episode value but
    # exists) — proves the callback ran at least once.
    assert result.metrics["reward_mean"] is not None
    # reward_std always populated from eval rollouts.
    assert result.metrics["reward_std"] is not None
    # PPO MUST populate kl and clip_frac after at least one update.
    assert result.metrics["kl"] is not None, "PPO should log train/approx_kl"
    assert result.metrics["clip_frac"] is not None, "PPO should log train/clip_fraction"

    # --- Reward curve populated ------------------------------------------
    assert len(result.reward_curve) >= 1
    for step, reward in result.reward_curve:
        assert isinstance(step, int) and step > 0
        assert isinstance(reward, float)

    # --- Artifact persisted ----------------------------------------------
    assert result.artifact_path is not None
    # SB3 adds ".zip" to the save path under the hood.
    from pathlib import Path

    saved = Path(result.artifact_path)
    assert saved.with_suffix(".zip").exists() or saved.exists()

    # --- Policy registry captured the version ---------------------------
    versions = policy_registry.list_versions("smoke-ppo")
    assert len(versions) == 1
    version = versions[0]
    assert version.version == 1
    assert version.algorithm == "ppo"
    assert version.total_timesteps == 2048
    assert version.mean_reward is not None

    # Spec was auto-created by the trainer.
    spec = policy_registry.get_spec("smoke-ppo")
    assert spec is not None
    assert spec.algorithm == "ppo"


@pytest.mark.integration
def test_rl_train_module_entry_trains_end_to_end(tmp_path) -> None:
    """``km.rl_train`` (via kailash_ml.rl.rl_train) trains successfully."""
    from kailash_ml.rl import rl_train

    result = rl_train(
        "CartPole-v1",
        algo="ppo",
        total_timesteps=2048,
        hyperparameters={"n_steps": 512},  # smaller rollout -> faster test
        seed=42,
        register_as="rl-train-smoke",
        root_dir=str(tmp_path / "artifacts"),
    )
    assert result.algorithm == "ppo"
    assert result.policy_name == "rl-train-smoke"
    assert result.metrics["reward_mean"] is not None
    assert result.metrics["kl"] is not None


@pytest.mark.integration
def test_env_registry_wiring_resolves_standard_gym_env() -> None:
    """EnvironmentRegistry resolves standard gym ids via make()."""
    from kailash_ml.rl import EnvironmentRegistry

    reg = EnvironmentRegistry(tenant_id="tenant-test")
    env = reg.make("CartPole-v1")
    try:
        obs, info = env.reset(seed=0)
        assert obs is not None
        # action_space.n = 2 for CartPole
        assert env.action_space.n == 2
    finally:
        env.close()


@pytest.mark.integration
def test_policy_registry_reward_registry_round_trip() -> None:
    """register_reward + get_reward round-trips a user callable."""
    from kailash_ml.rl import PolicyRegistry

    def dense_reward(obs, action, next_obs, env_info):
        return 1.0 if env_info.get("success") else 0.0

    reg = PolicyRegistry(tenant_id="tenant-test")
    reg.register_reward("success-dense", dense_reward)
    assert reg.get_reward("success-dense") is dense_reward
    assert "success-dense" in reg.list_rewards()
