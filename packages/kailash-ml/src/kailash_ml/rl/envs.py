# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EnvironmentRegistry -- register and manage Gymnasium environments."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["EnvironmentRegistry", "EnvironmentSpec"]


@dataclass
class EnvironmentSpec:
    """Specification for a registered environment."""

    name: str
    entry_point: str  # e.g. "gymnasium.envs.classic_control:CartPoleEnv"
    kwargs: dict[str, Any] = field(default_factory=dict)
    max_episode_steps: int | None = None
    reward_threshold: float | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entry_point": self.entry_point,
            "kwargs": self.kwargs,
            "max_episode_steps": self.max_episode_steps,
            "reward_threshold": self.reward_threshold,
            "description": self.description,
        }


class EnvironmentRegistry:
    """Registry for Gymnasium environments.

    Manages custom and standard environments, providing a unified
    interface for creating and configuring RL training environments.
    """

    def __init__(self) -> None:
        self._specs: dict[str, EnvironmentSpec] = {}

    def register(self, spec: EnvironmentSpec) -> None:
        """Register an environment specification.

        Also registers with Gymnasium if not already registered.
        """
        try:
            import gymnasium as gym
        except ImportError as exc:
            raise ImportError(
                "gymnasium is required for RL. Install with: pip install kailash-ml[rl]"
            ) from exc

        self._specs[spec.name] = spec

        # Register with Gymnasium if custom
        try:
            gym.spec(spec.name)
        except (gym.error.NameNotFound, Exception):
            gym.register(
                id=spec.name,
                entry_point=spec.entry_point,
                kwargs=spec.kwargs,
                max_episode_steps=spec.max_episode_steps,
                reward_threshold=spec.reward_threshold,
            )
            logger.info("Registered environment '%s' with Gymnasium.", spec.name)

    def make(self, name: str, **kwargs: Any) -> Any:
        """Create an environment instance.

        Parameters
        ----------
        name:
            Environment name. Can be a registered custom env or any
            standard Gymnasium environment.
        **kwargs:
            Additional keyword arguments passed to ``gymnasium.make()``.
        """
        try:
            import gymnasium as gym
        except ImportError as exc:
            raise ImportError(
                "gymnasium is required for RL. Install with: pip install kailash-ml[rl]"
            ) from exc

        spec = self._specs.get(name)
        merged_kwargs = {}
        if spec is not None:
            merged_kwargs.update(spec.kwargs)
        merged_kwargs.update(kwargs)

        return gym.make(name, **merged_kwargs)

    def list_environments(self) -> list[EnvironmentSpec]:
        """Return all registered custom environments."""
        return list(self._specs.values())

    def get_spec(self, name: str) -> EnvironmentSpec | None:
        """Get the specification for a registered environment."""
        return self._specs.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._specs

    def __len__(self) -> int:
        return len(self._specs)
