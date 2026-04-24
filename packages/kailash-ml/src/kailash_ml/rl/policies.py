# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Policy + reward registries for reinforcement learning.

Implements ``PolicyRegistry`` for:

* Policy specifications (algorithm choice, policy network kind, hyperparameters)
* Trained policy versions (artifact paths, evaluation stats)
* User-registered **reward functions** per invariant #5 of W29

The registry is intentionally in-process for W29; a tenant-scoped backend
lands with the later M9 shards (per ``specs/ml-rl-core.md`` §4.4). The in-
process surface uses a ``_tenant_id`` attribute so downstream shards can
bolt on persistence without re-plumbing every caller.

All failure modes raise from the ``RLError`` hierarchy; never
``ValueError`` / ``RuntimeError`` where an ``RLError`` subclass applies
(W29 invariant #7).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kailash_ml.errors import RLError

logger = logging.getLogger(__name__)

__all__ = [
    "PolicyRegistry",
    "PolicySpec",
    "PolicyVersion",
    "RewardFn",
    "_SB3_ALGORITHMS",
]


# Map user-facing algorithm name -> internal adapter import path. The adapter
# is the indirection layer that owns SB3 / sb3-contrib / deferred-error
# dispatch. See ``kailash_ml.rl.algorithms``. Keys are lowercased to match
# the ``km.rl_train(algo=...)`` surface; uppercased aliases are resolved
# in ``_canonical_algorithm`` via ``_ALIAS_MAP``.
_SB3_ALGORITHMS: dict[str, str] = {
    "ppo": "kailash_ml.rl.algorithms:PPOAdapter",
    "sac": "kailash_ml.rl.algorithms:SACAdapter",
    "dqn": "kailash_ml.rl.algorithms:DQNAdapter",
    "a2c": "kailash_ml.rl.algorithms:A2CAdapter",
    "td3": "kailash_ml.rl.algorithms:TD3Adapter",
    "ddpg": "kailash_ml.rl.algorithms:DDPGAdapter",
    "maskable-ppo": "kailash_ml.rl.algorithms:MaskablePPOAdapter",
    "maskable_ppo": "kailash_ml.rl.algorithms:MaskablePPOAdapter",
    "decision-transformer": "kailash_ml.rl.algorithms:DecisionTransformerAdapter",
    "decision_transformer": "kailash_ml.rl.algorithms:DecisionTransformerAdapter",
}

# Case-insensitive user aliases (pre-1.0 users often pass ``"PPO"``).
_ALIAS_MAP: dict[str, str] = {
    "PPO": "ppo",
    "SAC": "sac",
    "DQN": "dqn",
    "A2C": "a2c",
    "TD3": "td3",
    "DDPG": "ddpg",
    "MaskablePPO": "maskable-ppo",
    "DecisionTransformer": "decision-transformer",
}


RewardFn = Callable[..., float]
"""Callable that maps ``(*args, **kwargs)`` -> ``float`` reward.

The exact signature is algorithm-dependent; typical forms are
``(obs, action, next_obs, env_info) -> float`` for classical RL and
``(trajectory) -> float`` for offline RL. Registration is intentionally
permissive (positional + keyword): adapters invoke the registered fn
with whatever kwargs the surrounding algorithm produces.
"""


@dataclass
class PolicySpec:
    """Specification for an RL algorithm/policy."""

    name: str
    algorithm: str  # e.g. "ppo", "sac"; see _SB3_ALGORITHMS
    policy_type: str = "MlpPolicy"
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "algorithm": self.algorithm,
            "policy_type": self.policy_type,
            "hyperparameters": self.hyperparameters,
            "description": self.description,
        }


@dataclass
class PolicyVersion:
    """A trained policy version."""

    name: str
    version: int
    algorithm: str
    artifact_path: str
    mean_reward: float | None = None
    std_reward: float | None = None
    total_timesteps: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "algorithm": self.algorithm,
            "artifact_path": self.artifact_path,
            "mean_reward": self.mean_reward,
            "std_reward": self.std_reward,
            "total_timesteps": self.total_timesteps,
            "metadata": self.metadata,
        }


def _canonical_algorithm(algorithm: str) -> str:
    """Normalize ``algorithm`` against aliases + the lowercased key map.

    Raises
    ------
    RLError
        Algorithm is unknown. Error is typed so callers may catch without
        string-matching.
    """
    if algorithm in _SB3_ALGORITHMS:
        return algorithm
    mapped = _ALIAS_MAP.get(algorithm)
    if mapped is not None:
        return mapped
    lower = algorithm.lower() if isinstance(algorithm, str) else algorithm
    if isinstance(lower, str) and lower in _SB3_ALGORITHMS:
        return lower
    raise RLError(
        reason="unknown_algorithm",
        algorithm=algorithm,
        supported=sorted(set(_SB3_ALGORITHMS)),
    )


