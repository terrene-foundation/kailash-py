# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for RL module (without SB3/gymnasium -- unit tier with import guards)."""
from __future__ import annotations

import pytest

from kailash_ml.rl.policies import PolicyRegistry, PolicySpec, PolicyVersion


class TestPolicySpec:
    def test_creation(self):
        spec = PolicySpec(name="test", algorithm="PPO")
        assert spec.name == "test"
        assert spec.algorithm == "PPO"
        assert spec.policy_type == "MlpPolicy"

    def test_to_dict(self):
        spec = PolicySpec(name="test", algorithm="SAC", description="Test policy")
        d = spec.to_dict()
        assert d["name"] == "test"
        assert d["algorithm"] == "SAC"
        assert d["description"] == "Test policy"


class TestPolicyVersion:
    def test_creation(self):
        pv = PolicyVersion(
            name="test",
            version=1,
            algorithm="PPO",
            artifact_path="/tmp/model",
            mean_reward=100.0,
        )
        assert pv.version == 1
        assert pv.mean_reward == 100.0

    def test_to_dict(self):
        pv = PolicyVersion(
            name="test",
            version=2,
            algorithm="DQN",
            artifact_path="/tmp/model",
            std_reward=5.0,
        )
        d = pv.to_dict()
        assert d["version"] == 2
        assert d["algorithm"] == "DQN"


class TestPolicyRegistry:
    def test_register_spec(self):
        reg = PolicyRegistry()
        spec = PolicySpec(name="my-policy", algorithm="PPO")
        reg.register_spec(spec)
        assert "my-policy" in reg
        assert len(reg) == 1

    def test_register_invalid_algorithm(self):
        from kailash_ml.errors import RLError

        reg = PolicyRegistry()
        spec = PolicySpec(name="bad", algorithm="NONEXISTENT")
        with pytest.raises(RLError, match="unknown_algorithm"):
            reg.register_spec(spec)

    def test_register_version(self):
        reg = PolicyRegistry()
        spec = PolicySpec(name="my-policy", algorithm="PPO")
        reg.register_spec(spec)
        pv = PolicyVersion(
            name="my-policy",
            version=1,
            algorithm="PPO",
            artifact_path="/tmp/model",
            mean_reward=200.0,
        )
        reg.register_version(pv)
        assert reg.get_latest_version("my-policy") == pv

    def test_get_version(self):
        reg = PolicyRegistry()
        pv1 = PolicyVersion(
            name="p", version=1, algorithm="PPO", artifact_path="/tmp/1"
        )
        pv2 = PolicyVersion(
            name="p", version=2, algorithm="PPO", artifact_path="/tmp/2"
        )
        reg.register_version(pv1)
        reg.register_version(pv2)
        assert reg.get_version("p", 1) == pv1
        assert reg.get_version("p", 2) == pv2
        assert reg.get_version("p", 3) is None

    def test_latest_version(self):
        reg = PolicyRegistry()
        pv1 = PolicyVersion(
            name="p", version=1, algorithm="PPO", artifact_path="/tmp/1"
        )
        pv2 = PolicyVersion(
            name="p", version=3, algorithm="PPO", artifact_path="/tmp/3"
        )
        reg.register_version(pv1)
        reg.register_version(pv2)
        assert reg.get_latest_version("p").version == 3

    def test_list_specs(self):
        reg = PolicyRegistry()
        reg.register_spec(PolicySpec(name="a", algorithm="PPO"))
        reg.register_spec(PolicySpec(name="b", algorithm="SAC"))
        assert len(reg.list_specs()) == 2

    def test_supported_algorithms(self):
        algos = PolicyRegistry.supported_algorithms()
        # 1.0 canonical names are lowercased; uppercase aliases resolve
        # via the adapter registry but are not in the supported list.
        assert "ppo" in algos
        assert "sac" in algos
        assert "dqn" in algos

    def test_contains(self):
        reg = PolicyRegistry()
        reg.register_spec(PolicySpec(name="x", algorithm="PPO"))
        assert "x" in reg
        assert "y" not in reg


class TestRLTrainerImportGuard:
    """Verify RLTrainer gives clear ImportError without SB3."""

    def test_rl_trainer_importable(self):
        from kailash_ml.rl.trainer import RLTrainer, RLTrainingConfig, RLTrainingResult

        assert RLTrainer is not None
        config = RLTrainingConfig()
        assert config.algorithm == "PPO"
        assert config.total_timesteps == 100_000


class TestEnvironmentRegistryImportGuard:
    def test_env_registry_importable(self):
        from kailash_ml.rl.envs import EnvironmentRegistry, EnvironmentSpec

        spec = EnvironmentSpec(name="Test-v0", entry_point="test:TestEnv")
        assert spec.name == "Test-v0"
        d = spec.to_dict()
        assert d["entry_point"] == "test:TestEnv"
