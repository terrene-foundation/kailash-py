# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Module-level ``rl_train`` entry backing ``km.rl_train``.

Per W29 invariant #3, ``km.rl_train(env, algo, *, total_timesteps,
hyperparameters)`` is the user-facing surface. The actual top-level
registration (adding ``rl_train`` to ``kailash_ml.__all__`` Group 1)
lives in W33; W29 provides the callable so W33 only flips the import.

Dispatch (W30)
--------------

Per ``specs/ml-rl-align-unification.md`` §3.1, ``rl_train`` resolves
``algo`` via a two-level lookup:

1. First-party classical adapter registry
   (``kailash_ml.rl.algorithms``) — ``ppo``, ``a2c``, ``trpo``,
   ``dqn``, ``sac``, ``td3``, ``ddpg``, ...
2. Align-bridge registry (``kailash_ml.rl.align_adapter``) —
   ``dpo``, ``ppo-rlhf``, ``rloo``, ``online-dpo``, ``kto``,
   ``simpo``, ``cpo``, ``grpo``, ``orpo``, ``bco``. These are lazily
   resolved by importing ``kailash_align.rl_bridge`` on demand.

Every successful run populates an :class:`RLLineage` on the returned
:class:`RLTrainingResult` (spec §5). Classical adapters populate
``sdk_source="kailash-ml"``; bridge adapters populate
``sdk_source="kailash-align"``.

Failures raise from :class:`kailash_ml.errors.RLError` for classical-
path concerns (invalid config, env not resolvable, ...) and from
:class:`FeatureNotAvailableError` for missing bridge adapters (spec §7).
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from kailash_ml._version import __version__ as _KML_VERSION
from kailash_ml.errors import RLError
from kailash_ml.rl._lineage import RLLineage
from kailash_ml.rl.align_adapter import resolve_bridge_adapter

logger = logging.getLogger(__name__)

__all__ = ["rl_train"]