class PolicyRegistry:
    """In-process registry for RL policies + reward functions.

    Manager-shape class per ``rules/facade-manager-detection.md``. The
    registry does NOT construct a parallel framework; persistence hooks
    are deferred to the later M9 shards that add tenant-scoped storage.

    Parameters
    ----------
    root_dir:
        Root directory for policy artifacts.
    tenant_id:
        Tenant id for scoping. v1 stores the value on the instance so
        later persistence shards can key on it.
    """

    _MAX_VERSIONS_PER_POLICY = 1000

    def __init__(
        self,
        root_dir: str | Path = ".kailash_ml/policies",
        *,
        tenant_id: str | None = None,
    ) -> None:
        self._root = Path(root_dir)
        self._tenant_id = tenant_id
        self._specs: dict[str, PolicySpec] = {}
        self._versions: dict[str, list[PolicyVersion]] = {}
        self._rewards: dict[str, RewardFn] = {}

    # --- Policy specs + versions -----------------------------------------

    def register_spec(self, spec: PolicySpec) -> None:
        """Register a policy specification.

        Raises
        ------
        RLError
            The algorithm is not one of the supported algorithms.
        """
        _canonical_algorithm(spec.algorithm)  # raises RLError on unknown
        self._specs[spec.name] = spec
        logger.info(
            "policy_registry.spec.registered",
            extra={
                "policy_name": spec.name,
                "algorithm": spec.algorithm,
                "tenant_id": self._tenant_id,
            },
        )

    def register_version(self, version: PolicyVersion) -> None:
        """Register a trained policy version.

        Oldest versions beyond ``_MAX_VERSIONS_PER_POLICY`` are evicted to
        bound memory.
        """
        if version.name not in self._versions:
            self._versions[version.name] = []
        versions = self._versions[version.name]
        versions.append(version)
        if len(versions) > self._MAX_VERSIONS_PER_POLICY:
            self._versions[version.name] = versions[-self._MAX_VERSIONS_PER_POLICY :]
        logger.info(
            "policy_registry.version.registered",
            extra={
                "policy_name": version.name,
                "version": version.version,
                "mean_reward": version.mean_reward,
                "tenant_id": self._tenant_id,
            },
        )

    def get_spec(self, name: str) -> PolicySpec | None:
        return self._specs.get(name)

    def get_latest_version(self, name: str) -> PolicyVersion | None:
        versions = self._versions.get(name, [])
        if not versions:
            return None
        return max(versions, key=lambda v: v.version)

    def get_version(self, name: str, version: int) -> PolicyVersion | None:
        for v in self._versions.get(name, []):
            if v.version == version:
                return v
        return None

    def list_specs(self) -> list[PolicySpec]:
        return list(self._specs.values())

    def list_versions(self, name: str) -> list[PolicyVersion]:
        return list(self._versions.get(name, []))

    def load_model(self, name: str, version: int | None = None) -> Any:
        """Load a trained model artifact from disk via the adapter layer.

        Raises
        ------
        RLError
            No trained version exists, no spec is registered, or the
            algorithm cannot be resolved.
        """
        pv = (
            self.get_version(name, version)
            if version is not None
            else self.get_latest_version(name)
        )
        if pv is None:
            raise RLError(
                reason="policy_version_not_found",
                policy_name=name,
                version=version,
            )
        spec = self._specs.get(name)
        if spec is None:
            raise RLError(reason="policy_spec_not_found", policy_name=name)
        # Delegate to the adapter layer so sb3_contrib / deferred paths
        # route through the same error channel as training. Import lazily
        # so the registry remains importable without the [rl] extra.
        from kailash_ml.rl.algorithms import load_adapter_class

        adapter_cls = load_adapter_class(spec.algorithm)
        return adapter_cls.load(pv.artifact_path)

    # --- Reward registry (W29 invariant #5) ------------------------------

    def register_reward(self, name: str, fn: RewardFn) -> None:
        """Register a user-defined reward function under ``name``.

        Re-registering the exact same callable is idempotent; registering
        a *different* callable under an already-registered name raises
        ``RLError(reason="reward_name_occupied")`` so two modules cannot
        silently stomp each other.
        """
        if not callable(fn):
            raise RLError(
                reason="reward_not_callable",
                name=name,
                fn_type=type(fn).__name__,
            )
        existing = self._rewards.get(name)
        if existing is not None and existing is not fn:
            raise RLError(reason="reward_name_occupied", name=name)
        self._rewards[name] = fn
        logger.info(
            "policy_registry.reward.registered",
            extra={"reward_name": name, "tenant_id": self._tenant_id},
        )

    def get_reward(self, name: str) -> RewardFn:
        """Return the reward function registered under ``name``.

        Raises
        ------
        RLError
            No reward is registered under the given name.
        """
        fn = self._rewards.get(name)
        if fn is None:
            raise RLError(
                reason="reward_not_found",
                name=name,
                registered=sorted(self._rewards),
            )
        return fn

    def list_rewards(self) -> list[str]:
        return sorted(self._rewards)

    # --- Static helpers --------------------------------------------------

    @staticmethod
    def supported_algorithms() -> list[str]:
        """Return the sorted list of canonical algorithm names."""
        return sorted(set(_SB3_ALGORITHMS))

    def __contains__(self, name: str) -> bool:
        return name in self._specs

    def __len__(self) -> int:
        return len(self._specs)
