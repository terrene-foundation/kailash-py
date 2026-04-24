# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Framework integration registry.

Implements ``specs/ml-autolog.md §3.2`` (``FrameworkIntegration`` ABC)
and §4.4 (``register_integration`` / ``unregister_integration``).

The registry is process-local — every process that imports
:mod:`kailash_ml.autolog` starts with an empty list and populates it via
explicit calls to :func:`register_integration`. W23.a ships the ABC
only; framework-specific integrations (``SklearnIntegration``,
``LightgbmIntegration``, ``LightningIntegration``, …) land in W23.b–d.

Per ``rules/orphan-detection.md`` this registry has production call
sites in :mod:`kailash_ml.autolog._context` (the
:func:`~kailash_ml.autolog.autolog` async CM reads
:data:`_REGISTERED_INTEGRATIONS` during auto-detect per §4.1 and
resolves explicit framework names against it per §4.2). The ABC alone
would be an orphan; the context manager is its consumer.
"""
from __future__ import annotations

import logging
from typing import List, Sequence, Type

# FrameworkIntegration ABC moved to ``_types.py`` to break the static
# cycle with ``config.py``. Re-exported here for backward compatibility.
from kailash_ml.autolog._types import AutologConfig, FrameworkIntegration

__all__ = [
    "AutologConfig",
    "FrameworkIntegration",
    "register_integration",
    "unregister_integration",
    "registered_integration_names",
]


logger = logging.getLogger(__name__)


# Registered integration CLASSES (not instances). The context manager
# instantiates them per-block so each `async with autolog()` has a
# fresh state bag. Attach/detach never runs on a shared instance.
_REGISTERED_INTEGRATIONS: List[Type[FrameworkIntegration]] = []


def register_integration(
    integration_cls: Type[FrameworkIntegration],
) -> Type[FrameworkIntegration]:
    """Register a :class:`FrameworkIntegration` subclass.

    Usable as a decorator per ``specs/ml-autolog.md §4.4``::

        @register_integration
        class FastaiIntegration(FrameworkIntegration):
            name = "fastai"
            ...

    Re-registering the same class is an INFO log + no-op. Registering a
    different class under the SAME ``name`` raises ``ValueError`` — the
    name must be unique across the process per §4.2 (otherwise the
    dispatch in :func:`~kailash_ml.autolog.autolog` is non-deterministic).

    Returns the class unchanged so the decorator form composes.
    """
    if not isinstance(integration_cls, type) or not issubclass(
        integration_cls, FrameworkIntegration
    ):
        raise TypeError(
            f"register_integration expects a FrameworkIntegration subclass, "
            f"got {integration_cls!r}"
        )
    if not isinstance(integration_cls.name, str) or not integration_cls.name:
        raise ValueError(
            f"Integration class {integration_cls.__name__} must define a "
            f"non-empty class-level `name` attribute"
        )

    for existing in _REGISTERED_INTEGRATIONS:
        if existing is integration_cls:
            logger.debug(
                "autolog.register.idempotent",
                extra={"integration": integration_cls.name},
            )
            return integration_cls
        if existing.name == integration_cls.name:
            raise ValueError(
                f"Integration name {integration_cls.name!r} is already "
                f"registered to {existing.__module__}.{existing.__name__}; "
                f"refusing to re-register as "
                f"{integration_cls.__module__}.{integration_cls.__name__}"
            )

    _REGISTERED_INTEGRATIONS.append(integration_cls)
    logger.info(
        "autolog.register",
        extra={"integration": integration_cls.name},
    )
    return integration_cls


def unregister_integration(name: str) -> None:
    """Remove a previously-registered integration by name.

    Idempotent — unregistering an unknown name is a DEBUG log + no-op.
    """
    for idx, existing in enumerate(_REGISTERED_INTEGRATIONS):
        if existing.name == name:
            del _REGISTERED_INTEGRATIONS[idx]
            logger.info("autolog.unregister", extra={"integration": name})
            return
    logger.debug(
        "autolog.unregister.not_found",
        extra={"integration": name},
    )


def registered_integration_names() -> Sequence[str]:
    """Return the names of every currently-registered integration.

    Ordered by registration order per §4.1. Used by
    :class:`~kailash.ml.errors.AutologUnknownFrameworkError` messages
    to tell the user which names ARE valid.
    """
    return tuple(integ.name for integ in _REGISTERED_INTEGRATIONS)
