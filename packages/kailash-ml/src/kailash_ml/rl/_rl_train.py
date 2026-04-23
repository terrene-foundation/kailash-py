# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Module-level ``rl_train`` entry backing ``km.rl_train``.

Per W29 invariant #3, ``km.rl_train(env, algo, *, total_timesteps,
hyperparameters)`` is the user-facing surface. The actual top-level
registration (adding ``rl_train`` to ``kailash_ml.__all__`` Group 1)
lives in W33; W29 provides the callable so W33 only flips the import.

This is a thin facade over :class:`RLTrainer`:

* ``env`` may be a Gymnasium id (``"CartPole-v1"``) or a ``gym.Env`` /
  factory callable per the public spec signature (``specs/ml-rl-core.md``
  §3.1). For v1 we only support the string id + the factory callable;
  pre-built ``gym.Env`` instances are wrapped into a one-shot factory by
  the registry on first call.

Every failure raises from the :class:`kailash_ml.errors.RLError`
hierarchy (W29 invariant #7); unknown algorithm / missing SB3 / missing
sb3-contrib / deferred-algorithm paths surface as typed errors.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from kailash_ml.errors import RLError

logger = logging.getLogger(__name__)

__all__ = ["rl_train"]


def rl_train(
    env: str | Callable[[], Any] | Any,
    algo: str = "ppo",
    *,
    total_timesteps: int = 100_000,
    hyperparameters: dict[str, Any] | None = None,
    policy: str | None = None,
    n_eval_episodes: int = 10,
    seed: int | None = 42,
    register_as: str | None = None,
    env_registry: Any | None = None,
    policy_registry: Any | None = None,
    tenant_id: str | None = None,
    root_dir: str | None = None,
) -> Any:
    """Train an RL agent via the canonical Kailash surface.

    Parameters
    ----------
    env:
        Gymnasium id (e.g. ``"CartPole-v1"``) OR a zero-argument factory
        returning a ``gym.Env`` OR a pre-built env instance.
    algo:
        Algorithm name (``"ppo"``, ``"sac"``, ``"dqn"``, ``"a2c"``,
        ``"td3"``, ``"ddpg"``, ``"maskable-ppo"``, ``"decision-transformer"``).
        Unknown names raise ``RLError(reason="unknown_algorithm")``.
    total_timesteps:
        Total SB3 training steps. The default is 100_000; callers should
        override for production runs.
    hyperparameters:
        Passed into the SB3 constructor, merged over per-algorithm defaults.
    policy:
        SB3 policy kind (``"MlpPolicy"`` / ``"CnnPolicy"`` /
        ``"MultiInputPolicy"``). Defaults per-algorithm.
    n_eval_episodes:
        Number of eval episodes after training. Uses the training env to
        avoid requiring a second environment instance for the minimal
        v1 surface.
    seed:
        Random seed forwarded to the SB3 constructor.
    register_as:
        If set, the trained policy is registered under this name in the
        ``policy_registry``. If ``policy_registry`` is ``None``, an in-
        process registry is constructed so the registration is always
        captured somewhere.
    env_registry:
        Optional :class:`EnvironmentRegistry` used to resolve ``env`` when
        it is a string id.
    policy_registry:
        Optional :class:`PolicyRegistry` for storing trained policies and
        reward functions.
    tenant_id:
        Tenant id forwarded to the trainer for logging and artifact
        paths.
    root_dir:
        Root directory for saved policy artifacts; defaults to
        ``.kailash_ml/rl_artifacts``.

    Returns
    -------
    RLTrainingResult
        Populated with the W29 metric-parity keys. ``artifact_path``
        points at the SB3 ``.zip`` model file.
    """
    # Lazy-import heavy modules so `from kailash_ml.rl import rl_train`
    # works without SB3 installed (tests without [rl] can assert importability).
    from kailash_ml.rl.envs import EnvironmentRegistry
    from kailash_ml.rl.policies import PolicyRegistry
    from kailash_ml.rl.trainer import RLTrainer, RLTrainingConfig

    if total_timesteps <= 0 or not isinstance(total_timesteps, int):
        raise RLError(
            reason="invalid_total_timesteps",
            total_timesteps=total_timesteps,
        )

    # Resolve env. A pre-built env or factory goes through a synthetic
    # registry entry so the trainer never sees a raw object. The callable
    # form wraps the factory for lazy construction.
    if env_registry is None:
        env_registry = EnvironmentRegistry(tenant_id=tenant_id)
    env_id, env_registry = _normalize_env(env, env_registry, tenant_id=tenant_id)

    if policy_registry is None:
        policy_registry = PolicyRegistry(tenant_id=tenant_id)

    trainer_kwargs: dict[str, Any] = {
        "env_registry": env_registry,
        "policy_registry": policy_registry,
        "tenant_id": tenant_id,
    }
    if root_dir is not None:
        trainer_kwargs["root_dir"] = root_dir
    trainer = RLTrainer(**trainer_kwargs)

    config = RLTrainingConfig(
        algorithm=algo,
        policy_type=policy or "MlpPolicy",
        total_timesteps=int(total_timesteps),
        hyperparameters=dict(hyperparameters or {}),
        n_eval_episodes=n_eval_episodes,
        seed=seed,
    )
    policy_name = register_as or f"{algo}-{env_id}"

    logger.info(
        "rl_train.start",
        extra={
            "algorithm": algo,
            "env": env_id,
            "total_timesteps": total_timesteps,
            "policy_name": policy_name,
            "tenant_id": tenant_id,
        },
    )
    return trainer.train(env_id, policy_name, config=config)


# ---------------------------------------------------------------------------
# env normalization
# ---------------------------------------------------------------------------


class _CallableEnvSpec:
    """Wrap a factory callable so ``gym.make`` resolution is consistent.

    ``EnvironmentRegistry.make`` only resolves string ids via Gymnasium; a
    factory callable or a pre-built env is routed through this one-shot
    registry entry so the trainer's ``_make_env`` path remains uniform.
    """

    def __init__(self, fn: Callable[[], Any]) -> None:
        self._fn = fn
        self._built: list[Any] = []

    def __call__(self) -> Any:
        env = self._fn()
        self._built.append(env)
        return env


def _normalize_env(
    env: str | Callable[[], Any] | Any,
    env_registry: Any,
    *,
    tenant_id: str | None,
) -> tuple[str, Any]:
    """Normalize ``env`` to a string id + registry that can resolve it.

    * String id -> return as-is; trainer resolves via ``gym.make`` or
      the user-supplied registry.
    * Callable (factory) -> insert a ``_FactoryRegistry`` adapter that
      returns the factory output from ``.make(name)``; id is synthetic.
    * Pre-built env -> wrap in a one-shot factory + same adapter.
    """
    if isinstance(env, str):
        return env, env_registry
    if callable(env):
        factory = env
    else:
        # Pre-built env instance — wrap in a one-shot factory. The first
        # ``.make()`` returns the passed instance; subsequent calls
        # produce a fresh env via the underlying env.unwrapped spec if
        # available, else re-use the original (with a warning).
        _built = env

        def factory() -> Any:
            nonlocal _built
            current = _built
            _built = None
            if current is None:
                raise RLError(
                    reason="prebuilt_env_consumed",
                    remediation="Pass a factory callable rather than a pre-built env",
                    tenant_id=tenant_id,
                )
            return current

    synthetic_id = f"kailash-ml://factory/{id(factory):x}"
    return synthetic_id, _FactoryRegistryAdapter(
        env_registry, synthetic_id, factory, tenant_id=tenant_id
    )


class _FactoryRegistryAdapter:
    """Delegate around ``EnvironmentRegistry`` that resolves synthetic ids.

    We do NOT mutate the passed-in ``env_registry`` — that avoids cross-
    tenant leakage if the caller shares the registry across training
    runs. The adapter delegates unknown ids back to the original
    registry and answers only the synthetic id registered at construction.
    """

    def __init__(
        self,
        inner: Any,
        synthetic_id: str,
        factory: Callable[[], Any],
        *,
        tenant_id: str | None = None,
    ) -> None:
        self._inner = inner
        self._synthetic_id = synthetic_id
        self._factory = factory
        self._tenant_id = tenant_id

    def __contains__(self, name: str) -> bool:
        if name == self._synthetic_id:
            return True
        return name in self._inner

    def make(self, name: str, **kwargs: Any) -> Any:
        if name == self._synthetic_id:
            return self._factory()
        return self._inner.make(name, **kwargs)

    def __getattr__(self, attr: str) -> Any:
        # Forward anything else (list_environments, register, ...) to the
        # underlying registry so the user's state is not shadowed.
        return getattr(self._inner, attr)
