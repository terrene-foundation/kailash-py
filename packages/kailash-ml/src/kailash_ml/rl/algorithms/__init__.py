# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Algorithm adapter layer for RL.

Per ``specs/ml-rl-algorithms.md`` §2, each algorithm supported by
``km.rl_train`` is exposed as a thin adapter over Stable-Baselines3 (or
sb3-contrib, or a future deferred backend). The adapter owns:

* lazy import of the backend class (``[rl]`` gated — ``rules/dependencies``)
* default policy + default hyperparameters
* construction of the ``(model, env)`` pair
* ``learn(...)`` that returns the underlying backend model
* ``save`` / ``load``

Metrics extraction lives in ``kailash_ml.rl.trainer._KailashRLCallback``;
adapters themselves do NOT own metric families so the surface stays
uniform across backends.

**Deferred adapters.** MaskablePPO and DecisionTransformer are declared
non-goals of W29 (per ``specs/ml-rl-core.md`` §1.2 RA-02 / RA-03) but
W29's dispatch table reserves both names. MaskablePPO uses sb3-contrib
which is a soft dependency under ``[rl]``; when installed the adapter
works; when absent we raise a typed ``ImportError`` with the extra
mentioned. DecisionTransformer has no stock SB3 source; v1 raises
``FeatureNotYetSupportedError`` pointing at the upstream tracking issue.

This module deliberately avoids a top-level ``import stable_baselines3``
— everything that touches SB3 lives inside the adapter method that the
trainer calls, so ``from kailash_ml.rl.algorithms import PPOAdapter``
works without the extra installed.
"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from kailash_ml.errors import FeatureNotYetSupportedError, RLError

logger = logging.getLogger(__name__)


__all__ = [
    "AlgorithmAdapter",
    "PPOAdapter",
    "SACAdapter",
    "DQNAdapter",
    "A2CAdapter",
    "TD3Adapter",
    "DDPGAdapter",
    "MaskablePPOAdapter",
    "DecisionTransformerAdapter",
    "load_adapter_class",
]


# ---------------------------------------------------------------------------
# Shared SB3 import helpers
# ---------------------------------------------------------------------------


def _require_sb3() -> Any:
    """Import ``stable_baselines3`` lazily with a loud, actionable error."""
    try:
        import stable_baselines3 as sb3  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover — exercised only without [rl]
        raise ImportError(
            "stable-baselines3 is required for RL. "
            "Install with: pip install kailash-ml[rl]"
        ) from exc
    return sb3


def _require_sb3_contrib() -> Any:
    """Import ``sb3_contrib`` lazily; raise a loud, actionable error."""
    try:
        import sb3_contrib  # noqa: WPS433
    except ImportError as exc:
        raise ImportError(
            "maskable_ppo requires sb3-contrib. "
            "Install with: pip install sb3-contrib>=2.3"
        ) from exc
    return sb3_contrib


# ---------------------------------------------------------------------------
# AlgorithmAdapter base
# ---------------------------------------------------------------------------


