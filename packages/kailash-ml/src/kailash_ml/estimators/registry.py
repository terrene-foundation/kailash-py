# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Process-global registry of custom estimators for kailash-ml composites.

Cross-SDK alignment with kailash-rs#402 commit ``5429928c``. The registry
is keyed by the fully-qualified class path so ``register_estimator`` is
usable both as a decorator and as a function, and so the same class
registered from two import paths collapses to one entry.

The rule (per `rules/agent-reasoning.md` and the ticket): custom estimators
MUST be registered explicitly. The composite primitives (``Pipeline``,
``FeatureUnion``, ``ColumnTransformer``) consult this registry before
rejecting a step as "unknown", preventing both silent duck-type acceptance
and hardcoded allowlist lock-in.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Set, TypeVar

logger = logging.getLogger(__name__)

__all__ = [
    "is_registered_estimator",
    "register_estimator",
    "registered_estimators",
    "unregister_estimator",
]


# Keyed by (module, qualname) so two copies of the same class from
# different import paths collide on the same slot. Values are the class
# objects themselves for fast ``isinstance`` / identity checks.
_REGISTRY: dict[tuple[str, str], type] = {}
_LOCK = threading.Lock()


T = TypeVar("T", bound=type)


def _fqn(cls: type) -> tuple[str, str]:
    return (getattr(cls, "__module__", "__unknown__"), cls.__qualname__)


def register_estimator(cls: T) -> T:
    """Register a custom estimator class. Usable as decorator or function.

    Idempotent: re-registering the same class is a no-op. Thread-safe.
    """
    if not isinstance(cls, type):
        raise TypeError(
            f"register_estimator expects a class, got {type(cls).__name__!r}; "
            "wrap decorator at the class definition, not the instance"
        )
    key = _fqn(cls)
    with _LOCK:
        existing = _REGISTRY.get(key)
        if existing is cls:
            return cls  # idempotent
        _REGISTRY[key] = cls
    logger.debug(
        "kailash_ml.estimators.register",
        extra={"estimator_module": key[0], "estimator_qualname": key[1]},
    )
    return cls


def unregister_estimator(cls: type) -> bool:
    """Remove a custom estimator class from the registry.

    Returns True if the class was registered and removed, False otherwise.
    """
    key = _fqn(cls)
    with _LOCK:
        removed = _REGISTRY.pop(key, None) is not None
    if removed:
        logger.debug(
            "kailash_ml.estimators.unregister",
            extra={"estimator_module": key[0], "estimator_qualname": key[1]},
        )
    return removed


def is_registered_estimator(obj: Any) -> bool:
    """True if ``obj`` is (an instance of) a class registered with
    ``register_estimator``. Accepts both classes and instances.
    """
    cls = obj if isinstance(obj, type) else type(obj)
    key = _fqn(cls)
    with _LOCK:
        return _REGISTRY.get(key) is cls


def registered_estimators() -> Set[type]:
    """Return a snapshot of every registered estimator class."""
    with _LOCK:
        return set(_REGISTRY.values())
