# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Lazy dispatch from ``km.rl_train`` to ``kailash-align`` bridge adapters.

Per ``specs/ml-rl-align-unification.md`` §3 (dispatch) + §7 (dependency
topology):

* ``kailash-ml`` declares the :class:`~kailash_ml.rl.protocols.RLLifecycleProtocol`
  contract and this dispatch module.
* ``kailash-align`` 0.5.0+ ships ``kailash_align.rl_bridge`` with
  concrete adapters (``dpo``, ``ppo-rlhf``, ``rloo``, ``online-dpo``,
  ``kto``, ``simpo``, ``cpo``, ``grpo``, ``orpo``, ``bco``) that satisfy
  the Protocol and call :func:`register_bridge_adapter` at align's
  own import time.
* ``km.rl_train(algo=<name>)`` calls :func:`resolve_bridge_adapter`
  which lazily imports ``kailash_align.rl_bridge`` when the name is
  not in the first-party classical registry.

Zero align-side imports at module scope — importing
``kailash_ml.rl.align_adapter`` is safe without ``kailash-align``
installed; the lazy resolver raises :class:`FeatureNotAvailableError`
with a naming-the-extra message per
``rules/dependencies.md`` § "Optional Extras with Loud Failure".
"""
from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kailash_ml.rl.protocols import RLLifecycleProtocol

logger = logging.getLogger(__name__)

__all__ = [
    "BRIDGE_ADAPTERS",
    "FeatureNotAvailableError",
    "register_bridge_adapter",
    "resolve_bridge_adapter",
]


# Module-scope registry populated by ``kailash_align.rl_bridge`` at its
# OWN import time via :func:`register_bridge_adapter`. Starts empty;
# this module does NOT import ``kailash_align`` to populate it.
BRIDGE_ADAPTERS: dict[str, type["RLLifecycleProtocol"]] = {}


class FeatureNotAvailableError(Exception):
    """Raised when a bridge adapter name is not resolvable.

    Most common cause: ``kailash-align`` (or the ``[rl-bridge]`` extra)
    is not installed. The error message always names the missing extra
    per ``rules/dependencies.md`` § "Optional Extras with Loud Failure".

    Attributes
    ----------
    algo_name:
        The algorithm name the caller tried to resolve.
    """

    def __init__(self, algo_name: str, *, message: str | None = None) -> None:
        self.algo_name = algo_name
        if message is None:
            message = (
                f"algo={algo_name!r} requires kailash-align[rl-bridge]; "
                f"install via 'pip install kailash-align[rl-bridge]'"
            )
        super().__init__(message)


def register_bridge_adapter(
    name: str,
    adapter_cls: type["RLLifecycleProtocol"],
) -> None:
    """Register a bridge adapter class under ``name``.

    Called by ``kailash_align.rl_bridge`` during its own import. Idempotent
    when re-registering the exact same class; raises ``ValueError`` when a
    DIFFERENT class is registered under the same name (cross-SDK drift
    guard — two align versions trying to claim the same algo).

    Parameters
    ----------
    name:
        Algorithm name (``"dpo"``, ``"ppo-rlhf"``, ...).
    adapter_cls:
        Class whose instances satisfy :class:`RLLifecycleProtocol`.
    """
    if not isinstance(name, str) or not name:
        raise ValueError(
            f"register_bridge_adapter: name must be a non-empty string "
            f"(got {name!r})"
        )
    if not isinstance(adapter_cls, type):
        raise ValueError(
            f"register_bridge_adapter: adapter_cls must be a class "
            f"(got {adapter_cls!r})"
        )
    existing = BRIDGE_ADAPTERS.get(name)
    if existing is not None and existing is not adapter_cls:
        raise ValueError(
            f"bridge adapter {name!r} is already registered to "
            f"{existing.__module__}.{existing.__name__}; cannot re-register "
            f"as {adapter_cls.__module__}.{adapter_cls.__name__}"
        )
    BRIDGE_ADAPTERS[name] = adapter_cls
    logger.info(
        "rl.bridge.register",
        extra={
            "algo": name,
            "adapter_cls": f"{adapter_cls.__module__}.{adapter_cls.__name__}",
            "mode": "real",
        },
    )


def resolve_bridge_adapter(algo_name: str) -> type["RLLifecycleProtocol"]:
    """Resolve ``algo_name`` to a bridge adapter class.

    Resolution order:

    1. If ``algo_name`` is already in :data:`BRIDGE_ADAPTERS` (because a
       prior import of ``kailash_align.rl_bridge`` registered it),
       return the class directly.
    2. Otherwise lazy-import ``kailash_align.rl_bridge``; its import
       side-effect is to register every bridge adapter. Re-check
       :data:`BRIDGE_ADAPTERS`.
    3. If still not present, raise :class:`FeatureNotAvailableError` with
       a message naming the ``[rl-bridge]`` extra.

    Parameters
    ----------
    algo_name:
        Algorithm name (``"dpo"``, ``"ppo-rlhf"``, ...).

    Returns
    -------
    type[RLLifecycleProtocol]
        The adapter class. Callers construct an instance and assert
        ``isinstance(instance, RLLifecycleProtocol)`` before use.

    Raises
    ------
    FeatureNotAvailableError
        ``kailash-align`` is not installed OR the installed
        ``kailash-align`` does not register ``algo_name``.
    """
    logger.info(
        "rl.bridge.resolve.start",
        extra={"algo": algo_name, "mode": "real"},
    )
    if algo_name in BRIDGE_ADAPTERS:
        adapter_cls = BRIDGE_ADAPTERS[algo_name]
        logger.info(
            "rl.bridge.resolve.ok",
            extra={
                "algo": algo_name,
                "adapter_cls": (f"{adapter_cls.__module__}.{adapter_cls.__name__}"),
                "source": "registry",
                "mode": "real",
            },
        )
        return adapter_cls

    # Lazy import — ``kailash_align`` is an optional dependency per
    # spec §7. Per ``rules/dependencies.md`` § "Optional Extras with
    # Loud Failure" the ImportError surfaces as a typed, actionable
    # error naming the ``[rl-bridge]`` extra.
    try:
        importlib.import_module("kailash_align.rl_bridge")
    except ImportError as exc:
        logger.error(
            "rl.bridge.resolve.fail",
            extra={
                "algo": algo_name,
                "error": "kailash-align not installed",
                "cause": str(exc),
            },
        )
        raise FeatureNotAvailableError(algo_name) from exc

    # Import succeeded; check the registry again. If the name still
    # is not present, align is installed but does not ship a bridge
    # adapter for this algo (version drift or typo).
    if algo_name in BRIDGE_ADAPTERS:
        adapter_cls = BRIDGE_ADAPTERS[algo_name]
        logger.info(
            "rl.bridge.resolve.ok",
            extra={
                "algo": algo_name,
                "adapter_cls": (f"{adapter_cls.__module__}.{adapter_cls.__name__}"),
                "source": "lazy_import",
                "mode": "real",
            },
        )
        return adapter_cls

    message = (
        f"algo={algo_name!r} is not registered by kailash_align.rl_bridge "
        f"(kailash-align is installed but does not ship a bridge adapter for "
        f"this algorithm; available: {sorted(BRIDGE_ADAPTERS)!r}). "
        f"Upgrade via 'pip install --upgrade kailash-align[rl-bridge]' or "
        f"check the spelling."
    )
    logger.error(
        "rl.bridge.resolve.fail",
        extra={
            "algo": algo_name,
            "error": "not_registered",
            "available": sorted(BRIDGE_ADAPTERS),
        },
    )
    raise FeatureNotAvailableError(algo_name, message=message)