class AlgorithmAdapter:
    """Thin base class for SB3-backed algorithm adapters.

    Subclasses declare the class-level constants (``name``, ``paradigm``,
    ``requires_extra``, ``default_policy``, ``default_hyperparameters``,
    ``_sb3_class_path``) and inherit ``build`` / ``learn`` / ``save`` /
    ``load``. When the underlying behavior diverges (e.g. MaskablePPO
    uses sb3-contrib, DecisionTransformer is deferred), subclasses
    override the relevant method.
    """

    name: ClassVar[str] = ""
    paradigm: ClassVar[str] = "on-policy"
    buffer_kind: ClassVar[str] = "rollout"
    requires_extra: ClassVar[tuple[str, ...]] = ("rl",)
    default_policy: ClassVar[str] = "MlpPolicy"
    default_hyperparameters: ClassVar[dict[str, Any]] = {}

    # Import path to the backend class (``module:attr``). Subclasses MUST
    # set this or override ``_resolve_class``.
    _sb3_class_path: ClassVar[str] = ""

    def __init__(
        self,
        *,
        env: Any,
        policy: str | None = None,
        hyperparameters: dict[str, Any] | None = None,
        seed: int | None = None,
        tenant_id: str | None = None,
        device: str | None = None,
    ) -> None:
        self._env = env
        self._policy = policy or self.default_policy
        self._hp = {**self.default_hyperparameters, **(hyperparameters or {})}
        self._seed = seed
        self._tenant_id = tenant_id
        self._device = device
        self._model: Any = None

    # -- backend resolution ------------------------------------------------

    @classmethod
    def _resolve_class(cls) -> Any:
        """Import + return the underlying backend class."""
        if not cls._sb3_class_path:
            raise RLError(
                reason="adapter_missing_backend_path",
                algorithm=cls.name,
            )
        _require_sb3()  # ensure [rl] is installed; do not swallow ImportError
        module_name, attr = cls._sb3_class_path.split(":", 1)
        module = importlib.import_module(module_name)
        return getattr(module, attr)

    # -- lifecycle ---------------------------------------------------------

    def build(self) -> Any:
        """Instantiate the backend model. Idempotent."""
        if self._model is not None:
            return self._model
        cls = self._resolve_class()
        kwargs: dict[str, Any] = dict(self._hp)
        if self._seed is not None:
            kwargs.setdefault("seed", self._seed)
        if self._device is not None:
            kwargs.setdefault("device", self._device)
        kwargs.setdefault("verbose", 0)
        self._model = cls(self._policy, self._env, **kwargs)
        logger.info(
            "rl.algorithm.build",
            extra={
                "algorithm": self.name,
                "policy": self._policy,
                "seed": self._seed,
                "tenant_id": self._tenant_id,
            },
        )
        return self._model

    def learn(
        self,
        total_timesteps: int,
        *,
        callback: Any | None = None,
        progress_bar: bool = False,
    ) -> Any:
        """Run the backend training loop."""
        model = self.build()
        model.learn(
            total_timesteps=total_timesteps,
            callback=callback,
            progress_bar=progress_bar,
        )
        return model

    def save(self, path: str | Path) -> Path:
        """Persist the trained model; returns the saved path."""
        if self._model is None:
            raise RLError(reason="save_before_train", algorithm=self.name)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._model.save(str(p))
        return p

    @classmethod
    def load(cls, path: str | Path) -> Any:
        """Load a previously-saved model via the backend class."""
        backend = cls._resolve_class()
        return backend.load(str(path))


# ---------------------------------------------------------------------------
# Per-algorithm adapters
# ---------------------------------------------------------------------------


class PPOAdapter(AlgorithmAdapter):
    name = "ppo"
    paradigm = "on-policy"
    buffer_kind = "rollout"
    default_policy = "MlpPolicy"
    default_hyperparameters = {
        "n_steps": 2048,
        "batch_size": 64,
        "n_epochs": 10,
        "learning_rate": 3e-4,
        "gamma": 0.99,
        "gae_lambda": 0.95,
        "clip_range": 0.2,
        "vf_coef": 0.5,
        "ent_coef": 0.0,
        "max_grad_norm": 0.5,
    }
    _sb3_class_path = "stable_baselines3:PPO"


class A2CAdapter(AlgorithmAdapter):
    name = "a2c"
    paradigm = "on-policy"
    buffer_kind = "rollout"
    default_policy = "MlpPolicy"
    # Per spec §3.4 the adapter pins its own GAE defaults (a2c: gamma=0.99,
    # gae_lambda=1.0) rather than inheriting buffer defaults.
    default_hyperparameters = {
        "n_steps": 5,
        "learning_rate": 7e-4,
        "gamma": 0.99,
        "gae_lambda": 1.0,
        "ent_coef": 0.0,
        "vf_coef": 0.5,
        "max_grad_norm": 0.5,
    }
    _sb3_class_path = "stable_baselines3:A2C"


