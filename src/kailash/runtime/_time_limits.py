# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Time-limit validation + enforcement helpers for runtime ``execute*`` methods (#912).

Issue #912 — per-task soft/hard time limits. This module owns the SINGLE
validation surface every runtime entry point calls when accepting the
typed ``soft_time_limit`` / ``time_limit`` kwargs (Shard 1) AND the
deadline-arming wrapper that consumes the validated values and raises
:class:`~kailash.sdk_exceptions.SoftTimeLimitExceeded` /
:class:`~kailash.sdk_exceptions.HardTimeLimitExceeded` at the right
moments (Shard 2).

Centralising validation prevents drift across the 10 ``execute*`` methods
on the runtime hierarchy (per ``security.md`` § Multi-Site Kwarg
Plumbing — every caller of a security-relevant kwarg helper MUST share
the same validation).

Hard-limit enforcement model
----------------------------

The brief's invariant 5 (issue #912) requires that after
``time_limit + grace_seconds``, the wrapper raises
:class:`~kailash.sdk_exceptions.HardTimeLimitExceeded` UNCONDITIONALLY —
the grace window is the runtime's chance to wind down cleanly after the
soft signal but the hard kill is non-negotiable.

The clean implementation cannot raise an exception from a background
thread INTO the executing thread (Python's threading model does not
support cross-thread exception injection on a worker that is NOT
polling). Instead, the background timer sets a flag
(``hard_deadline_reached: bool = False`` -> ``True``) on the
:class:`_Cancellable` returned by :func:`arm_time_limits`. The CALLER
(the runtime wrapper) MUST check this flag in a try/finally around the
workflow execution AND raise :class:`HardTimeLimitExceeded` if set.

Sketch of the caller's contract::

    cancellable = arm_time_limits(token, soft_time_limit=2.0, time_limit=10.0)
    try:
        results, run_id = _execute_workflow_inner(...)
    except WorkflowCancelledError as exc:
        # Token was cancelled. Was it our soft/hard deadline?
        classifier = _TimeLimitClassifier(cancellable)
        raise classifier.classify(exc) from exc
    finally:
        cancellable.disarm()
        if cancellable.hard_deadline_reached:
            raise HardTimeLimitExceeded(
                f"workflow exceeded hard time limit "
                f"(time_limit={cancellable.time_limit}s + "
                f"grace_seconds={cancellable.grace_seconds}s)"
            )

The flag-based model avoids the impossible "raise from a background
thread into the executing thread" problem AND the equally-bad
:mod:`signal`-based model (``signal.SIGALRM`` fails outside the main
thread and fails on Windows entirely).

Sync vs async
-------------

:func:`arm_time_limits` (sync) uses :class:`threading.Timer` for both
deadlines — cross-platform, works inside any thread.

:func:`arm_time_limits_async` (async) uses :func:`asyncio.create_task`
+ :func:`asyncio.sleep` against the running event loop — same
semantics, different primitives.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from kailash.sdk_exceptions import (
    HardTimeLimitExceeded,
    SoftTimeLimitExceeded,
    WorkflowCancelledError,
)

if TYPE_CHECKING:
    from kailash.runtime.cancellation import CancellationToken

logger = logging.getLogger(__name__)