# Bridge-adapter kwargs that ``km.rl_train`` forwards to align-side
# adapters per spec §3.1 step 2. Kept as a module constant so future
# additions have exactly one edit site.
_BRIDGE_ADAPTER_KWARGS: tuple[str, ...] = (
    "policy",
    "reference_model",
    "reward_model",
    "preference_dataset",
    "hyperparameters",
    "device",
    "tenant_id",
)


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
    # -- RLHF bridge-adapter kwargs (spec §3.1 step 2) --------------
    reference_model: Any | None = None,
    reward_model: Any | None = None,
    preference_dataset: Any | None = None,
    device: Any | None = None,
    experiment_name: str | None = None,
    parent_run_id: str | None = None,
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
        points at the SB3 ``.zip`` model file. Every successful run
        carries an :class:`RLLineage` on ``result.lineage`` per W30
        spec §5.
    """
    # Lazy-import heavy modules so `from kailash_ml.rl import rl_train`
    # works without SB3 installed (tests without [rl] can assert importability).
    from kailash_ml.rl.algorithms import load_adapter_class
    from kailash_ml.rl.envs import EnvironmentRegistry
    from kailash_ml.rl.policies import PolicyRegistry
    from kailash_ml.rl.trainer import RLTrainer, RLTrainingConfig

    if total_timesteps <= 0 or not isinstance(total_timesteps, int):
        raise RLError(
            reason="invalid_total_timesteps",
            total_timesteps=total_timesteps,
        )

    # -- Algorithm resolution: classical-first, then bridge ----------
    #
    # Per ``specs/ml-rl-align-unification.md`` §3.1, dispatch tries the
    # first-party classical registry FIRST. If the classical registry
    # raises ``unknown_algorithm`` we try the bridge; bridge resolution
    # may itself raise ``FeatureNotAvailableError`` if kailash-align is
    # not installed. Either error propagates up with an actionable
    # message naming the missing extra (rules/dependencies.md §
    # "Optional Extras with Loud Failure").
    try:
        load_adapter_class(algo)
        _is_classical = True
    except RLError as exc:
        if getattr(exc, "reason", None) != "unknown_algorithm":
            raise
        _is_classical = False

    if not _is_classical:
        logger.info(
            "rl_train.dispatch.bridge",
            extra={
                "algorithm": algo,
                "tenant_id": tenant_id,
                "mode": "real",
            },
        )
        return _run_bridge_adapter(
            algo=algo,
            env=env,
            total_timesteps=total_timesteps,
            hyperparameters=hyperparameters,
            policy=policy,
            n_eval_episodes=n_eval_episodes,
            seed=seed,
            tenant_id=tenant_id,
            reference_model=reference_model,
            reward_model=reward_model,
            preference_dataset=preference_dataset,
            device=device,
            experiment_name=experiment_name,
            parent_run_id=parent_run_id,
            register_as=register_as,
        )

    # -- Classical (first-party) dispatch ---------------------------
    logger.info(
        "rl_train.dispatch.classical",
        extra={
            "algorithm": algo,
            "tenant_id": tenant_id,
            "mode": "real",
        },
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
    result = trainer.train(env_id, policy_name, config=config)

    # Attach W30 cross-SDK lineage. Classical runs populate
    # ``sdk_source="kailash-ml"`` per spec §5.2 so MLDashboard can
    # distinguish them from align-bridge runs.
    if result.lineage is None:
        # dataclass is frozen, but ``result`` is a plain @dataclass
        # (not frozen) -- direct attribute assignment is fine.
        result.lineage = _build_lineage(
            algo=algo,
            env_id=env_id,
            tenant_id=tenant_id,
            experiment_name=experiment_name,
            parent_run_id=parent_run_id,
            sdk_source="kailash-ml",
            sdk_version=_KML_VERSION,
            paradigm=_paradigm_for_classical(algo),
            base_model_ref=None,
            reference_model_ref=None,
            reward_model_ref=None,
            dataset_ref=None,
        )
    logger.info(
        "rl_train.ok",
        extra={
            "algorithm": algo,
            "env": env_id,
            "run_id": result.lineage.run_id if result.lineage else None,
            "mean_reward": result.mean_reward,
            "tenant_id": tenant_id,
            "sdk_source": "kailash-ml",
            "mode": "real",
        },
    )
    return result


# ---------------------------------------------------------------------------
# Bridge-adapter dispatch (W30 spec §3.1 step 2)
# ---------------------------------------------------------------------------


def _run_bridge_adapter(
    *,
    algo: str,
    env: Any,
    total_timesteps: int,
    hyperparameters: dict[str, Any] | None,
    policy: str | None,
    n_eval_episodes: int,
    seed: int | None,
    tenant_id: str | None,
    reference_model: Any | None,
    reward_model: Any | None,
    preference_dataset: Any | None,
    device: Any | None,
    experiment_name: str | None,
    parent_run_id: str | None,
    register_as: str | None,
) -> Any:
    """Resolve and drive a bridge adapter satisfying ``RLLifecycleProtocol``.

    Raises
    ------
    FeatureNotAvailableError
        ``kailash-align`` is not installed OR does not register ``algo``.
    ValueError
        A required kwarg for the bridge adapter is missing (e.g.
        ``algo="dpo"`` with no ``preference_dataset``).
    """
    from kailash_ml.rl.protocols import RLLifecycleProtocol

    # Lazy resolve — raises FeatureNotAvailableError if align is absent.
    adapter_cls = resolve_bridge_adapter(algo)

    # Construct adapter per spec §3.1 step 2 kwarg set.
    adapter_kwargs: dict[str, Any] = {
        "policy": policy,
        "reference_model": reference_model,
        "reward_model": reward_model,
        "preference_dataset": preference_dataset,
        "hyperparameters": dict(hyperparameters or {}),
        "device": device,
        "tenant_id": tenant_id,
    }
    # DPO-family adapters require ``preference_dataset``; PPO-RLHF
    # requires ``reward_model``. Surface the missing kwarg as a
    # typed ValueError BEFORE constructing the adapter so the caller
    # gets an actionable message (not a TypeError from the adapter
    # __init__). Per ``rules/zero-tolerance.md`` Rule 3 (no silent
    # fallbacks).
    _validate_bridge_kwargs(algo, adapter_kwargs)

    try:
        adapter = adapter_cls(**adapter_kwargs)
    except TypeError as exc:
        # Constructor signature mismatch — treat as an actionable
        # user error rather than let a low-level TypeError escape.
        raise ValueError(
            f"bridge adapter for algo={algo!r} rejected the kwargs "
            f"{sorted(adapter_kwargs)!r}: {exc}. The align-bridge "
            f"adapter contract is "
            f"specs/ml-rl-align-unification.md §3.1 step 2."
        ) from exc

    # Conformance gate per spec §2.3.
    if not isinstance(adapter, RLLifecycleProtocol):
        raise TypeError(
            f"bridge adapter {adapter_cls.__module__}."
            f"{adapter_cls.__name__} does not satisfy "
            f"RLLifecycleProtocol at runtime. This is a bug in "
            f"kailash-align; upgrade to a matching version."
        )

    # Drive the lifecycle. ``learn`` returns the populated
    # RLTrainingResult per the Protocol contract (see
    # protocols.RLLifecycleProtocol.learn docstring).
    adapter.build()
    logger.info(
        "rl_train.bridge.learn.start",
        extra={
            "algorithm": algo,
            "total_timesteps": total_timesteps,
            "tenant_id": tenant_id,
            "mode": "real",
        },
    )
    result = adapter.learn(
        total_timesteps,
        callbacks=[],
        eval_env_fn=env if callable(env) and not isinstance(env, str) else None,
        eval_freq=max(1, total_timesteps // 10) if total_timesteps > 0 else 1,
        n_eval_episodes=n_eval_episodes,
    )

    # Populate lineage with sdk_source="kailash-align" so MLDashboard
    # can render the provenance badge (spec §5.2).
    if getattr(result, "lineage", None) is None:
        base_model_ref = _model_ref(policy)
        ref_model_ref = _model_ref(reference_model)
        reward_ref = _model_ref(reward_model)
        dataset_ref = _dataset_ref(preference_dataset)
        align_version = _resolved_align_version()
        paradigm = _paradigm_for_bridge(adapter_cls)
        result.lineage = _build_lineage(
            algo=algo,
            env_id=(env if isinstance(env, str) else "text:preferences"),
            tenant_id=tenant_id,
            experiment_name=experiment_name,
            parent_run_id=parent_run_id,
            sdk_source="kailash-align",
            sdk_version=align_version,
            paradigm=paradigm,
            base_model_ref=base_model_ref,
            reference_model_ref=ref_model_ref,
            reward_model_ref=reward_ref,
            dataset_ref=dataset_ref,
        )

    logger.info(
        "rl_train.bridge.learn.ok",
        extra={
            "algorithm": algo,
            "run_id": result.lineage.run_id if result.lineage else None,
            "tenant_id": tenant_id,
            "sdk_source": "kailash-align",
            "mode": "real",
        },
    )
    return result


def _validate_bridge_kwargs(
    algo: str,
    adapter_kwargs: dict[str, Any],
) -> None:
    """Surface missing required bridge kwargs as typed ValueError.

    Spec §3.3: "If the bridge adapter constructor is missing a kwarg
    (e.g. user passed ``algo="dpo"`` without ``preference_dataset``),
    raise ``ValueError`` with actionable message — do NOT silently
    fallback." Per ``rules/zero-tolerance.md`` Rule 3.
    """
    # DPO-family algorithms require a preference dataset.
    _DPO_FAMILY = {"dpo", "online-dpo", "kto", "simpo", "cpo", "orpo", "bco"}
    if algo in _DPO_FAMILY and adapter_kwargs.get("preference_dataset") is None:
        raise ValueError(
            f"algo={algo!r} requires preference_dataset= (DPO-family). "
            f"Pass preference_dataset=<polars.DataFrame | "
            f"datasets.Dataset> via km.rl_train(..., preference_dataset=...)."
        )
    if algo in {"ppo-rlhf", "rloo", "grpo"} and (
        adapter_kwargs.get("reward_model") is None
    ):
        raise ValueError(
            f"algo={algo!r} requires reward_model= (RLHF PPO-family). "
            f"Pass reward_model=<str | model> via "
            f"km.rl_train(..., reward_model=...)."
        )


def _build_lineage(
    *,
    algo: str,
    env_id: str | None,
    tenant_id: str | None,
    experiment_name: str | None,
    parent_run_id: str | None,
    sdk_source: str,
    sdk_version: str,
    paradigm: str,
    base_model_ref: str | None,
    reference_model_ref: str | None,
    reward_model_ref: str | None,
    dataset_ref: str | None,
) -> RLLineage:
    """Construct an :class:`RLLineage` with spec §5.1 fields."""
    return RLLineage(
        run_id=str(uuid.uuid4()),
        experiment_name=experiment_name,
        tenant_id=tenant_id,
        base_model_ref=base_model_ref,
        reference_model_ref=reference_model_ref,
        reward_model_ref=reward_model_ref,
        dataset_ref=dataset_ref,
        env_spec=env_id,
        algorithm=algo,
        paradigm=paradigm,  # type: ignore[arg-type]  # Literal enforced at runtime
        parent_run_id=parent_run_id,
        sdk_source=sdk_source,  # type: ignore[arg-type]
        sdk_version=sdk_version,
        created_at=datetime.now(timezone.utc),
    )


_CLASSICAL_PARADIGMS: dict[str, str] = {
    "ppo": "on-policy",
    "a2c": "on-policy",
    "trpo": "on-policy",
    "maskable-ppo": "on-policy",
    "dqn": "off-policy",
    "sac": "off-policy",
    "td3": "off-policy",
    "ddpg": "off-policy",
    "bc": "offline",
    "cql": "offline",
    "iql": "offline",
    "decision-transformer": "offline",
}


def _paradigm_for_classical(algo: str) -> str:
    """Map a classical algo name to its paradigm for lineage."""
    lower = algo.lower() if isinstance(algo, str) else algo
    if isinstance(lower, str) and lower in _CLASSICAL_PARADIGMS:
        return _CLASSICAL_PARADIGMS[lower]
    # Default to on-policy for unknown classical names; the
    # classical registry already validated the name so this is a
    # never-reached safety net.
    return "on-policy"


def _paradigm_for_bridge(adapter_cls: Any) -> str:
    """Prefer the adapter's declared paradigm; fall back to ``"rlhf"``."""
    paradigm = getattr(adapter_cls, "paradigm", None)
    if isinstance(paradigm, str) and paradigm in {
        "on-policy",
        "off-policy",
        "offline",
        "rlhf",
    }:
        return paradigm
    return "rlhf"


def _model_ref(obj: Any) -> str | None:
    """Stringify a model reference for lineage.

    ``None`` -> ``None``; string -> string; anything else -> repr with
    class prefix. We never persist weights; lineage refs are labels.
    """
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    return f"{type(obj).__module__}.{type(obj).__name__}"


def _dataset_ref(obj: Any) -> str | None:
    """Stringify a dataset reference for lineage."""
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    name = f"{type(obj).__module__}.{type(obj).__name__}"
    # Best-effort row-count enrichment for common dataset types.
    try:
        n = len(obj)
        return f"{name}:rows={n}"
    except TypeError:
        return name


def _resolved_align_version() -> str:
    """Best-effort lookup of ``kailash_align.__version__``.

    Falls back to ``"unknown"`` if kailash-align is not importable
    at this point (should not happen since bridge-dispatch reached
    here only after a successful ``resolve_bridge_adapter``).
    """
    try:
        import kailash_align  # noqa: WPS433

        return str(getattr(kailash_align, "__version__", "unknown"))
    except ImportError:
        return "unknown"


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