class DQNAdapter(AlgorithmAdapter):
    name = "dqn"
    paradigm = "off-policy"
    buffer_kind = "replay"
    default_policy = "MlpPolicy"
    default_hyperparameters = {
        "learning_rate": 1e-4,
        "buffer_size": 1_000_000,
        "learning_starts": 50_000,
        "batch_size": 32,
        "tau": 1.0,
        "gamma": 0.99,
        "train_freq": 4,
        "target_update_interval": 10_000,
        "exploration_fraction": 0.1,
        "exploration_final_eps": 0.05,
    }
    _sb3_class_path = "stable_baselines3:DQN"


class SACAdapter(AlgorithmAdapter):
    name = "sac"
    paradigm = "off-policy"
    buffer_kind = "replay"
    default_policy = "MlpPolicy"
    default_hyperparameters = {
        "learning_rate": 3e-4,
        "buffer_size": 1_000_000,
        "learning_starts": 100,
        "batch_size": 256,
        "tau": 0.005,
        "gamma": 0.99,
        "train_freq": 1,
        "gradient_steps": 1,
        "ent_coef": "auto",
    }
    _sb3_class_path = "stable_baselines3:SAC"


class TD3Adapter(AlgorithmAdapter):
    name = "td3"
    paradigm = "off-policy"
    buffer_kind = "replay"
    default_policy = "MlpPolicy"
    default_hyperparameters = {
        "learning_rate": 1e-3,
        "buffer_size": 1_000_000,
        "learning_starts": 100,
        "batch_size": 100,
        "tau": 0.005,
        "gamma": 0.99,
        "policy_delay": 2,
        "target_policy_noise": 0.2,
        "target_noise_clip": 0.5,
    }
    _sb3_class_path = "stable_baselines3:TD3"


class DDPGAdapter(AlgorithmAdapter):
    name = "ddpg"
    paradigm = "off-policy"
    buffer_kind = "replay"
    default_policy = "MlpPolicy"
    default_hyperparameters = {
        "learning_rate": 1e-3,
        "buffer_size": 1_000_000,
        "learning_starts": 100,
        "batch_size": 100,
        "tau": 0.005,
        "gamma": 0.99,
    }
    _sb3_class_path = "stable_baselines3:DDPG"


class MaskablePPOAdapter(AlgorithmAdapter):
    """Adapter for ``sb3_contrib.MaskablePPO``.

    MaskablePPO is declared post-1.0 in ``specs/ml-rl-core.md`` §1.2
    RA-02 but sb3-contrib is already a sibling of stable-baselines3 and
    can be installed via the same ``[rl]`` extra as soon as operators
    choose to. The adapter therefore emits a loud ``ImportError`` when
    sb3-contrib is missing (per ``rules/dependencies.md`` § "Optional
    Extras with Loud Failure") rather than a silent no-op.
    """

    name = "maskable-ppo"
    paradigm = "on-policy"
    buffer_kind = "rollout"
    default_policy = "MlpPolicy"
    default_hyperparameters = {
        "n_steps": 2048,
        "batch_size": 64,
        "n_epochs": 10,
        "learning_rate": 3e-4,
        "gamma": 0.99,
        "gae_lambda": 0.95,
        "clip_range": 0.2,
    }
    _sb3_class_path = "sb3_contrib:MaskablePPO"

    @classmethod
    def _resolve_class(cls) -> Any:
        _require_sb3_contrib()
        module = importlib.import_module("sb3_contrib")
        return module.MaskablePPO


class DecisionTransformerAdapter(AlgorithmAdapter):
    """Deferred adapter — Decision Transformer is post-1.0 (RA-03).

    Unlike classical RL algorithms, DT treats RL as sequence modelling
    under a return-conditioned causal transformer and has a DISTINCT
    Protocol (no ``env.step`` rollout loop). 1.0.0 does not attempt to
    collapse DT into the ``AlgorithmAdapter`` shape; it gets its own
    Protocol and facade in 1.2.0+ under ``[rl]``.
    """

    name = "decision-transformer"
    paradigm = "offline"
    buffer_kind = "dataset"

    def __init__(self, **kwargs: Any) -> None:  # noqa: D401 — override signature
        # DT doesn't fit the AlgorithmAdapter shape — we refuse at construction
        # so callers don't see a partially-built adapter.
        raise FeatureNotYetSupportedError(
            reason="decision_transformer_deferred_to_1_2",
            algorithm="decision-transformer",
            tracking="https://github.com/terrene-foundation/kailash-py/"
            "issues?q=label%3Arl-RA-03",
        )

    @classmethod
    def _resolve_class(cls) -> Any:
        raise FeatureNotYetSupportedError(
            reason="decision_transformer_deferred_to_1_2",
            algorithm="decision-transformer",
        )

    @classmethod
    def load(cls, path: str | Path) -> Any:
        raise FeatureNotYetSupportedError(
            reason="decision_transformer_deferred_to_1_2",
            algorithm="decision-transformer",
            path=str(path),
        )


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


