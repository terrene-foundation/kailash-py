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

# AutologConfig and FrameworkIntegration moved to ``_types.py`` to break
# the static cycle with ``_registry.py``. Re-exported here so callers
# importing from ``kailash_ml.autolog.config`` continue to resolve.
from kailash_ml.autolog._types import AutologConfig, FrameworkIntegration

__all__ = ["AutologConfig", "AutologHandle"]


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
