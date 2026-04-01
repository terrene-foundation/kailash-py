# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PolicyRegistry -- register and manage RL policies (SB3 algorithms)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["PolicyRegistry", "PolicySpec", "PolicyVersion"]


@dataclass
class PolicySpec:
    """Specification for an RL algorithm/policy."""

    name: str
    algorithm: str  # SB3 algorithm class name: "PPO", "SAC", "DQN", "A2C", "TD3"
    policy_type: str = "MlpPolicy"  # "MlpPolicy", "CnnPolicy", "MultiInputPolicy"
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


# Maps SB3 algorithm name to import path
_SB3_ALGORITHMS: dict[str, str] = {
    "PPO": "stable_baselines3.PPO",
    "SAC": "stable_baselines3.SAC",
    "DQN": "stable_baselines3.DQN",
    "A2C": "stable_baselines3.A2C",
    "TD3": "stable_baselines3.TD3",
    "DDPG": "stable_baselines3.DDPG",
}


class PolicyRegistry:
    """Registry for RL policies.

    Manages policy specifications and trained policy artifacts,
    providing versioned storage and retrieval.

    Parameters
    ----------
    root_dir:
        Root directory for policy artifacts.
    """

    def __init__(self, root_dir: str | Path = ".kailash_ml/policies") -> None:
        self._root = Path(root_dir)
        self._specs: dict[str, PolicySpec] = {}
        self._versions: dict[str, list[PolicyVersion]] = {}

    def register_spec(self, spec: PolicySpec) -> None:
        """Register a policy specification."""
        if spec.algorithm not in _SB3_ALGORITHMS:
            raise ValueError(
                f"Unknown algorithm '{spec.algorithm}'. "
                f"Supported: {sorted(_SB3_ALGORITHMS)}"
            )
        self._specs[spec.name] = spec
        logger.info("Registered policy spec '%s' (%s).", spec.name, spec.algorithm)

    _MAX_VERSIONS_PER_POLICY = 1000

    def register_version(self, version: PolicyVersion) -> None:
        """Register a trained policy version."""
        if version.name not in self._versions:
            self._versions[version.name] = []
        versions = self._versions[version.name]
        versions.append(version)
        # Evict oldest if over limit
        if len(versions) > self._MAX_VERSIONS_PER_POLICY:
            self._versions[version.name] = versions[-self._MAX_VERSIONS_PER_POLICY :]
        logger.info(
            "Registered policy '%s' v%d (reward=%.2f).",
            version.name,
            version.version,
            version.mean_reward or 0.0,
        )

    def get_spec(self, name: str) -> PolicySpec | None:
        """Get the spec for a registered policy."""
        return self._specs.get(name)

    def get_latest_version(self, name: str) -> PolicyVersion | None:
        """Get the latest trained version of a policy."""
        versions = self._versions.get(name, [])
        if not versions:
            return None
        return max(versions, key=lambda v: v.version)

    def get_version(self, name: str, version: int) -> PolicyVersion | None:
        """Get a specific version of a trained policy."""
        versions = self._versions.get(name, [])
        for v in versions:
            if v.version == version:
                return v
        return None

    def list_specs(self) -> list[PolicySpec]:
        """List all registered policy specifications."""
        return list(self._specs.values())

    def list_versions(self, name: str) -> list[PolicyVersion]:
        """List all trained versions of a policy."""
        return list(self._versions.get(name, []))

    def load_model(self, name: str, version: int | None = None) -> Any:
        """Load a trained SB3 model from disk.

        Parameters
        ----------
        name:
            Policy name.
        version:
            Specific version number. If None, loads latest.
        """
        if version is not None:
            pv = self.get_version(name, version)
        else:
            pv = self.get_latest_version(name)

        if pv is None:
            raise ValueError(f"No trained version found for policy '{name}'")

        spec = self._specs.get(name)
        if spec is None:
            raise ValueError(f"No spec registered for policy '{name}'")

        algo_path = _SB3_ALGORITHMS.get(spec.algorithm)
        if algo_path is None:
            raise ValueError(f"Unknown algorithm: {spec.algorithm}")

        try:
            import importlib

            module_path, cls_name = algo_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            algo_cls = getattr(module, cls_name)
        except ImportError as exc:
            raise ImportError(
                "stable-baselines3 is required for RL. "
                "Install with: pip install kailash-ml[rl]"
            ) from exc

        return algo_cls.load(pv.artifact_path)

    @staticmethod
    def supported_algorithms() -> list[str]:
        """Return list of supported SB3 algorithm names."""
        return sorted(_SB3_ALGORITHMS)

    def __contains__(self, name: str) -> bool:
        return name in self._specs

    def __len__(self) -> int:
        return len(self._specs)
