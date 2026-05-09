# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Time-limit validation helper for runtime ``execute*`` methods (#912 Shard 1).

Issue #912 — per-task soft/hard time limits. This module owns the SINGLE
validation surface every runtime entry point calls when accepting the
typed ``soft_time_limit`` / ``time_limit`` kwargs. Centralising the check
prevents drift across the 10 ``execute*`` methods on the runtime
hierarchy (per ``security.md`` § Multi-Site Kwarg Plumbing — every
caller of a security-relevant kwarg helper MUST share the same
validation).

Shard 1 lands the kwarg slot + validation. Shard 2 will add the
deadline-arming wrapper (`arm_time_limits` / `arm_time_limits_async`)
that consumes the validated values and raises
:class:`~kailash.sdk_exceptions.SoftTimeLimitExceeded` /
:class:`~kailash.sdk_exceptions.HardTimeLimitExceeded` at the right
moments.
"""

from __future__ import annotations


def _validate_limits(
    soft_time_limit: float | None,
    time_limit: float | None,
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
            soft limit. ``<= 0`` is invalid.
        time_limit: Unconditional kill deadline in seconds. ``None`` =
            no hard limit. ``<= 0`` is invalid.

    Raises:
        ValueError: If either kwarg is ``<= 0``, or if both are set and
            ``soft_time_limit >= time_limit``.

    Added in: v0.13.0 (issue #912 Shard 1).
    """
    if soft_time_limit is not None and soft_time_limit <= 0:
        raise ValueError(
            f"soft_time_limit MUST be > 0 when set (got {soft_time_limit!r}); "
            f"pass None to disable the soft deadline"
        )
    if time_limit is not None and time_limit <= 0:
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
