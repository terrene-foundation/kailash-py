# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EnvironmentRegistry for Gymnasium environments.

Manager-shape class per ``rules/facade-manager-detection.md``: every
manager-shape class (``*Registry``) MUST route its failures through the
``RLError`` hierarchy (W29 invariant #7) and MUST NOT import SB3 /
gymnasium at module scope (they live behind the ``[rl]`` extra — see
``rules/dependencies.md`` § "Declared = Gated Consistently").

A user passing an environment name that is neither registered here nor
resolvable via ``gymnasium.make`` gets a single ``RLError`` with the list
of known ids; the underlying ``gym.error.NameNotFound`` is chained for
operators who want the Gymnasium-side stack.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from kailash_ml.errors import RLError

logger = logging.getLogger(__name__)

__all__ = ["EnvironmentRegistry", "EnvironmentSpec"]


def _require_gymnasium() -> Any:
    """Import ``gymnasium`` lazily + raise a typed ImportError if missing.

    ``rules/dependencies.md`` § "Exception: Optional Extras with Loud
    Failure" — we name the extra so the user can act on the error.
    """
    try:
        import gymnasium as gym  # noqa: WPS433 (intentional local import)
    except ImportError as exc:  # pragma: no cover - exercised only without [rl]
        raise ImportError(
            "gymnasium is required for RL. " "Install with: pip install kailash-ml[rl]"
        ) from exc
    return gym


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
    """Registry for Gymnasium environments (tenant-scoped placeholder).

    Parameters
    ----------
    tenant_id:
        Optional tenant id stored on the instance. v1 is in-process; the
        later M9 persistence shard uses this field to key Redis entries
        per ``rules/tenant-isolation.md``. In-process storage is already
        per-instance so cross-tenant leakage requires sharing an instance
        across tenants (which callers MUST NOT do).
    """

    def __init__(self, *, tenant_id: str | None = None) -> None:
        self._specs: dict[str, EnvironmentSpec] = {}
        self._tenant_id = tenant_id

    # --- Registration + resolution --------------------------------------

    def register(self, spec: EnvironmentSpec) -> None:
        """Register an environment specification.

        Also registers with Gymnasium if not already registered. A
        subsequent ``make(spec.name)`` MUST succeed — per
        ``specs/ml-rl-core.md`` §4.4 we smoke-test the registration by
        calling ``gym.spec(name)``; a failure raises ``RLError`` so the
        orphan-detection tests catch registrations that never produce a
        usable env.
        """
        gym = _require_gymnasium()
        self._specs[spec.name] = spec

        # Register with Gymnasium if not already registered.
        try:
            gym.spec(spec.name)
        except Exception:  # pragma: no cover — gym.error is version-variant
            try:
                gym.register(
                    id=spec.name,
                    entry_point=spec.entry_point,
                    kwargs=spec.kwargs,
                    max_episode_steps=spec.max_episode_steps,
                    reward_threshold=spec.reward_threshold,
                )
            except Exception as exc:
                raise RLError(
                    reason="gym_register_failed",
                    env_name=spec.name,
                    entry_point=spec.entry_point,
                    cause=str(exc),
                    tenant_id=self._tenant_id,
                ) from exc
            logger.info(
                "env_registry.registered",
                extra={
                    "env_name": spec.name,
                    "entry_point": spec.entry_point,
                    "tenant_id": self._tenant_id,
                },
            )

    def make(self, name: str, **kwargs: Any) -> Any:
        """Create an environment instance.

        Raises
        ------
        RLError
            The environment name is neither registered here nor
            resolvable through Gymnasium.
        """
        gym = _require_gymnasium()
        spec = self._specs.get(name)
        merged: dict[str, Any] = {}
        if spec is not None:
            merged.update(spec.kwargs)
        merged.update(kwargs)
        try:
            return gym.make(name, **merged)
        except Exception as exc:
            raise RLError(
                reason="env_not_resolvable",
                env_name=name,
                registered=sorted(self._specs),
                cause=str(exc),
                tenant_id=self._tenant_id,
            ) from exc

    def list_environments(self) -> list[EnvironmentSpec]:
        """Return all registered custom environments."""
        return list(self._specs.values())

    def get_spec(self, name: str) -> EnvironmentSpec | None:
        return self._specs.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._specs

    def __len__(self) -> int:
        return len(self._specs)
