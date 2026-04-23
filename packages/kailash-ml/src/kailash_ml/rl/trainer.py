# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""RLTrainer — Stable-Baselines3 wrapper for the RL training lifecycle.

Per W29:

* Manager-shape class (`rules/facade-manager-detection.md`): wiring-test
  required (see ``tests/integration/test_rl_trainer_wiring.py``).
* Cross-algorithm ``RLTrainingResult`` parity: every run populates a
  metrics dict with ``reward_mean``, ``reward_std``, ``ep_len_mean``,
  ``ep_len_std``, ``kl``, and ``clip_frac``; non-applicable metrics
  surface as ``None`` with a documented reason rather than hallucinated
  zeros (``rules/zero-tolerance.md`` Rule 2).
* Error hierarchy: every failure path raises from :mod:`kailash_ml.errors`
  (W29 invariant #7).

The substrate is Stable-Baselines3 + Gymnasium (Decision 8 carve-out —
RL is NOT Lightning-routed). The imports are all local inside methods so
``from kailash_ml.rl.trainer import RLTrainer`` works without the ``[rl]``
extra installed; tests without ``[rl]`` can still exercise import guards.

Requires ``pip install kailash-ml[rl]`` (stable-baselines3, gymnasium).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kailash_ml.errors import RLError

logger = logging.getLogger(__name__)

__all__ = [
    "RLTrainer",
    "RLTrainingConfig",
    "RLTrainingResult",
    "METRIC_KEYS",
]


# --- Cross-algorithm metric parity (W29 invariant #4) ----------------------

# Every RLTrainingResult.metrics MUST expose exactly these keys. Values
# that are not applicable to the algorithm surface as ``None``; non-finite
# values are BLOCKED by the adapter's callback.
METRIC_KEYS: tuple[str, ...] = (
    "reward_mean",
    "reward_std",
    "ep_len_mean",
    "ep_len_std",
    "kl",
    "clip_frac",
)


# --- Configuration + result dataclasses -----------------------------------


@dataclass
class RLTrainingConfig:
    """Configuration for RL training."""

    algorithm: str = "PPO"
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
    """Result of an RL training run.

    The ``metrics`` dict carries the W29 invariant #4 keys:
    ``reward_mean``, ``reward_std``, ``ep_len_mean``, ``ep_len_std``,
    ``kl``, ``clip_frac``. Metrics not applicable to the algorithm are
    ``None`` (never hallucinated zero — per zero-tolerance Rule 2).
    """

    policy_name: str
    algorithm: str
    total_timesteps: int
    mean_reward: float
    std_reward: float
    training_time_seconds: float
    metrics: dict[str, float | None] = field(default_factory=dict)
    artifact_path: str | None = None
    eval_history: list[dict[str, Any]] = field(default_factory=list)
    reward_curve: list[tuple[int, float]] = field(default_factory=list)
    env_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_name": self.policy_name,
            "algorithm": self.algorithm,
            "total_timesteps": self.total_timesteps,
            "mean_reward": self.mean_reward,
            "std_reward": self.std_reward,
            "training_time_seconds": self.training_time_seconds,
            "metrics": dict(self.metrics),
            "artifact_path": self.artifact_path,
            "eval_history": list(self.eval_history),
            "reward_curve": list(self.reward_curve),
            "env_name": self.env_name,
        }


# --- Metric-capture callback ----------------------------------------------


def _make_callback() -> Any:
    """Construct a ``stable_baselines3.common.callbacks.BaseCallback``.

    Kept as a lazy factory so ``kailash_ml.rl.trainer`` imports without
    SB3 installed. The callback samples the backend logger after each
    rollout + each eval and stores the metrics on ``self.snapshot`` so
    ``RLTrainer.train`` can write them into the ``RLTrainingResult``.
    """
    try:
        from stable_baselines3.common.callbacks import BaseCallback
    except ImportError as exc:  # pragma: no cover - exercised only without [rl]
        raise ImportError(
            "stable-baselines3 is required for RL. "
            "Install with: pip install kailash-ml[rl]"
        ) from exc

    class _KailashRLCallback(BaseCallback):  # type: ignore[misc]
        """Capture the canonical RL metrics from the backend logger."""

        def __init__(self) -> None:
            super().__init__(verbose=0)
            self.snapshot: dict[str, float | None] = {k: None for k in METRIC_KEYS}
            self.reward_curve: list[tuple[int, float]] = []

        def _on_step(self) -> bool:  # pragma: no cover — trivial
            return True

        def _capture(self) -> None:
            """Copy metrics from the backend logger into ``snapshot``.

            SB3 exposes metrics as ``self.logger.name_to_value`` (tensorboard-
            compatible). Metric keys differ slightly per algorithm:
            * rollout/ep_rew_mean (+ ep_len_mean) — all algos
            * train/approx_kl — PPO, TRPO, SAC (entropy coef)
            * train/clip_fraction — PPO
            """
            import math

            src = getattr(self.logger, "name_to_value", {}) or {}

            def _get(key: str) -> float | None:
                if key not in src:
                    return None
                try:
                    val = float(src[key])
                except (TypeError, ValueError):
                    return None
                if not math.isfinite(val):
                    return None
                return val

            rew_mean = _get("rollout/ep_rew_mean")
            if rew_mean is not None:
                self.snapshot["reward_mean"] = rew_mean
                # reward_curve: sample every rollout-end at the current step.
                self.reward_curve.append((int(self.num_timesteps), rew_mean))

            if (len_mean := _get("rollout/ep_len_mean")) is not None:
                self.snapshot["ep_len_mean"] = len_mean
            if (kl := _get("train/approx_kl")) is not None:
                self.snapshot["kl"] = kl
            if (clip := _get("train/clip_fraction")) is not None:
                self.snapshot["clip_frac"] = clip

        def _on_rollout_end(self) -> None:  # pragma: no cover — SB3-internal
            self._capture()

        def _on_training_end(self) -> None:  # pragma: no cover — SB3-internal
            self._capture()

    return _KailashRLCallback()