def _validate_limits(
    soft_time_limit: float | None,
    time_limit: float | None,
    grace_seconds: float | None = None,
) -> None:
    """Validate the typed time-limit kwargs accepted by every runtime ``execute*``.

    Called from every runtime entry point that accepts ``soft_time_limit``
    / ``time_limit`` kwargs. Raises :class:`ValueError` with an
    actionable message on caller error so the failure surfaces at the
    entry point — NOT later from a timer thread where the traceback
    points at internals.

    Per the celery-style convention (see issue #912 brief): when both
    kwargs are set, ``soft_time_limit`` MUST be strictly less than
    ``time_limit`` so the soft signal precedes the hard kill with a
    non-zero warning window.

    Args:
        soft_time_limit: Advisory deadline in seconds. ``None`` = no
            soft limit. ``<= 0`` and non-finite (``NaN`` / ``±inf``) are
            invalid — :class:`threading.Timer` would either sleep forever
            (``inf``) or crash from a daemon thread (``NaN``).
        time_limit: Unconditional kill deadline in seconds. ``None`` =
            no hard limit. ``<= 0`` and non-finite are invalid.
        grace_seconds: Optional wind-down window between the hard
            deadline and the unconditional raise. ``None`` (the default)
            skips the grace check — callers that don't pass a grace
            value want the helper's default applied at arm-time. When
            set, MUST be ``>= 0`` AND finite. ``grace_seconds < 0``
            would make the hard timer fire BEFORE ``time_limit``,
            inverting the celery-style soft-then-hard contract.

    Raises:
        ValueError: If either time-limit kwarg is ``<= 0`` or non-finite,
            or if both are set and ``soft_time_limit >= time_limit``,
            or if ``grace_seconds`` is negative or non-finite.

    Added in: v0.13.0 (issue #912 Shard 1). Extended by issue #912
    Shard 6 to reject NaN / Inf and to validate ``grace_seconds`` so
    every entry-point call surfaces caller error before any timer
    thread is started.
    """
    if soft_time_limit is not None:
        if not math.isfinite(soft_time_limit):
            raise ValueError(
                f"soft_time_limit MUST be finite when set (got {soft_time_limit!r}); "
                f"NaN sleeps forever from a daemon thread, ±inf is "
                f"unbounded — pass None to disable the soft deadline"
            )
        if soft_time_limit <= 0:
            raise ValueError(
                f"soft_time_limit MUST be > 0 when set (got {soft_time_limit!r}); "
                f"pass None to disable the soft deadline"
            )
    if time_limit is not None:
        if not math.isfinite(time_limit):
            raise ValueError(
                f"time_limit MUST be finite when set (got {time_limit!r}); "
                f"NaN sleeps forever from a daemon thread, ±inf is "
                f"unbounded — pass None to disable the hard deadline"
            )
        if time_limit <= 0:
            raise ValueError(
                f"time_limit MUST be > 0 when set (got {time_limit!r}); "
                f"pass None to disable the hard deadline"
            )
    if (
        soft_time_limit is not None
        and time_limit is not None
        and soft_time_limit >= time_limit
    ):
        raise ValueError(
            f"soft_time_limit ({soft_time_limit!r}) MUST be strictly less than "
            f"time_limit ({time_limit!r}) so the advisory signal precedes the "
            f"hard kill with a non-zero warning window"
        )
    if grace_seconds is not None:
        if not math.isfinite(grace_seconds):
            raise ValueError(
                f"grace_seconds MUST be finite when set (got {grace_seconds!r}); "
                f"NaN crashes the daemon thread, ±inf is unbounded"
            )
        if grace_seconds < 0:
            raise ValueError(
                f"grace_seconds MUST be >= 0 when set (got {grace_seconds!r}); "
                f"a negative grace would fire the hard kill BEFORE the soft "
                f"signal, inverting the celery-style soft-then-hard contract"
            )


