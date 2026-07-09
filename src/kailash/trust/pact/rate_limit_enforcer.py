# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Stateful sliding-window rate-limit enforcer for the PACT verdict path.

The governance envelope carries *declared* rate limits
(``operational.max_actions_per_day`` / ``max_actions_per_hour``), but until
this module the engine only ever compared them against a **caller-supplied**
count (``ctx["daily_calls"]`` / ``ctx["hourly_calls"]``) -- a limit that
*nothing tallied* (GitHub #1516 leg a). A caller that never supplied a count
was never rate-limited at all.

:class:`RateLimitEnforcer` closes that gap: it keeps a stateful sliding-window
counter that TALLIES real ``verify_action`` calls per ``(role, action,
window)`` key and reports a breach the moment the live count reaches the
declared limit. It adapts the proven deque sliding-window model from
``McpGovernanceEnforcer._check_rate_limit``
(``packages/kailash-pact/src/pact/mcp/enforcer.py``) into the core trust-plane
governance engine -- the same ``deque(maxlen=...)`` tracker, per-key window
pruning, amortized window-expiry GC, and LRU hard-cap eviction.

Security invariants (each pinned by a test):

1. **Stateful tally, not a caller count.** The counter records every call it
   admits; the ``(N+1)``-th call inside a window whose limit is ``N`` breaches.
2. **Fail-closed.** A counter/backend error surfaces as an exception the caller
   converts to ``BLOCKED`` -- never a permissive result (``pact-governance.md``
   Rule 4).
3. **Thread-safe, atomic tally.** The whole check-then-record is one critical
   section under ``self._lock`` (``pact-governance.md`` Rule 8) -- no
   check/record TOCTOU. Multi-window admission is all-or-nothing.
4. **Bounded memory.** Each key is a ``deque(maxlen=limit+1)``; an amortized
   window-expiry GC reclaims silent keys and an LRU hard-cap bounds the map
   under adversarial key churn (``trust-plane-security.md`` Rule 4).
5. **Finite guards.** Window seconds and limits are validated with
   ``math.isfinite`` (``pact-governance.md`` Rule 6) so a ``NaN``/``Inf`` limit
   cannot silently bypass the comparison.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from datetime import datetime

__all__ = ["RateLimitEnforcer", "RateLimitSpec", "RateBreach"]

logger = logging.getLogger(__name__)


# A single window to enforce: (key, limit, window_seconds). ``key`` is opaque to
# the enforcer -- the engine composes it from ``(role, action, window-label)``.
RateLimitSpec = tuple[str, int, float]

# Returned on breach: (limit, window_seconds) of the FIRST window that tripped.
RateBreach = tuple[int, float]


class RateLimitEnforcer:
    """Stateful sliding-window rate-limit counter.

    One instance is owned by a :class:`~kailash.trust.pact.engine.GovernanceEngine`
    and consulted inside ``verify_action``. Thread-safe and fail-closed: the
    single public method :meth:`check_and_record` either admits a call (recording
    it in every window) or reports the first breached window, raising on a
    malformed spec so the engine can fail closed to ``BLOCKED``.
    """

    # Sliding-window GC cadence (seconds of OBSERVED time). The silent-key sweep
    # runs at most once per interval so the hot path stays O(1) between sweeps;
    # the size cap is the within-burst backstop. Mirrors the mcp enforcer.
    _RATE_GC_INTERVAL_SECONDS = 60.0
    # Hard backstop: max distinct keys retained. Only reached when more than this
    # many keys are simultaneously ACTIVE within one window (GC cannot reclaim
    # active keys); bounds memory under that extreme (trust-plane-security Rule 4).
    _MAX_TRACKER_ENTRIES = 10_000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> (window_seconds, deque[timestamp_float]). The window is stored
        # alongside the deque so the GC can compute each key's expiry cutoff.
        self._tracker: dict[str, tuple[float, deque[float]]] = {}
        # Observed-time high-water of the last GC sweep. None until the first
        # admitted call. Amortizes the O(n) silent-key sweep.
        self._last_gc_ts: float | None = None

    def check_and_record(
        self,
        specs: list[RateLimitSpec],
        now: datetime,
    ) -> RateBreach | None:
        """Atomically tally a call across EVERY window in ``specs``.

        The whole operation is one critical section (no check/record TOCTOU):

        * **Check phase** -- for each window, prune entries older than the
          window and test the live count against the limit. If ANY window is at
          or over its limit, the call is a breach and NOTHING is recorded (the
          breaching call does not consume budget in any window).
        * **Record phase** -- only when no window breached, append ``now`` to
          every window's deque.

        Args:
            specs: One ``(key, limit, window_seconds)`` per window to enforce.
                An empty list admits unconditionally (returns ``None``).
            now: The call's timestamp. All windows share this instant.

        Returns:
            ``None`` when the call is admitted (recorded in every window), or a
            ``(limit, window_seconds)`` naming the FIRST breached window.

        Raises:
            ValueError: If ``now`` or any spec's ``limit`` / ``window_seconds``
                is non-finite, or a window is non-positive. The engine converts
                this to a ``BLOCKED`` verdict (fail-closed), never fail-open.
        """
        now_ts = now.timestamp()
        if not math.isfinite(now_ts):
            raise ValueError("rate-limit 'now' timestamp is not finite")

        # Validate ALL specs up-front (finite guards -- pact-governance Rule 6).
        # A NaN/Inf limit would make `len(dq) >= limit` silently False forever.
        for key, limit, window_seconds in specs:
            if not math.isfinite(window_seconds) or window_seconds <= 0:
                raise ValueError(
                    f"rate-limit window_seconds must be finite and > 0 for key "
                    f"{key!r}, got {window_seconds!r}"
                )
            if not math.isfinite(float(limit)):
                raise ValueError(
                    f"rate-limit limit must be finite for key {key!r}, got {limit!r}"
                )

        with self._lock:
            # Amortized window-expiry GC (bounded memory, Rule 4).
            self._gc_expired(now_ts)

            # --- Check phase: NOTHING is recorded here. ---
            # A missing key counts as an empty window (count 0), so a limit of 0
            # blocks even the very first call (fail-closed edge).
            for key, limit, window_seconds in specs:
                cutoff = now_ts - window_seconds
                count = 0
                entry = self._tracker.get(key)
                if entry is not None:
                    _, dq = entry
                    while dq and dq[0] < cutoff:
                        dq.popleft()
                    count = len(dq)
                if count >= limit:
                    # Breach: budget already exhausted in this window.
                    return (limit, window_seconds)

            # --- Record phase: no window breached -> tally in EVERY window. ---
            for key, limit, window_seconds in specs:
                entry = self._tracker.get(key)
                if entry is None:
                    # New key: enforce the hard-cap backstop before inserting.
                    if len(self._tracker) >= self._MAX_TRACKER_ENTRIES:
                        self._evict_oldest(now_ts)
                    dq = deque((), maxlen=max(2, limit + 1))
                    self._tracker[key] = (window_seconds, dq)
                else:
                    stored_window, dq = entry
                    # If the declared limit GREW since this deque was created,
                    # its maxlen would cap storage below the new limit and the
                    # count could never reach it (fail-OPEN). Recreate wider,
                    # preserving the in-window entries.
                    needed = max(2, limit + 1)
                    if dq.maxlen is not None and dq.maxlen < needed:
                        dq = deque(dq, maxlen=needed)
                    self._tracker[key] = (window_seconds, dq)
                dq.append(now_ts)

        return None

    def _gc_expired(self, now_ts: float) -> None:
        """Reclaim keys whose sliding window has fully expired.

        A "silent" key is one whose most-recent timestamp is older than its
        window: its deque would prune to empty on the next call, so it holds no
        active rate state yet retains memory. This amortized sweep keeps the map
        sized to CURRENTLY-ACTIVE keys, closing the silent-key accumulation
        surface (mirrors ``McpGovernanceEnforcer._gc_expired_rate_entries``).

        Runs at most once per :data:`_RATE_GC_INTERVAL_SECONDS` of observed
        time. Out-of-order (earlier) timestamps simply skip the sweep; the size
        cap remains the within-burst backstop.

        Must be called while holding ``self._lock``.
        """
        last = self._last_gc_ts
        if last is not None and (now_ts - last) < self._RATE_GC_INTERVAL_SECONDS:
            return
        self._last_gc_ts = now_ts

        expired = [
            key
            for key, (window_seconds, dq) in self._tracker.items()
            if not dq or dq[-1] < now_ts - window_seconds
        ]
        for key in expired:
            del self._tracker[key]

        if expired:
            # Schema-safe: log the COUNT only -- never the (role, action) keys
            # (PII-adjacent per observability.md Rule 8). DEBUG so an amortized
            # sweep cannot flood aggregators.
            logger.debug(
                "RateLimitEnforcer: GC evicted %d silent key(s); %d active key(s) remain",
                len(expired),
                len(self._tracker),
            )

    def _evict_oldest(self, now_ts: float) -> None:
        """Hard-cap backstop: bound the tracker at :data:`_MAX_TRACKER_ENTRIES`.

        Frees ~10% of keys. Evicts fully-expired-window keys FIRST (safe -- they
        hold no active state); only if that does not free enough does it fall
        back to evicting the least-recently-active keys. Reaching the LRU
        fallback means more than the cap of keys are simultaneously ACTIVE
        within one window -- an overload in which memory protection takes
        precedence over per-key enforcement fidelity (a deliberate DoS bound).

        Must be called while holding ``self._lock``.
        """
        if not self._tracker:
            return

        target = max(1, len(self._tracker) // 10)

        # 1) Expired-window keys first -- safe, they hold no active state.
        expired = [
            key
            for key, (window_seconds, dq) in self._tracker.items()
            if not dq or dq[-1] < now_ts - window_seconds
        ]
        for key in expired:
            del self._tracker[key]
        if len(expired) >= target:
            return

        # 2) Still over budget -> evict least-recently-active as a last resort.
        # Empty deques sort first (-inf).
        def _last_ts(key: str) -> float:
            _, dq = self._tracker[key]
            return dq[-1] if dq else float("-inf")

        remaining = target - len(expired)
        for key in sorted(self._tracker.keys(), key=_last_ts)[:remaining]:
            del self._tracker[key]
