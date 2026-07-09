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
4. **Bounded memory, fail-CLOSED at the cap.** Each key is a
   ``deque(maxlen=limit+1)``; an amortized window-expiry GC reclaims silent
   keys (``trust-plane-security.md`` Rule 4). At the hard cap the enforcer
   reclaims only EXPIRED keys and, if that does not free room, REFUSES the new
   key (a ``"capacity"`` breach) -- it NEVER evicts an ACTIVE-window key,
   because doing so would reset that key's live tally to 0, a fail-OPEN
   rate-limit bypass (a throttled agent could flood junk keys to evict its own
   active tally). Refusing new keys bounds memory without ever resetting a live
   count.
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
from typing import Literal, NamedTuple

__all__ = ["RateLimitEnforcer", "RateLimitSpec", "RateBreach"]

logger = logging.getLogger(__name__)


# A single window to enforce: (key, limit, window_seconds). ``key`` is opaque to
# the enforcer -- the engine composes it from ``(role, action, window-label)``.
RateLimitSpec = tuple[str, int, float]


class RateBreach(NamedTuple):
    """A rate-limit breach, returned by :meth:`RateLimitEnforcer.check_and_record`.

    ``kind`` discriminates the two breach causes so the engine can render a
    precise, non-misleading audit reason:

    * ``"window"`` -- a window's LIVE tally reached its declared limit.
    * ``"capacity"`` -- the tracker is at its hard cap and admitting a NEW key
      would require evicting an ACTIVE-window key (which would reset that key's
      live tally to 0 = a fail-OPEN rate-limit bypass). The enforcer instead
      REFUSES the new call (fail-CLOSED); nothing is recorded.
    """

    limit: int
    window_seconds: float
    kind: Literal["window", "capacity"]


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

        If admitting the call would require creating NEW keys beyond the hard
        cap AND expired-key reclamation cannot free room, the call is REFUSED
        with a ``"capacity"`` breach (fail-closed) -- no active tally is ever
        evicted to make room.

        Returns:
            ``None`` when the call is admitted (recorded in every window), or a
            :class:`RateBreach` naming the FIRST breached window
            (``kind="window"``) or a capacity refusal (``kind="capacity"``).

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
                    return RateBreach(limit, window_seconds, "window")

            # --- Capacity guard (fail-CLOSED): admitting NEW keys MUST NOT
            # evict an ACTIVE-window key. Reclaim EXPIRED keys only (safe -- no
            # live tally); if the new keys STILL do not fit, REFUSE the whole
            # call (record nothing) so no active tally is ever reset to 0.
            new_specs = [s for s in specs if s[0] not in self._tracker]
            if new_specs and (
                len(self._tracker) + len(new_specs) > self._MAX_TRACKER_ENTRIES
            ):
                self._reclaim_expired(now_ts)
                new_specs = [s for s in specs if s[0] not in self._tracker]
                if new_specs and (
                    len(self._tracker) + len(new_specs) > self._MAX_TRACKER_ENTRIES
                ):
                    first = new_specs[0]
                    return RateBreach(first[1], first[2], "capacity")

            # --- Record phase: no breach, capacity OK -> tally EVERY window. ---
            for key, limit, window_seconds in specs:
                entry = self._tracker.get(key)
                if entry is None:
                    dq = deque((), maxlen=max(2, limit + 1))
                    self._tracker[key] = (window_seconds, dq)
                else:
                    _stored_window, dq = entry
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

    def _reclaim_expired(self, now_ts: float) -> None:
        """Capacity-pressure backstop: reclaim ONLY fully-expired-window keys.

        Unlike the amortized :meth:`_gc_expired`, this runs UNCONDITIONALLY (it
        is called from the capacity guard, not the hot path). It evicts a key
        only when that key's sliding window has fully expired -- i.e. it holds
        NO live tally. It NEVER evicts an ACTIVE-window key.

        This is the fail-CLOSED half of the memory bound: evicting an active key
        would reset its live rate tally to 0, a rate-limit RESET bypass (a
        throttled agent floods junk keys to evict its own active ``(role,
        action)`` key, then calls again with a fresh full budget). When expired
        keys alone cannot free room, :meth:`check_and_record` REFUSES the new
        key instead (a ``"capacity"`` breach), so memory stays bounded without
        ever resetting an active count.

        Must be called while holding ``self._lock``.
        """
        expired = [
            key
            for key, (window_seconds, dq) in self._tracker.items()
            if not dq or dq[-1] < now_ts - window_seconds
        ]
        for key in expired:
            del self._tracker[key]
        if expired:
            # Schema-safe: COUNT only -- never the (role, action) keys.
            logger.debug(
                "RateLimitEnforcer: reclaimed %d expired key(s) under capacity "
                "pressure; %d active key(s) remain (new keys refused, not evicted)",
                len(expired),
                len(self._tracker),
            )
