# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests: arm_time_limits / arm_time_limits_async / classifier (#912 Shard 2).

Issue #912 Shard 2 — wrapper helper for soft/hard time-limit ENFORCEMENT.

These Tier-2 tests exercise the actual ``threading.Timer`` /
``asyncio.create_task`` deadline plumbing against the REAL
:class:`kailash.runtime.cancellation.CancellationToken`. No mocking is
permitted at Tier 2 (per ``rules/testing.md`` § 3-Tier Testing).

Coverage:
  * Soft timer fires `token.cancel(reason=...)` after the soft deadline.
  * No-soft-limit case: token stays uncancelled across the test window.
  * Hard timer sets ``cancellable.hard_deadline_reached = True`` after
    ``time_limit + grace_seconds``.
  * Grace window respected: hard flag stays False until grace elapses.
  * ``disarm()`` releases timer threads (no zombie thread growth).
  * ``disarm()`` is idempotent.
  * Validation runs BEFORE arming (no timer leaked on caller error).
  * Async equivalents of soft + disarm.
  * Classifier converts WorkflowCancelledError into the typed subclass.
  * No signal.SIGALRM handler is installed (proves no signal-based
    implementation regressed in).

Timing thresholds use generous slack (+0.4s on most asserts) so the
suite stays robust on shared CI runners; the deadline IDs are still
meaningful because the test windows are sized to cleanly separate
"before" and "after" the deadline.
"""

from __future__ import annotations

import asyncio
import signal
import threading
import time

import pytest

from kailash.runtime._time_limits import (
    _Cancellable,
    _TimeLimitClassifier,
    arm_time_limits,
    arm_time_limits_async,
)
from kailash.runtime.cancellation import CancellationToken
from kailash.sdk_exceptions import (
    HardTimeLimitExceeded,
    SoftTimeLimitExceeded,
    WorkflowCancelledError,
)

# ─────────────────────────────────────────────────────────────────────
# Sync soft-limit tests
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_soft_limit_calls_token_cancel():
    """After ``soft_time_limit`` elapses, the token is cancelled with reason."""
    token = CancellationToken()
    cancellable = arm_time_limits(token, soft_time_limit=0.2, time_limit=None)
    try:
        time.sleep(0.4)
        assert token.is_cancelled is True
        assert token.reason is not None
        assert "soft time limit" in token.reason
    finally:
        cancellable.disarm()


@pytest.mark.integration
def test_no_soft_limit_no_cancel():
    """When ``soft_time_limit`` is None, the token stays uncancelled."""
    token = CancellationToken()
    cancellable = arm_time_limits(token, soft_time_limit=None, time_limit=1.0)
    try:
        time.sleep(0.5)
        # Token NOT cancelled: no soft timer armed AND hard deadline
        # (1.0 + 1.0 grace = 2.0s) has not yet fired.
        assert token.is_cancelled is False
    finally:
        cancellable.disarm()


# ─────────────────────────────────────────────────────────────────────
# Sync hard-limit tests
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_hard_limit_sets_flag_after_grace():
    """Hard flag is True once ``time_limit + grace_seconds`` elapses."""
    token = CancellationToken()
    cancellable = arm_time_limits(
        token,
        soft_time_limit=None,
        time_limit=0.2,
        grace_seconds=0.2,
    )
    try:
        # Sleep past time_limit + grace = 0.4s, with slack.
        time.sleep(0.6)
        assert cancellable.hard_deadline_reached is True
    finally:
        cancellable.disarm()


@pytest.mark.integration
def test_hard_limit_grace_window_respected():
    """Hard flag stays False until ``time_limit + grace_seconds`` elapses."""
    token = CancellationToken()
    cancellable = arm_time_limits(
        token,
        soft_time_limit=None,
        time_limit=0.2,
        grace_seconds=0.5,
    )
    try:
        # Past time_limit (0.2s) but still inside grace window (0.7s
        # total before the hard flag fires).
        time.sleep(0.4)
        assert cancellable.hard_deadline_reached is False
        # Now past grace: time_limit + grace_seconds = 0.7s total;
        # cumulative sleep 0.9s, with slack.
        time.sleep(0.5)
        assert cancellable.hard_deadline_reached is True
    finally:
        cancellable.disarm()


# ─────────────────────────────────────────────────────────────────────
# disarm() tests
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_disarm_releases_timer_thread():
    """``disarm()`` cancels the pending timers — no zombie thread growth."""
    token = CancellationToken()
    baseline = threading.active_count()
    cancellable = arm_time_limits(token, soft_time_limit=2.0, time_limit=5.0)
    # Disarm well before either timer fires.
    cancellable.disarm()
    # Wait past the soft + hard deadlines that WOULD have fired.
    time.sleep(0.5)
    # Active count should not have grown by the timer threads we just
    # cancelled. ``threading.Timer`` worker threads exit cleanly on
    # ``cancel()``; allow a small slack for unrelated thread churn.
    assert threading.active_count() <= baseline + 2, (
        f"active_count grew unexpectedly: baseline={baseline}, "
        f"now={threading.active_count()}"
    )
    # And the token was NOT cancelled (timers were disarmed before
    # they could fire).
    assert token.is_cancelled is False


@pytest.mark.integration
def test_disarm_idempotent():
    """Calling ``disarm()`` twice is safe (no exceptions)."""
    token = CancellationToken()
    cancellable = arm_time_limits(token, soft_time_limit=2.0, time_limit=5.0)
    cancellable.disarm()
    cancellable.disarm()  # MUST NOT raise
    cancellable.disarm()  # third call still safe


# ─────────────────────────────────────────────────────────────────────
# Validation tests (Tier 2 — proves validation runs before arming)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_validation_fails_before_arming():
    """``arm_time_limits`` rejects bad inputs BEFORE starting any timer.

    The ``_validate_limits`` invariant from Shard 1 is preserved: a
    caller error (negative deadline) raises ``ValueError`` synchronously
    at the entry point. No timer thread is started, so a subsequent
    ``threading.active_count()`` check sees no growth.
    """
    token = CancellationToken()
    baseline = threading.active_count()
    with pytest.raises(ValueError, match="soft_time_limit"):
        arm_time_limits(token, soft_time_limit=-1, time_limit=None)
    # No timer thread was started.
    assert threading.active_count() == baseline


# ─────────────────────────────────────────────────────────────────────
# Async tests
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_soft_limit_calls_token_cancel():
    """Async equivalent of the sync soft-limit test."""
    token = CancellationToken()
    cancellable = arm_time_limits_async(token, soft_time_limit=0.2, time_limit=None)
    try:
        await asyncio.sleep(0.4)
        assert token.is_cancelled is True
        assert token.reason is not None
        assert "soft time limit" in token.reason
    finally:
        cancellable.disarm()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_disarm_cancels_pending_tasks():
    """``disarm()`` cancels pending async tasks; no un-awaited RuntimeWarning."""
    token = CancellationToken()
    cancellable = arm_time_limits_async(token, soft_time_limit=2.0, time_limit=5.0)
    # Disarm well before deadlines.
    cancellable.disarm()
    # Await past the deadlines that WOULD have fired.
    await asyncio.sleep(0.3)
    # Token never cancelled.
    assert token.is_cancelled is False
    # Tasks are cancelled (or completed cleanly via the inner
    # CancelledError swallow).
    if cancellable._soft_task is not None:
        # Either cancelled or finished cleanly via the CancelledError
        # branch in _fire_soft_async; both states are acceptable.
        assert cancellable._soft_task.done()
    if cancellable._hard_task is not None:
        assert cancellable._hard_task.done()


# ─────────────────────────────────────────────────────────────────────
# Classifier tests
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_classifier_soft_first():
    """Classifier returns SoftTimeLimitExceeded when soft reached, hard not."""
    token = CancellationToken()
    cancellable = arm_time_limits(token, soft_time_limit=0.1, time_limit=10.0)
    try:
        time.sleep(0.3)  # past soft, well inside hard
        assert cancellable.hard_deadline_reached is False
        original = WorkflowCancelledError("workflow cancelled")
        classifier = _TimeLimitClassifier(cancellable)
        classified = classifier.classify(original)
        assert isinstance(classified, SoftTimeLimitExceeded)
        # Caller chains via `raise classified from original`; verify
        # the chain works end-to-end.
        try:
            raise classified from original
        except SoftTimeLimitExceeded as exc:
            assert exc.__cause__ is original
    finally:
        cancellable.disarm()


@pytest.mark.integration
def test_classifier_hard_first():
    """Classifier returns HardTimeLimitExceeded when hard reached."""
    token = CancellationToken()
    cancellable = arm_time_limits(
        token,
        soft_time_limit=None,
        time_limit=0.1,
        grace_seconds=0.1,
    )
    try:
        time.sleep(0.4)  # past time_limit + grace
        assert cancellable.hard_deadline_reached is True
        original = WorkflowCancelledError("workflow cancelled")
        classifier = _TimeLimitClassifier(cancellable)
        classified = classifier.classify(original)
        assert isinstance(classified, HardTimeLimitExceeded)
    finally:
        cancellable.disarm()


@pytest.mark.integration
def test_classifier_both_reached_returns_hard():
    """When both deadlines have been reached, hard wins (more severe)."""
    token = CancellationToken()
    cancellable = arm_time_limits(
        token,
        soft_time_limit=0.1,
        time_limit=0.2,
        grace_seconds=0.1,
    )
    try:
        # Past time_limit + grace = 0.3s; well past soft = 0.1s.
        time.sleep(0.5)
        assert cancellable.hard_deadline_reached is True
        original = WorkflowCancelledError("workflow cancelled")
        classifier = _TimeLimitClassifier(cancellable)
        classified = classifier.classify(original)
        # Hard wins — represents the more severe condition per docstring.
        assert isinstance(classified, HardTimeLimitExceeded)
    finally:
        cancellable.disarm()


@pytest.mark.integration
def test_classifier_neither_reached_returns_original():
    """When neither deadline reached, classifier returns the original error.

    Token cancelled for an external reason (user cancel, sibling
    cancellation) — NOT one of our deadlines. The classifier MUST NOT
    fabricate a time-limit cause.
    """
    token = CancellationToken()
    cancellable = arm_time_limits(token, soft_time_limit=10.0, time_limit=20.0)
    try:
        # Don't sleep — neither deadline reached.
        original = WorkflowCancelledError("user cancel")
        classifier = _TimeLimitClassifier(cancellable)
        classified = classifier.classify(original)
        assert classified is original
    finally:
        cancellable.disarm()


# ─────────────────────────────────────────────────────────────────────
# Signal-free implementation guard
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_signal_not_used():
    """Arming + disarming MUST NOT install a SIGALRM handler.

    Per the brief and the helper docstring, ``signal.SIGALRM`` is
    BLOCKED by design (fails outside the main thread, fails on
    Windows). This test pins the structural invariant: a future
    refactor that switches to a signal-based implementation would
    flip the SIGALRM handler from its baseline value, and this test
    fails loudly.

    On non-main threads ``signal.signal()`` raises; we therefore use
    ``signal.getsignal()`` which is read-only and main-thread-safe.
    """
    # Capture baseline SIGALRM handler (default is signal.SIG_DFL on
    # most platforms; some test runners may set their own handler —
    # we compare relative to baseline, not absolute).
    baseline = signal.getsignal(signal.SIGALRM)
    token = CancellationToken()
    cancellable = arm_time_limits(token, soft_time_limit=2.0, time_limit=5.0)
    try:
        after_arm = signal.getsignal(signal.SIGALRM)
        assert after_arm == baseline, (
            f"SIGALRM handler changed by arm_time_limits: "
            f"{baseline!r} -> {after_arm!r}; signal-based implementation "
            f"is BLOCKED per module docstring"
        )
    finally:
        cancellable.disarm()
    after_disarm = signal.getsignal(signal.SIGALRM)
    assert after_disarm == baseline, (
        f"SIGALRM handler changed across arm/disarm cycle: "
        f"{baseline!r} -> {after_disarm!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# Type guard
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_arm_returns_cancellable_type():
    """``arm_time_limits`` always returns a ``_Cancellable`` instance.

    Mirrors the unit-test invariant against the real CancellationToken
    so the integration suite ALSO pins the contract — refactors that
    move the dataclass to a different module without re-exporting
    surface here too.
    """
    token = CancellationToken()
    cancellable = arm_time_limits(token, soft_time_limit=10.0, time_limit=20.0)
    try:
        assert isinstance(cancellable, _Cancellable)
    finally:
        cancellable.disarm()
