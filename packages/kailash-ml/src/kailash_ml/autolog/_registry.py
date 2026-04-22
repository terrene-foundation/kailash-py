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
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, List, Sequence, Type

if TYPE_CHECKING:
    from kailash_ml.autolog.config import AutologConfig
    from kailash_ml.tracking import ExperimentRun


__all__ = [
    "FrameworkIntegration",
    "register_integration",
    "unregister_integration",
    "registered_integration_names",
]


logger = logging.getLogger(__name__)


class FrameworkIntegration(ABC):
    """Abstract base for every framework autolog integration.

    Every concrete integration (Lightning, sklearn, lightgbm,
    transformers, xgboost, statsmodels, polars) MUST subclass and
    implement :meth:`is_available`, :meth:`attach`, :meth:`detach`.

    Lifecycle per ``specs/ml-autolog.md §3.2``:

    1. :meth:`is_available` — classmethod checked by
       :func:`~kailash_ml.autolog.autolog` during auto-detect (§4.1).
       MUST inspect ``sys.modules`` — NOT import the framework (surprise
       imports of torch/transformers cost tens of seconds).
    2. :meth:`attach` — called on ``__aenter__`` with the ambient
       :class:`~kailash_ml.tracking.ExperimentRun` and the frozen
       :class:`~kailash_ml.autolog.config.AutologConfig`. Installs hooks
       / callbacks / wrappers within the block's scope. Double-attach
       without an intervening :meth:`detach` raises
       :class:`~kailash.ml.errors.AutologDoubleAttachError`.
    3. :meth:`detach` — called on ``__aexit__`` (inside ``finally:`` —
       runs even if the user's ``async with`` body raised). Idempotent.

    Subclasses MUST define a unique :attr:`name` class attribute used by
    :func:`register_integration` and by the spec-mandated typed error
    messages (§4.2 / §4.3).
    """

    name: ClassVar[str]
    """Unique registration name for this integration. Used by
    :func:`~kailash_ml.autolog.autolog` for explicit framework
    selection per §4.2 + §4.3."""

    def __init__(self) -> None:
        self._attached = False

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Return True iff this framework's hook surface is importable.

        MUST inspect ``sys.modules`` only per §4.1 — importing the
        framework here produces surprise-imports that violate the
        "zero overhead when unused" contract.

        Raising :class:`ImportError` from this method is BLOCKED per
        §10.1 MUST. Unavailable frameworks return ``False``; they do
        NOT raise.
        """

    @abstractmethod
    def attach(self, run: "ExperimentRun", config: "AutologConfig") -> None:
        """Install callbacks / hooks / wrappers for this framework.

        Called on ``async with autolog():`` entry. The integration
        captures references to ``run`` and ``config`` so the hooks it
        installs can emit metrics / params / artifacts against the
        ambient run.

        Double-attach is BLOCKED per §3.2. Concrete subclasses SHOULD
        delegate the guard to :meth:`_guard_double_attach` at the top
        of their override.

        :raises AutologDoubleAttachError: if ``attach`` is called twice
            without an intervening :meth:`detach`.
        :raises AutologAttachError: if the framework refuses the hook
            installation (e.g. API version mismatch); the framework's
            original exception is preserved as ``__cause__``.
        """

    @abstractmethod
    def detach(self) -> None:
        """Remove callbacks / hooks / wrappers installed by
        :meth:`attach`.

        Idempotent per §3.2 — calling detach on an already-detached
        integration is a no-op (NOT an error). This is what makes
        :meth:`kailash_ml.autolog.config.AutologHandle.stop` safe to
        call multiple times.

        MUST run inside the context manager's ``finally:`` even if the
        user's ``async with`` body raised an exception per §3.2.
        """

    def _guard_double_attach(self) -> None:
        """Helper for subclasses — raise
        :class:`~kailash.ml.errors.AutologDoubleAttachError` when
        called on an already-attached instance; flip the flag otherwise.

        Concrete :meth:`attach` overrides call this as their first
        statement.
        """
        from kailash.ml.errors import AutologDoubleAttachError

        if self._attached:
            raise AutologDoubleAttachError(
                reason=(
                    f"FrameworkIntegration {self.name!r} is already "
                    "attached; detach() must be called before a second "
                    "attach(). Check for nested `async with "
                    "km.autolog(): ...` blocks."
                )
            )
        self._attached = True

    def _mark_detached(self) -> None:
        """Helper for subclasses — flip the attached flag back to
        False so a subsequent :meth:`attach` on the same instance is
        valid. Concrete :meth:`detach` overrides call this in their
        ``finally:`` block.
        """
        self._attached = False


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