_ADAPTER_REGISTRY: dict[str, type[AlgorithmAdapter]] = {
    "ppo": PPOAdapter,
    "a2c": A2CAdapter,
    "dqn": DQNAdapter,
    "sac": SACAdapter,
    "td3": TD3Adapter,
    "ddpg": DDPGAdapter,
    "maskable-ppo": MaskablePPOAdapter,
    "maskable_ppo": MaskablePPOAdapter,
    "decision-transformer": DecisionTransformerAdapter,
    "decision_transformer": DecisionTransformerAdapter,
}

# Uppercase aliases (legacy + symmetry with W29's ``algo="PPO"`` surface).
_ADAPTER_REGISTRY["PPO"] = PPOAdapter
_ADAPTER_REGISTRY["A2C"] = A2CAdapter
_ADAPTER_REGISTRY["DQN"] = DQNAdapter
_ADAPTER_REGISTRY["SAC"] = SACAdapter
_ADAPTER_REGISTRY["TD3"] = TD3Adapter
_ADAPTER_REGISTRY["DDPG"] = DDPGAdapter
_ADAPTER_REGISTRY["MaskablePPO"] = MaskablePPOAdapter
_ADAPTER_REGISTRY["DecisionTransformer"] = DecisionTransformerAdapter


def load_adapter_class(algorithm: str) -> type[AlgorithmAdapter]:
    """Look up an adapter class by algorithm name.

    Raises
    ------
    RLError
        Algorithm is unknown; ``reason`` is ``"unknown_algorithm"``.
    """
    if algorithm in _ADAPTER_REGISTRY:
        return _ADAPTER_REGISTRY[algorithm]
    lower = algorithm.lower() if isinstance(algorithm, str) else algorithm
    if isinstance(lower, str) and lower in _ADAPTER_REGISTRY:
        return _ADAPTER_REGISTRY[lower]
    raise RLError(
        reason="unknown_algorithm",
        algorithm=algorithm,
        supported=sorted(
            {k for k in _ADAPTER_REGISTRY if "_" not in k and not k.isupper()}
        ),
    )


# Re-exported convenience: callers occasionally want the full list of
# user-facing canonical names (no aliases, no uppercase synonyms).
def supported_algorithm_names() -> list[str]:
    return sorted(
        {k for k, v in _ADAPTER_REGISTRY.items() if not k.isupper() and "_" not in k}
    )


# Registration hook for user-defined adapters (§2 of the algorithm spec).
def register_algorithm(name: str, adapter_cls: type[AlgorithmAdapter]) -> None:
    """Register a user-defined adapter under ``name``.

    Re-registering the exact same class is idempotent; overwriting with a
    different class raises ``RLError(reason="algorithm_name_occupied")``.
    """
    if not isinstance(adapter_cls, type) or not issubclass(
        adapter_cls, AlgorithmAdapter
    ):
        raise RLError(
            reason="adapter_not_subclass",
            algorithm_name=name,
            adapter=str(adapter_cls),
        )
    existing = _ADAPTER_REGISTRY.get(name)
    if existing is not None and existing is not adapter_cls:
        raise RLError(reason="algorithm_name_occupied", algorithm_name=name)
    _ADAPTER_REGISTRY[name] = adapter_cls


_CallbackBuilder = Callable[[], Any]  # reserved for trainer.py use
