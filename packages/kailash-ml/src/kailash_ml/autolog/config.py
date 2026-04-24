# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Autolog configuration and runtime handle dataclasses.

Implements ``specs/ml-autolog.md §4.0``:

- :class:`AutologConfig` — frozen immutable configuration snapshot
  constructed inside :func:`kailash_ml.autolog.autolog` from the
  user's positional + keyword arguments. Passed to every
  :meth:`FrameworkIntegration.attach` call so integrations read a
  consistent non-mutating view (§3.2).
- :class:`AutologHandle` — runtime handle yielded by
  ``async with autolog() as handle`` giving the test surface
  access to ``run_id``, frozen ``config``, and the
  post-filter ``attached_integrations`` tuple (§4.0 + §8.2).

No framework-specific imports live in this module — the scaffolding
MUST stay importable on every platform / extras combination (§10.1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kailash_ml.autolog._registry import FrameworkIntegration


__all__ = ["AutologConfig", "AutologHandle"]


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


@dataclass(frozen=True)
class AutologHandle:
    """Runtime handle yielded by ``async with autolog() as handle:``.

    Exposes introspection on the live block. Test code MAY assert
    ``handle.attached_integrations`` matches the expected set of
    frameworks for Tier-2 wiring tests per §8.2.

    Frozen — the fields represent the state captured at ``__aenter__``
    time. To observe live detach via :meth:`stop`, callers inspect
    :attr:`frameworks_active` which delegates to the shared mutable
    list owned by the context manager.
    """

    run_id: str
    """The ambient :class:`~kailash_ml.tracking.ExperimentRun.run_id`
    captured at ``__aenter__`` time per §4.0."""

    config: AutologConfig
    """The frozen config this block is running under (§4.0 MUST)."""

    attached_integrations: tuple[str, ...]
    """Names of integrations that successfully attached post
    auto-detect + disable filtering. Ordered by registration order
    per §4.1."""

    _active: list[FrameworkIntegration] = field(default_factory=list, repr=False)
    """Private mutable reference to the CM's live-integrations list.
    The context manager pops entries on :meth:`stop`; test code reads
    :attr:`frameworks_active` to observe the live set."""

    @property
    def frameworks_active(self) -> list[str]:
        """Names of frameworks whose callbacks are currently installed.

        Equivalent to :attr:`attached_integrations` after successful
        attach; drops names whose :meth:`detach` was called via
        :meth:`stop`.
        """
        return [integ.name for integ in self._active]

    def stop(self) -> None:
        """Early-detach every currently-attached integration without
        exiting the context manager.

        Idempotent per §4.0 MUST. After :meth:`stop`, the block's
        ``__aexit__`` still runs but its detach pass is a no-op on
        already-detached integrations.
        """
        from kailash.ml.errors import AutologDetachError

        # Detach in reverse of attach order so integrations that share
        # state (e.g. transformers layered on top of lightning) unwind
        # LIFO. Per §3.2 MUST, every detach runs inside `finally:` so a
        # failure in one does NOT prevent the remaining from running.
        errors: list[BaseException] = []
        while self._active:
            integ = self._active.pop()
            try:
                integ.detach()
            except Exception as exc:  # noqa: BLE001 — per-integration isolation
                errors.append(exc)
        if errors:
            # Surface the first failure as primary; chain siblings via
            # __context__ so the full stack is reachable for debug.
            first = errors[0]
            wrapped = AutologDetachError(
                reason=(
                    f"stop() hit {len(errors)} detach failure(s); "
                    f"first: {type(first).__name__}: {first}"
                )
            )
            wrapped.__cause__ = first
            raise wrapped
