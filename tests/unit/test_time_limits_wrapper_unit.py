# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests: _Cancellable + arm_time_limits skeleton (#912 Shard 2).

Issue #912 Shard 2 — wrapper helper for soft/hard time-limit ENFORCEMENT.

These unit tests pin the SHAPE of the helper APIs without exercising the
real timer mechanics. The Tier 2 integration tests in
``tests/integration/test_time_limits_wrapper.py`` exercise the actual
``threading.Timer`` / ``asyncio.create_task`` deadline plumbing and
classifier behaviour against the real ``CancellationToken``.

Invariants asserted here:
  1. ``_Cancellable`` exposes a ``hard_deadline_reached: bool`` flag
     defaulting to False — the caller polls this in a try/finally to
     decide whether to raise :class:`HardTimeLimitExceeded`.
  2. ``arm_time_limits(token, *, soft_time_limit, time_limit)`` returns
     a ``_Cancellable`` instance — the public return-type contract.
  3. ``arm_time_limits(token, soft_time_limit=None, time_limit=None)``
     returns a no-op ``_Cancellable`` whose ``disarm()`` is safe to call
     (no timers were armed, no exceptions raised).
"""

from __future__ import annotations

import pytest

from kailash.runtime._time_limits import arm_time_limits
from kailash.runtime.cancellation import CancellationToken


@pytest.mark.unit
def test_cancellable_initial_state():
    """A fresh ``_Cancellable`` has ``hard_deadline_reached`` set to False.

    The flag is the structural-completion signal the caller checks in
    ``finally`` to decide whether the hard deadline fired before the
    workflow completed. Default-False ensures the caller does NOT raise
    spuriously when no hard timer was armed or when the workflow
    completed inside the budget.
    """
    token = CancellationToken()
    cancellable = arm_time_limits(token, soft_time_limit=None, time_limit=None)
    try:
        assert cancellable.hard_deadline_reached is False
    finally:
        cancellable.disarm()


# test_arm_returns_cancellable removed — armed-path return type is pinned
# by tests/integration/test_time_limits_wrapper.py::test_arm_returns_cancellable_type
# (Tier 2). The Tier 1 invocation hung intermittently on CI runners because
# threading.Timer.start() blocks on self._started.wait() under thread-creation
# contention after ~3700 prior tests. The no-limits path is still pinned by
# test_arm_with_no_limits_returns_noop_cancellable below (no thread spawned).


@pytest.mark.unit
def test_arm_with_no_limits_returns_noop_cancellable():
    """No-limits case still returns a ``_Cancellable`` with safe ``disarm()``.

    When both kwargs are ``None``, the helper does NOT arm any timers,
    but still returns a ``_Cancellable`` so callers can use a uniform
    try/finally pattern without conditional ``if cancellable is not
    None`` guards. ``disarm()`` MUST be a safe no-op in this case.
    """
    token = CancellationToken()
    cancellable = arm_time_limits(token, soft_time_limit=None, time_limit=None)
    # Safe to disarm even though nothing was armed.
    cancellable.disarm()
    # Safe to disarm twice (idempotent).
    cancellable.disarm()
    # Hard deadline was never reached (no timer armed).
    assert cancellable.hard_deadline_reached is False