# --- Trainer --------------------------------------------------------------


class RLTrainer:
    """Reinforcement learning trainer wrapping Stable-Baselines3.

    Manager-shape class per ``rules/facade-manager-detection.md``. The
    trainer takes explicit ``env_registry`` + ``policy_registry`` so the
    framework dependency is visible at construction (no global lookups).

    Parameters
    ----------
    env_registry:
        EnvironmentRegistry for resolving environment names.
    policy_registry:
        PolicyRegistry for storing trained policies + reward functions.
    root_dir:
        Root directory for saving model artifacts.
    """

    def __init__(
        self,
        env_registry: Any | None = None,
        policy_registry: Any | None = None,
        *,
        root_dir: str | Path = ".kailash_ml/rl_artifacts",
        tenant_id: str | None = None,
    ) -> None:
        self._env_registry = env_registry
        self._policy_registry = policy_registry
        self._root = Path(root_dir)
        self._tenant_id = tenant_id

    # ------------------------------------------------------------------

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
            Name under which the trained policy is registered.
        config:
            Training configuration. Uses defaults if ``None``.

        Returns
        -------
        RLTrainingResult
            Populated with the W29 metric-parity keys.
        """
        config = config or RLTrainingConfig()
        env = self._make_env(env_name)

        try:
            from kailash_ml.rl.algorithms import load_adapter_class
        except ImportError:  # pragma: no cover — keeps import path clear
            raise

        adapter_cls = load_adapter_class(config.algorithm)
        hp = dict(config.hyperparameters)
        hp.setdefault("verbose", config.verbose)

        adapter = adapter_cls(
            env=env,
            policy=config.policy_type,
            hyperparameters=hp,
            seed=config.seed,
            tenant_id=self._tenant_id,
        )
        callback = _make_callback()

        logger.info(
            "rl_trainer.train.start",
            extra={
                "algorithm": config.algorithm,
                "env": env_name,
                "total_timesteps": config.total_timesteps,
                "policy_name": policy_name,
                "tenant_id": self._tenant_id,
                "mode": "real",
            },
        )

        start = time.perf_counter()
        try:
            model = adapter.learn(config.total_timesteps, callback=callback)
        except Exception as exc:
            logger.exception(
                "rl_trainer.train.error",
                extra={
                    "algorithm": config.algorithm,
                    "env": env_name,
                    "tenant_id": self._tenant_id,
                },
            )
            raise RLError(
                reason="train_failed",
                algorithm=config.algorithm,
                env=env_name,
                cause=str(exc),
                tenant_id=self._tenant_id,
            ) from exc
        training_time = time.perf_counter() - start

        mean_reward, std_reward = self._evaluate(model, env, config.n_eval_episodes)
        artifact_path = self._save_model(model, adapter, policy_name, config)

        # Metrics parity — every RLTrainingResult carries the full key set;
        # missing keys default to None (W29 invariant #4).
        metrics = dict(callback.snapshot)
        # reward_mean / ep_len_mean may be missing for very short runs;
        # fall back to the evaluation mean/std which are always populated.
        if metrics.get("reward_mean") is None:
            metrics["reward_mean"] = mean_reward
        metrics["reward_std"] = std_reward
        for required in METRIC_KEYS:
            metrics.setdefault(required, None)

        result = RLTrainingResult(
            policy_name=policy_name,
            algorithm=config.algorithm,
            total_timesteps=config.total_timesteps,
            mean_reward=mean_reward,
            std_reward=std_reward,
            training_time_seconds=training_time,
            metrics=metrics,
            artifact_path=str(artifact_path) if artifact_path else None,
            reward_curve=list(callback.reward_curve),
            env_name=env_name,
        )

        if self._policy_registry is not None:
            self._register_trained(policy_name, result, config)

        try:
            env.close()
        except Exception:  # pragma: no cover — cleanup path
            logger.warning(
                "rl_trainer.env_close_failed",
                extra={"env": env_name, "tenant_id": self._tenant_id},
            )

        logger.info(
            "rl_trainer.train.ok",
            extra={
                "algorithm": config.algorithm,
                "env": env_name,
                "mean_reward": mean_reward,
                "training_time_s": training_time,
                "tenant_id": self._tenant_id,
            },
        )
        return result

    # ------------------------------------------------------------------

    def evaluate(
        self,
        model: Any,
        env_name: str,
        n_episodes: int = 10,
    ) -> tuple[float, float]:
        """Evaluate a trained model on an environment."""
        env = self._make_env(env_name)
        try:
            return self._evaluate(model, env, n_episodes)
        finally:
            try:
                env.close()
            except Exception:  # pragma: no cover
                pass

    def load_and_evaluate(
        self,
        policy_name: str,
        env_name: str,
        version: int | None = None,
        n_episodes: int = 10,
    ) -> tuple[float, float]:
        """Load a policy from the registry and evaluate it."""
        if self._policy_registry is None:
            raise RLError(reason="policy_registry_required", op="load_and_evaluate")
        model = self._policy_registry.load_model(policy_name, version)
        return self.evaluate(model, env_name, n_episodes)

    # ------------------------------------------------------------------

    def _make_env(self, env_name: str) -> Any:
        """Resolve an environment via the registry, falling back to gym."""
        if self._env_registry is not None and env_name in self._env_registry:
            return self._env_registry.make(env_name)
        try:
            import gymnasium as gym
        except ImportError as exc:
            raise ImportError(
                "gymnasium is required for RL. "
                "Install with: pip install kailash-ml[rl]"
            ) from exc
        try:
            return gym.make(env_name)
        except Exception as exc:
            raise RLError(
                reason="env_not_resolvable",
                env_name=env_name,
                tenant_id=self._tenant_id,
                cause=str(exc),
            ) from exc

    @staticmethod
    def _evaluate(model: Any, env: Any, n_episodes: int) -> tuple[float, float]:
        """Run evaluation episodes and return ``(mean_reward, std_reward)``."""
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

        if not rewards:
            return 0.0, 0.0
        return float(np.mean(rewards)), float(np.std(rewards))

    def _save_model(
        self,
        model: Any,
        adapter: Any,
        policy_name: str,
        config: RLTrainingConfig,
    ) -> Path | None:
        """Persist the trained model; returns the saved path."""
        save_dir = config.save_path or self._root / policy_name
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        model_path = save_dir / "model"
        try:
            model.save(str(model_path))
        except Exception as exc:
            raise RLError(
                reason="model_save_failed",
                policy_name=policy_name,
                path=str(model_path),
                cause=str(exc),
                tenant_id=self._tenant_id,
            ) from exc
        logger.info(
            "rl_trainer.save.ok",
            extra={
                "policy_name": policy_name,
                "artifact_path": str(model_path),
                "tenant_id": self._tenant_id,
            },
        )
        return model_path

    def _register_trained(
        self,
        policy_name: str,
        result: RLTrainingResult,
        config: RLTrainingConfig,
    ) -> None:
        from kailash_ml.rl.policies import PolicySpec, PolicyVersion

        # Register a spec if one doesn't exist so future load_model works.
        if self._policy_registry.get_spec(policy_name) is None:
            spec = PolicySpec(
                name=policy_name,
                algorithm=config.algorithm,
                policy_type=config.policy_type,
                hyperparameters=dict(config.hyperparameters),
            )
            self._policy_registry.register_spec(spec)
        versions = self._policy_registry.list_versions(policy_name)
        next_version = max((v.version for v in versions), default=0) + 1
        pv = PolicyVersion(
            name=policy_name,
            version=next_version,
            algorithm=config.algorithm,
            artifact_path=result.artifact_path or "",
            mean_reward=result.mean_reward,
            std_reward=result.std_reward,
            total_timesteps=result.total_timesteps,
            metadata={
                **config.to_dict(),
                "env_name": result.env_name,
                "metrics": dict(result.metrics),
            },
        )
        self._policy_registry.register_version(pv)

    @staticmethod
    def supported_algorithms() -> list[str]:
        """Return the list of supported algorithm names.

        Delegates to the adapter registry so the list stays in sync with
        the actual adapter layer.
        """
        from kailash_ml.rl.algorithms import supported_algorithm_names

        return supported_algorithm_names()
