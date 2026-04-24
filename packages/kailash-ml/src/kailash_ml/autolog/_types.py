# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared types for ``kailash_ml.autolog``.

This module breaks the static import cycle between
:mod:`kailash_ml.autolog.config` and :mod:`kailash_ml.autolog._registry`.
Both files previously back-edged each other under ``TYPE_CHECKING`` —
the cycle was benign at runtime but flagged by static analysers and
created surprise during import-graph audits.

Both ``AutologConfig`` (the frozen configuration dataclass) and
``FrameworkIntegration`` (the abstract base for every concrete
integration) are defined here. ``config.py`` and ``_registry.py``
re-export them so existing
``from kailash_ml.autolog.config import AutologConfig`` and
``from kailash_ml.autolog._registry import FrameworkIntegration``
import paths continue to resolve unchanged.

``ExperimentRun`` remains a forward-reference string in
:meth:`FrameworkIntegration.attach` / :meth:`flush` — it is owned by
:mod:`kailash_ml.tracking` which has its own dependency graph; importing
it here would re-introduce the cross-cutting cycle this module was
created to prevent.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:  # pragma: no cover - typing only
    from kailash_ml.tracking import ExperimentRun


__all__ = ["AutologConfig", "FrameworkIntegration"]


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutologConfig:
    """Immutable configuration snapshot for a single ``km.autolog()`` block.

    Constructed inside :func:`kailash_ml.autolog.autolog` from the
    positional + keyword arguments the user supplied. Passed to every
    :meth:`FrameworkIntegration.attach` call so each integration reads
    from a consistent, non-mutating view — mutating the config mid-block
    would produce cross-framework state divergence.

    Frozen per ``specs/ml-autolog.md §4.0 MUST``.
    """

    frameworks: tuple[str, ...] = ("auto",)
    """Positional framework names or ``("auto",)`` for sys.modules-based
    detection (§4.1). When not ``("auto",)``, every entry MUST resolve to
    a registered integration per §4.2 — unknown names raise
    :class:`~kailash.ml.errors.AutologUnknownFrameworkError`.
    """

    log_models: bool = True
    """Emit ``log_model()`` on fit-exit for fitted estimators /
    checkpoints / boosters (§2.1)."""

    log_datasets: bool = True
    """Emit schema fingerprint for training data (§2.1)."""

    log_figures: bool = True
    """Emit figures (confusion matrix, classification report, feature
    importance) via ``log_figure`` (§2.1)."""

    log_system_metrics: bool = False
    """Emit CPU / GPU util + memory per step. Requires ``psutil``; off
    by default per §2.1."""

    system_metrics_interval_s: int = 5
    """Seconds between system-metrics samples when
    :attr:`log_system_metrics` is True. Locked to 5s per Phase-B Round
    2b §A.2 SAFE-DEFAULT A-05."""

    sample_rate_steps: int = 1
    """Emit per-step metrics every Nth step. 1 = every step. Ignored
    by epoch-level metrics per §2.1. Per Phase-B A-03, default stays at
    1 for epoch-level; step-level integrations apply 1-in-10 sampling
    on long runs."""

    disable: tuple[str, ...] = ()
    """Framework names to skip even if detected. Unknown names raise
    :class:`~kailash.ml.errors.AutologUnknownFrameworkError` per §4.3.
    """

    disable_metrics: tuple[str, ...] = ()
    """Glob patterns for metric keys to drop at emit time (§5.2).
    Each integration is responsible for honoring these at its own
    ``log_metric`` call sites.
    """

    tokens_per_second_window: int = 128
    """Rolling-window size for the HF Trainer
    ``tokens_per_second_rolling_128`` metric per §3.1.2. MUST NOT be
    < 8 (too volatile) or > 4096 (hides regressions) — validated at
    config-construction time."""

    def __post_init__(self) -> None:
        # Range-check the rolling window per §3.1.2 MUST rule 2. Done at
        # construction time (not emit time) so the user sees the error
        # loudly at `async with km.autolog(...)` rather than on first
        # metric emit.
        if not 8 <= self.tokens_per_second_window <= 4096:
            raise ValueError(
                "tokens_per_second_window must be between 8 and 4096 "
                f"(got {self.tokens_per_second_window}); < 8 is too "
                "volatile, > 4096 hides regressions per "
                "ml-autolog.md §3.1.2"
            )


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
       :class:`AutologConfig`. Installs hooks
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
    def attach(self, run: "ExperimentRun", config: AutologConfig) -> None:
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

    async def flush(self, run: "ExperimentRun") -> None:
        """Drain any buffered log events to the tracker.

        Called by the autolog context manager between ``yield`` and
        :meth:`detach` — the event loop is still running, so integrations
        MAY ``await`` their tracker calls here even when the user's
        instrumented code path was sync (e.g. scikit-learn's
        ``estimator.fit(X, y)``).

        Default implementation is a no-op. Integrations whose hook
        surface is natively async (Lightning's ``pl.Callback`` which
        receives the run via an injected tracker reference) leave this
        untouched. Integrations whose hook surface is sync (sklearn
        wrapping ``BaseEstimator.fit``, statsmodels wrapping
        ``Results.summary``) override to drain an in-memory buffer.

        Per ``rules/zero-tolerance.md`` Rule 3 — failures here raise
        loudly; silent-swallow of buffered events is BLOCKED.
        """
        return None

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
