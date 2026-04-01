# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""RLTrainer -- Stable-Baselines3 wrapper for RL training lifecycle.

Requires ``pip install kailash-ml[rl]`` (stable-baselines3, gymnasium, torch).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["RLTrainer", "RLTrainingConfig", "RLTrainingResult"]


@dataclass
class RLTrainingConfig:
    """Configuration for RL training."""

    algorithm: str = "PPO"  # "PPO", "SAC", "DQN", "A2C", "TD3", "DDPG"
    policy_type: str = "MlpPolicy"
    total_timesteps: int = 100_000
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    n_eval_episodes: int = 10
    eval_freq: int = 10_000
    seed: int | None = 42
    verbose: int = 0
    save_path: str | Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "policy_type": self.policy_type,
            "total_timesteps": self.total_timesteps,
            "hyperparameters": self.hyperparameters,
            "n_eval_episodes": self.n_eval_episodes,
            "eval_freq": self.eval_freq,
            "seed": self.seed,
        }


@dataclass
class RLTrainingResult:
    """Result of an RL training run."""

    policy_name: str
    algorithm: str
    total_timesteps: int
    mean_reward: float
    std_reward: float
    training_time_seconds: float
    artifact_path: str | None = None
    eval_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_name": self.policy_name,
            "algorithm": self.algorithm,
            "total_timesteps": self.total_timesteps,
            "mean_reward": self.mean_reward,
            "std_reward": self.std_reward,
            "training_time_seconds": self.training_time_seconds,
            "artifact_path": self.artifact_path,
        }


from kailash_ml.rl.policy_registry import _SB3_ALGORITHMS as _ALGO_MAP


def _import_algo(algorithm: str) -> Any:
    """Lazily import an SB3 algorithm class."""
    algo_path = _ALGO_MAP.get(algorithm)
    if algo_path is None:
        raise ValueError(
            f"Unknown algorithm '{algorithm}'. Supported: {sorted(_ALGO_MAP)}"
        )
    try:
        import importlib

        module_path, cls_name = algo_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, cls_name)
    except ImportError as exc:
        raise ImportError(
            "stable-baselines3 is required for RL training. "
            "Install with: pip install kailash-ml[rl]"
        ) from exc


class RLTrainer:
    """[P2: Experimental] Reinforcement learning trainer wrapping Stable-Baselines3.

    Provides a high-level interface for training, evaluating, and saving
    RL policies using SB3 algorithms on Gymnasium environments.

    Parameters
    ----------
    env_registry:
        EnvironmentRegistry for resolving environment names.
    policy_registry:
        PolicyRegistry for storing trained policies.
    root_dir:
        Root directory for saving model artifacts.
    """

    def __init__(
        self,
        env_registry: Any | None = None,
        policy_registry: Any | None = None,
        *,
        root_dir: str | Path = ".kailash_ml/rl_artifacts",
    ) -> None:
        self._env_registry = env_registry
        self._policy_registry = policy_registry
        self._root = Path(root_dir)

    def train(
        self,
        env_name: str,
        policy_name: str,
        config: RLTrainingConfig | None = None,
    ) -> RLTrainingResult:
        """Train an RL agent on the given environment.

        Parameters
        ----------
        env_name:
            Gymnasium environment name (e.g. ``"CartPole-v1"``).
        policy_name:
            Name to register the trained policy under.
        config:
            Training configuration. Uses defaults if None.

        Returns
        -------
        RLTrainingResult
        """
        config = config or RLTrainingConfig()

        # Create environment
        env = self._make_env(env_name)

        # Import algorithm
        algo_cls = _import_algo(config.algorithm)

        # Build hyperparameters
        hp = dict(config.hyperparameters)
        if config.seed is not None:
            hp["seed"] = config.seed
        hp["verbose"] = config.verbose

        # Create model
        model = algo_cls(config.policy_type, env, **hp)

        # Train
        start = time.perf_counter()
        model.learn(total_timesteps=config.total_timesteps)
        training_time = time.perf_counter() - start

        # Evaluate
        mean_reward, std_reward = self._evaluate(model, env, config.n_eval_episodes)

        # Save artifact
        artifact_path = self._save_model(model, policy_name, config)

        # Register with policy registry
        if self._policy_registry is not None:
            from kailash_ml.rl.policy_registry import PolicyVersion

            versions = self._policy_registry.list_versions(policy_name)
            next_version = max((v.version for v in versions), default=0) + 1
            pv = PolicyVersion(
                name=policy_name,
                version=next_version,
                algorithm=config.algorithm,
                artifact_path=str(artifact_path),
                mean_reward=mean_reward,
                std_reward=std_reward,
                total_timesteps=config.total_timesteps,
                metadata=config.to_dict(),
            )
            self._policy_registry.register_version(pv)

        env.close()

        return RLTrainingResult(
            policy_name=policy_name,
            algorithm=config.algorithm,
            total_timesteps=config.total_timesteps,
            mean_reward=mean_reward,
            std_reward=std_reward,
            training_time_seconds=training_time,
            artifact_path=str(artifact_path) if artifact_path else None,
        )

    def evaluate(
        self,
        model: Any,
        env_name: str,
        n_episodes: int = 10,
    ) -> tuple[float, float]:
        """Evaluate a trained model on an environment.

        Returns (mean_reward, std_reward).
        """
        env = self._make_env(env_name)
        result = self._evaluate(model, env, n_episodes)
        env.close()
        return result

    def load_and_evaluate(
        self,
        policy_name: str,
        env_name: str,
        version: int | None = None,
        n_episodes: int = 10,
    ) -> tuple[float, float]:
        """Load a policy from registry and evaluate it."""
        if self._policy_registry is None:
            raise ValueError("PolicyRegistry required for load_and_evaluate")
        model = self._policy_registry.load_model(policy_name, version)
        return self.evaluate(model, env_name, n_episodes)

    def _make_env(self, env_name: str) -> Any:
        """Create an environment, using registry if available."""
        if self._env_registry is not None and env_name in self._env_registry:
            return self._env_registry.make(env_name)

        try:
            import gymnasium as gym
        except ImportError as exc:
            raise ImportError(
                "gymnasium is required for RL. Install with: pip install kailash-ml[rl]"
            ) from exc
        return gym.make(env_name)

    @staticmethod
    def _evaluate(model: Any, env: Any, n_episodes: int) -> tuple[float, float]:
        """Run evaluation episodes and return (mean_reward, std_reward)."""
        import numpy as np

        rewards: list[float] = []
        for _ in range(n_episodes):
            obs, _info = env.reset()
            episode_reward = 0.0
            done = False
            while not done:
                action, _ = model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, _info = env.step(action)
                episode_reward += float(reward)
                done = terminated or truncated
            rewards.append(episode_reward)

        return float(np.mean(rewards)), float(np.std(rewards))

    def _save_model(
        self, model: Any, policy_name: str, config: RLTrainingConfig
    ) -> Path | None:
        """Save model to disk."""
        save_dir = config.save_path or self._root / policy_name
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        model_path = save_dir / "model"
        model.save(str(model_path))
        logger.info("Saved RL model to %s.", model_path)
        return model_path

    @staticmethod
    def supported_algorithms() -> list[str]:
        """Return list of supported SB3 algorithm names."""
        return sorted(_ALGO_MAP)