@dataclass
class _Cancellable:
    """Handle returned by :func:`arm_time_limits` / :func:`arm_time_limits_async`.

    Holds the active timer handles + deadline metadata + the
    cancellation token + the hard-deadline flag the caller polls in
    its ``finally`` block.

    The caller MUST:

    1. Wrap workflow execution in ``try / except WorkflowCancelledError
       / finally``.
    2. In ``except``, run the classifier (``_TimeLimitClassifier``) to
       convert the cancellation into the typed
       :class:`SoftTimeLimitExceeded` / :class:`HardTimeLimitExceeded`.
    3. In ``finally``, call :meth:`disarm` to release the timer threads
       AND check :attr:`hard_deadline_reached` — if True, raise
       :class:`HardTimeLimitExceeded` even if the workflow returned
       successfully (the deadline fired but the runtime had not yet
       observed the token).

    Attributes:
        token: The cancellation token armed by the soft timer.
        soft_time_limit: Stored for classifier diagnostics. ``None`` if
            no soft timer was armed.
        time_limit: Stored for classifier diagnostics. ``None`` if no
            hard timer was armed.
        grace_seconds: Wind-down window between ``time_limit`` and the
            unconditional hard raise.
        hard_deadline_reached: Set to True by the hard-deadline timer
            when ``time_limit + grace_seconds`` elapses. The caller
            polls this in ``finally``.
        armed_at: ``time.monotonic()`` snapshot at arming time. Used by
            the classifier to compare against deadlines.
        soft_deadline_at: ``armed_at + soft_time_limit`` (monotonic
            absolute time). ``None`` if no soft limit.
        hard_deadline_at: ``armed_at + time_limit + grace_seconds``
            (monotonic absolute time). ``None`` if no hard limit.
    """

    token: CancellationToken
    soft_time_limit: float | None = None
    time_limit: float | None = None
    grace_seconds: float = 1.0
    hard_deadline_reached: bool = False
    armed_at: float = 0.0
    soft_deadline_at: float | None = None
    hard_deadline_at: float | None = None
    _soft_timer: threading.Timer | None = field(default=None, repr=False)
    _hard_timer: threading.Timer | None = field(default=None, repr=False)
    _soft_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _hard_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _disarmed: bool = field(default=False, repr=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def disarm(self) -> None:
        """Cancel both pending timers / tasks idempotently.

        Safe to call multiple times. Safe to call when no timers were
        armed (the no-limits case). Holds an internal lock so concurrent
        disarm attempts (caller's ``finally`` and a sibling cleanup
        path) do not race.
        """
        with self._lock:
            if self._disarmed:
                return
            self._disarmed = True

        if self._soft_timer is not None:
            try:
                self._soft_timer.cancel()
            except Exception:  # noqa: BLE001 — defensive cleanup
                logger.debug("soft timer cancel raised", exc_info=True)
        if self._hard_timer is not None:
            try:
                self._hard_timer.cancel()
            except Exception:  # noqa: BLE001 — defensive cleanup
                logger.debug("hard timer cancel raised", exc_info=True)
        if self._soft_task is not None and not self._soft_task.done():
            self._soft_task.cancel()
        if self._hard_task is not None and not self._hard_task.done():
            self._hard_task.cancel()


def arm_time_limits(
    token: CancellationToken,
    *,
    soft_time_limit: float | None,
    time_limit: float | None,
    grace_seconds: float = 1.0,
) -> _Cancellable:
    """Arm soft + hard deadlines via :class:`threading.Timer`.

    Validates inputs via :func:`_validate_limits` (raises
    :class:`ValueError` BEFORE any timer is started, so caller error
    surfaces at the entry point, not later from a timer thread).

    Behaviour:

    * If ``soft_time_limit`` is set, a background timer fires after
      ``soft_time_limit`` seconds and calls
      ``token.cancel(reason="soft time limit exceeded after Xs")``.
      The runtime observes the cancelled token at its next poll and
      raises :class:`~kailash.sdk_exceptions.WorkflowCancelledError`,
      which the caller's ``except`` branch converts to
      :class:`~kailash.sdk_exceptions.SoftTimeLimitExceeded` via
      :class:`_TimeLimitClassifier`.

    * If ``time_limit`` is set, a SECOND timer fires after
      ``time_limit + grace_seconds`` seconds and sets
      ``cancellable.hard_deadline_reached = True``. The caller's
      ``finally`` block polls this flag and raises
      :class:`HardTimeLimitExceeded` UNCONDITIONALLY (per brief
      invariant 5 — the grace window is the runtime's chance to wind
      down cleanly after the soft signal; if it didn't, the hard kill
      is non-negotiable).

    Both timers are released by :meth:`_Cancellable.disarm`. The caller
    MUST call ``disarm()`` in a ``finally`` block, even on the
    no-limits path, to keep the cleanup pattern uniform.

    The implementation is signal-free: :data:`signal.SIGALRM` is
    BLOCKED by design — it fails outside the main thread (every
    runtime worker thread cannot use it) and fails on Windows
    entirely.

    Args:
        token: The cancellation token the soft timer arms.
        soft_time_limit: Advisory deadline in seconds. ``None`` skips
            arming the soft timer.
        time_limit: Unconditional kill deadline in seconds. ``None``
            skips arming the hard timer.
        grace_seconds: Wind-down window after ``time_limit`` before the
            hard flag fires. Default 1.0s. MUST be ``>= 0``.

    Returns:
        A :class:`_Cancellable` handle. Always returned (even when both
        limits are ``None``) so callers can use a uniform try/finally
        pattern without a conditional ``if cancellable is not None``
        guard.

    Raises:
        ValueError: If ``_validate_limits`` rejects the inputs (see
            its docstring for the contract). NO timer was started
            when this raises.

    Added in: v0.13.0 (issue #912 Shard 2). Extended by Shard 6 to
    forward ``grace_seconds`` through the validator so caller error
    (negative / NaN / Inf grace) surfaces at this entry point instead
    of from a daemon thread later.
    """
    _validate_limits(soft_time_limit, time_limit, grace_seconds=grace_seconds)

    armed_at = time.monotonic()
    cancellable = _Cancellable(
        token=token,
        soft_time_limit=soft_time_limit,
        time_limit=time_limit,
        grace_seconds=grace_seconds,
        armed_at=armed_at,
        soft_deadline_at=(
            armed_at + soft_time_limit if soft_time_limit is not None else None
        ),
        hard_deadline_at=(
            armed_at + time_limit + grace_seconds if time_limit is not None else None
        ),
    )

    if soft_time_limit is not None:

        def _fire_soft() -> None:
            # The cancellation token is the integration point: the
            # runtime's poll loop observes it and raises
            # WorkflowCancelledError on the executing thread.
            token.cancel(reason=f"soft time limit exceeded after {soft_time_limit}s")

        timer = threading.Timer(soft_time_limit, _fire_soft)
        timer.daemon = True
        timer.start()
        cancellable._soft_timer = timer

    if time_limit is not None:
        hard_after = time_limit + grace_seconds

        def _fire_hard() -> None:
            # Set the flag the caller polls in its `finally` block.
            # Raising from this thread cannot inject the exception into
            # the executing thread — the flag-based model is the only
            # workable Python pattern (see module docstring).
            cancellable.hard_deadline_reached = True
            # Best-effort cancel the token too so the runtime can wind
            # down on its next poll if the soft timer didn't fire.
            try:
                token.cancel(
                    reason=(
                        f"hard time limit exceeded after {time_limit}s "
                        f"(grace={grace_seconds}s)"
                    )
                )
            except Exception:  # noqa: BLE001 — defensive
                logger.debug("hard timer token.cancel raised", exc_info=True)

        timer = threading.Timer(hard_after, _fire_hard)
        timer.daemon = True
        timer.start()
        cancellable._hard_timer = timer

    return cancellable


def arm_time_limits_async(
    token: CancellationToken,
    *,
    soft_time_limit: float | None,
    time_limit: float | None,
    grace_seconds: float = 1.0,
) -> _Cancellable:
    """Async analogue of :func:`arm_time_limits` using :mod:`asyncio` tasks.

    Identical semantics to :func:`arm_time_limits`. Uses
    :func:`asyncio.create_task` + :func:`asyncio.sleep` against the
    running event loop instead of :class:`threading.Timer`.

    MUST be called from inside a running event loop (raises
    :class:`RuntimeError` otherwise — surface the integration error at
    the call site).

    Args:
        token: The cancellation token the soft task arms.
        soft_time_limit: Advisory deadline in seconds. ``None`` skips
            arming the soft task.
        time_limit: Unconditional kill deadline in seconds. ``None``
            skips arming the hard task.
        grace_seconds: Wind-down window after ``time_limit`` before the
            hard flag fires. Default 1.0s.

    Returns:
        A :class:`_Cancellable` handle. Always returned.

    Raises:
        ValueError: If ``_validate_limits`` rejects the inputs.
        RuntimeError: If called outside a running event loop.

    Added in: v0.13.0 (issue #912 Shard 2). Extended by Shard 6 to
    forward ``grace_seconds`` through the validator so caller error
    (negative / NaN / Inf grace) surfaces at this entry point instead
    of from an asyncio task later.
    """
    _validate_limits(soft_time_limit, time_limit, grace_seconds=grace_seconds)

    loop = asyncio.get_running_loop()  # raises RuntimeError outside a loop

    armed_at = time.monotonic()
    cancellable = _Cancellable(
        token=token,
        soft_time_limit=soft_time_limit,
        time_limit=time_limit,
        grace_seconds=grace_seconds,
        armed_at=armed_at,
        soft_deadline_at=(
            armed_at + soft_time_limit if soft_time_limit is not None else None
        ),
        hard_deadline_at=(
            armed_at + time_limit + grace_seconds if time_limit is not None else None
        ),
    )

    if soft_time_limit is not None:

        async def _fire_soft_async() -> None:
            try:
                await asyncio.sleep(soft_time_limit)
            except asyncio.CancelledError:
                return
            token.cancel(reason=f"soft time limit exceeded after {soft_time_limit}s")

        cancellable._soft_task = loop.create_task(_fire_soft_async())

    if time_limit is not None:
        hard_after = time_limit + grace_seconds

        async def _fire_hard_async() -> None:
            try:
                await asyncio.sleep(hard_after)
            except asyncio.CancelledError:
                return
            cancellable.hard_deadline_reached = True
            try:
                token.cancel(
                    reason=(
                        f"hard time limit exceeded after {time_limit}s "
                        f"(grace={grace_seconds}s)"
                    )
                )
            except Exception:  # noqa: BLE001 — defensive
                logger.debug("async hard task token.cancel raised", exc_info=True)

        cancellable._hard_task = loop.create_task(_fire_hard_async())

    return cancellable


class _TimeLimitClassifier:
    """Convert :class:`WorkflowCancelledError` into the typed time-limit subclass.

    The runtime observes the cancellation token (set by either timer)
    and raises :class:`~kailash.sdk_exceptions.WorkflowCancelledError`.
    The caller's ``except`` branch passes that error to this classifier,
    which inspects the deadlines stored on the ``_Cancellable`` and
    returns the correct typed subclass — :class:`SoftTimeLimitExceeded`
    OR :class:`HardTimeLimitExceeded`.

    Decision rule:

    * If the hard deadline has been reached (per ``time.monotonic()``
      vs ``hard_deadline_at``), return :class:`HardTimeLimitExceeded`.
      Hard wins when both are reached — it represents the more severe
      condition.
    * Else if the soft deadline has been reached, return
      :class:`SoftTimeLimitExceeded`.
    * Else (token cancelled for a non-time-limit reason — e.g.
      external user cancel), return the original
      :class:`WorkflowCancelledError` unchanged.

    Returned exceptions are raised by the caller using
    ``raise classified from original`` — preserving the cause chain
    so operators see both the typed deadline event AND the underlying
    cancellation in the traceback.

    Args:
        cancellable: The handle returned by :func:`arm_time_limits` /
            :func:`arm_time_limits_async`. The classifier reads
            ``soft_deadline_at``, ``hard_deadline_at``, and
            ``hard_deadline_reached`` from it.
    """

    def __init__(self, cancellable: _Cancellable) -> None:
        self._cancellable = cancellable

    def classify(
        self,
        original: WorkflowCancelledError,
    ) -> SoftTimeLimitExceeded | HardTimeLimitExceeded | WorkflowCancelledError:
        """Return the typed subclass matching whichever deadline was reached.

        Args:
            original: The :class:`WorkflowCancelledError` the runtime
                raised when it observed the cancelled token.

        Returns:
            One of:

            * :class:`HardTimeLimitExceeded` — hard deadline reached
              (whether or not soft was also reached).
            * :class:`SoftTimeLimitExceeded` — soft deadline reached,
              hard NOT reached.
            * The original :class:`WorkflowCancelledError` unchanged
              when neither deadline was reached (token was cancelled
              for an external reason).
        """
        c = self._cancellable
        now = time.monotonic()

        hard_reached = c.hard_deadline_reached or (
            c.hard_deadline_at is not None and now >= c.hard_deadline_at
        )
        soft_reached = c.soft_deadline_at is not None and now >= c.soft_deadline_at

        if hard_reached:
            return HardTimeLimitExceeded(
                f"workflow exceeded hard time limit "
                f"(time_limit={c.time_limit}s + grace_seconds={c.grace_seconds}s)"
            )
        if soft_reached:
            return SoftTimeLimitExceeded(
                f"workflow exceeded soft time limit "
                f"(soft_time_limit={c.soft_time_limit}s)"
            )
        return original
