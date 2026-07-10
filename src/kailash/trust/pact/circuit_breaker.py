# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Stateful trip-and-hold governance circuit-breaker for the PACT verdict path.

The governance envelope carries *declared* circuit-breaker parameters
(``operational.circuit_failure_threshold`` / ``circuit_window_seconds`` /
``circuit_cooldown_seconds``), but until this module the ONLY breaker in the
trust plane was :class:`~kailash.trust.circuit_breaker.PostureCircuitBreaker` --
an ORCHESTRATION-only posture-downgrade helper keyed by ``agent_id`` that is
NEVER consulted in the verdict path (BH5 #1510). A repeatedly-escalating
``(role, action)`` was therefore never auto-held by a first-class governance
control.

:class:`PactCircuitBreaker` closes that gap: it keeps a stateful three-state
machine per opaque ``key`` (the engine composes it from ``(role, action)``) that
TRIPS after ``N`` breached calls inside a ``W``-second sliding window, HOLDS the
key blocked for a ``C``-second cooldown, then admits exactly ONE probe. It
adapts the proven deque sliding-window + fail-CLOSED-eviction discipline of
:class:`~kailash.trust.pact.rate_limit_enforcer.RateLimitEnforcer` into a
trip-and-hold breaker -- the same ``deque(maxlen=...)`` failure tracker,
per-key window pruning, amortized window-expiry GC, and hard-cap eviction that
NEVER resets a live/tripped key.

Three states per ``key``:

* **CLOSED** -- normal. Every call is admitted; breached calls accumulate in the
  sliding window; the ``N``-th in-window breach TRIPS the breaker to OPEN.
* **OPEN** -- tripped. Every call is BLOCKED (fail-closed hold) until the
  cooldown elapses.
* **HALF_OPEN** -- cooldown elapsed; exactly ONE probe call is admitted. A
  breached probe re-TRIPS to OPEN (fresh cooldown); a clean probe RESETS to
  CLOSED. A second concurrent call while a probe is in flight is BLOCKED.

Security invariants (each pinned by a test):

1. **Trip after N in-window breaches.** ``N`` breached calls inside window ``W``
   move CLOSED -> OPEN; the next call is BLOCKED (a breach can only TIGHTEN the
   engine verdict, never loosen it -- composed via ``combine_levels``).
2. **Fail-closed.** A malformed config (non-finite / non-positive window or
   cooldown, threshold ``< 1``) or a non-finite ``now`` raises ``ValueError``
   the engine converts to ``BLOCKED`` -- never a permissive result
   (``pact-governance.md`` Rule 4 / Rule 6). ``check`` on an OPEN key inside
   cooldown BLOCKS; a breaker-blocked call is NOT recorded (it is not a real
   governance outcome).
3. **Thread-safe, atomic transition.** Every state read + transition is one
   critical section under ``self._lock`` (``pact-governance.md`` Rule 8) -- no
   TOCTOU between the state check and the transition. The engine nests this
   inside its own ``_verify_action_locked`` lock, exactly like the rate enforcer.
4. **Bounded memory, fail-CLOSED at the cap.** Each key holds a
   ``deque(maxlen=N+1)`` of failure timestamps; an amortized window-expiry GC
   reclaims silent CLOSED keys (``trust-plane-security.md`` Rule 4). At the hard
   cap the breaker reclaims ONLY fully-expired CLOSED keys and, if that does not
   free room, REFUSES the new key (a ``"capacity"`` block) -- it NEVER evicts an
   OPEN or HALF_OPEN key, because doing so would silently reset a TRIPPED
   breaker to CLOSED, a fail-OPEN bypass (a flood of junk keys could otherwise
   evict a tripped ``(role, action)`` and clear its hold).
5. **Finite guards.** Window / cooldown / now / threshold are validated with
   ``math.isfinite`` (``pact-governance.md`` Rule 6) so a ``NaN``/``Inf`` value
   cannot silently bypass a ``<`` comparison.
6. **No self-feedback.** The breaker never records its OWN block as a breach --
   ``check`` returns ``record=False`` on every path where it blocks, so the
   engine's ``breached`` signal reflects only the UNDERLYING governance outcome
   (the level snapshotted BEFORE the breaker step).
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from datetime import datetime
from typing import Literal, NamedTuple

__all__ = ["PactCircuitBreaker", "CircuitBreakerConfig", "CircuitDecision"]

logger = logging.getLogger(__name__)


class CircuitBreakerConfig(NamedTuple):
    """Per-key breaker parameters. ``key`` is opaque to the breaker -- the engine
    composes it from ``(role, action)`` and the config from the effective
    envelope's ``operational.circuit_*`` fields.

    * ``failure_threshold`` -- ``N``: in-window breaches that TRIP the breaker.
    * ``window_seconds`` -- ``W``: sliding window over which breaches accumulate.
    * ``cooldown_seconds`` -- ``C``: how long an OPEN key HOLDS before a probe.
    """

    failure_threshold: int
    window_seconds: float
    cooldown_seconds: float


class CircuitDecision(NamedTuple):
    """The verdict of :meth:`PactCircuitBreaker.check`.

    * ``level`` -- ``"auto_approved"`` (admit) or ``"blocked"`` (fail-closed
      hold). The engine composes it MONOTONICALLY via ``combine_levels``.
    * ``record`` -- whether the engine should call :meth:`record` after the
      final verdict. ``False`` on every BLOCK path (a breaker-blocked call is
      not a real governance outcome -- recording it would be self-feedback).
    * ``was_probe`` -- whether the admitted call is the single HALF_OPEN probe.
      The engine passes this back to :meth:`record` so a clean probe RESETS and
      a breached probe re-TRIPS.
    * ``state`` -- the state the ``check`` observed / transitioned to, for audit
      (``"closed"`` / ``"open"`` / ``"half_open"`` / ``"capacity"``).
    """

    level: Literal["auto_approved", "blocked"]
    record: bool
    was_probe: bool
    state: str


class _KeyState:
    """Mutable per-key breaker state. Guarded by :attr:`PactCircuitBreaker._lock`."""

    __slots__ = ("state", "failures", "opened_at", "window_seconds")

    def __init__(self, maxlen: int, window_seconds: float) -> None:
        self.state: str = "closed"
        # Sliding window of failure timestamps (float seconds). Bounded like the
        # rate enforcer: maxlen == N+1 so the N-th in-window breach is always
        # observable before the oldest is dropped.
        self.failures: deque[float] = deque((), maxlen=maxlen)
        self.opened_at: float | None = None
        # Stored so the GC / reclaim can compute this key's own expiry cutoff
        # without the caller's config (a reclaim sweeps ALL keys at once).
        self.window_seconds: float = window_seconds


class PactCircuitBreaker:
    """Stateful trip-and-hold governance circuit-breaker.

    One instance is owned by a
    :class:`~kailash.trust.pact.engine.GovernanceEngine` and consulted at
    ``verify_action`` Step 3.7. Thread-safe and fail-closed: :meth:`check`
    decides admit/block for the current call, and :meth:`record` -- called AFTER
    the final verdict -- feeds back the underlying breach signal that trips /
    resets the breaker.
    """

    # Amortized silent-key GC cadence (seconds of OBSERVED time). Mirrors the
    # rate enforcer: the O(n) sweep runs at most once per interval so the hot
    # path stays O(1) between sweeps; the size cap is the within-burst backstop.
    _GC_INTERVAL_SECONDS = 60.0
    # Hard backstop: max distinct keys retained. Only reached when more than
    # this many keys are simultaneously live (OPEN/HALF_OPEN, or CLOSED with an
    # unexpired window); bounds memory under that extreme (trust-plane-security
    # Rule 4) WITHOUT ever resetting a tripped breaker.
    _MAX_TRACKER_ENTRIES = 10_000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tracker: dict[str, _KeyState] = {}
        # Observed-time high-water of the last amortized GC sweep. None until the
        # first admitted call.
        self._last_gc_ts: float | None = None

    # -- validation --------------------------------------------------------

    @staticmethod
    def _validate(config: CircuitBreakerConfig, now: datetime) -> float:
        """Finite-guard the config + ``now`` (``pact-governance.md`` Rule 6).

        Returns the finite ``now`` timestamp. Raises ``ValueError`` on any
        malformed input so the engine can fail CLOSED to ``BLOCKED`` -- a
        ``NaN``/``Inf`` window/cooldown would make the ``<`` cooldown comparison
        vacuously False and silently release a tripped breaker.
        """
        now_ts = now.timestamp()
        if not math.isfinite(now_ts):
            raise ValueError("circuit-breaker 'now' timestamp is not finite")
        threshold = config.failure_threshold
        if not math.isfinite(float(threshold)) or int(threshold) < 1:
            raise ValueError(
                f"circuit-breaker failure_threshold must be a finite int >= 1, "
                f"got {threshold!r}"
            )
        for label, val in (
            ("window_seconds", config.window_seconds),
            ("cooldown_seconds", config.cooldown_seconds),
        ):
            if not math.isfinite(val) or val <= 0:
                raise ValueError(
                    f"circuit-breaker {label} must be finite and > 0, got {val!r}"
                )
        return now_ts

    # -- public API --------------------------------------------------------

    def check(
        self,
        key: str,
        config: CircuitBreakerConfig,
        now: datetime,
    ) -> CircuitDecision:
        """Decide admit/block for the current call against ``key``'s state.

        * No stored state / CLOSED -> ``auto_approved`` (``record=True``).
        * OPEN within cooldown -> ``blocked`` (``record=False`` -- fail-closed
          hold; a breaker-blocked call is not recorded).
        * OPEN with cooldown elapsed -> transition HALF_OPEN, admit this call as
          the single probe (``auto_approved``, ``record=True``, ``was_probe=True``).
        * HALF_OPEN (a probe already in flight) -> ``blocked`` (``record=False``;
          only one probe at a time).
        * A NEW key at the hard cap that cannot be admitted without evicting a
          live/tripped key -> ``blocked`` with ``state="capacity"`` (fail-closed;
          nothing is created).

        Raises:
            ValueError: On a malformed config / non-finite ``now`` -- the engine
                converts this to ``BLOCKED`` (fail-closed), never fail-open.
        """
        now_ts = self._validate(config, now)
        with self._lock:
            self._gc_expired(now_ts)
            entry = self._tracker.get(key)

            if entry is None:
                # A brand-new key is implicitly created by a later record().
                # Guard the hard cap BEFORE that creation: reclaim ONLY expired
                # CLOSED keys, and if room still cannot be freed, REFUSE (a
                # live/tripped key is NEVER evicted -- that would reset a hold).
                if len(self._tracker) >= self._MAX_TRACKER_ENTRIES:
                    self._reclaim_expired(now_ts)
                    if len(self._tracker) >= self._MAX_TRACKER_ENTRIES:
                        return CircuitDecision("blocked", False, False, "capacity")
                return CircuitDecision("auto_approved", True, False, "closed")

            if entry.state == "closed":
                return CircuitDecision("auto_approved", True, False, "closed")

            if entry.state == "open":
                if (
                    entry.opened_at is not None
                    and (now_ts - entry.opened_at) < config.cooldown_seconds
                ):
                    # Fail-closed hold: still inside cooldown. Do NOT record.
                    return CircuitDecision("blocked", False, False, "open")
                # Cooldown elapsed -> admit exactly ONE probe.
                entry.state = "half_open"
                return CircuitDecision("auto_approved", True, True, "half_open")

            # half_open: a probe is already in flight -> only one at a time.
            return CircuitDecision("blocked", False, False, "half_open")

    def record(
        self,
        key: str,
        config: CircuitBreakerConfig,
        now: datetime,
        *,
        breached: bool,
        was_probe: bool,
    ) -> None:
        """Feed the underlying breach signal back into ``key``'s state machine.

        Called by the engine AFTER the final verdict, with ``breached`` reflecting
        the governance outcome EXCLUDING the breaker's own contribution (the level
        snapshotted BEFORE Step 3.7), and ``was_probe`` from the prior
        :meth:`check` decision.

        * ``was_probe`` and ``breached`` -> re-TRIP to OPEN (fresh cooldown).
        * ``was_probe`` and clean -> RESET to CLOSED (clear the failure window).
        * CLOSED and ``breached`` -> append the failure, prune to window ``W``;
          the ``N``-th in-window failure TRIPS to OPEN.
        * CLOSED and clean -> sliding-window decay only (prune expired failures;
          the window is NOT hard-reset -- time handles decay, matching the rate
          enforcer's sliding model).
        * OPEN / HALF_OPEN (non-probe) -> no-op (``check`` already gated this;
          ``record`` is only invoked with ``record=True``).

        Raises:
            ValueError: On a malformed config / non-finite ``now`` (fail-closed).
        """
        now_ts = self._validate(config, now)
        needed = max(2, int(config.failure_threshold) + 1)
        with self._lock:
            entry = self._tracker.get(key)
            if entry is None:
                entry = _KeyState(maxlen=needed, window_seconds=config.window_seconds)
                self._tracker[key] = entry

            if was_probe:
                # The single HALF_OPEN probe resolved.
                entry.failures.clear()
                if breached:
                    entry.state = "open"
                    entry.opened_at = now_ts
                else:
                    entry.state = "closed"
                    entry.opened_at = None
                return

            if entry.state != "closed":
                # OPEN / HALF_OPEN keys are gated by check(); a non-probe record
                # never legitimately reaches them. No-op (never silently reset).
                return

            # CLOSED path. Keep the failure deque wide enough for the current
            # threshold (a grown N must still be countable -- mirrors the rate
            # enforcer's maxlen-grow guard).
            if entry.failures.maxlen is not None and entry.failures.maxlen < needed:
                entry.failures = deque(entry.failures, maxlen=needed)
            entry.window_seconds = config.window_seconds

            cutoff = now_ts - config.window_seconds
            if breached:
                entry.failures.append(now_ts)
                while entry.failures and entry.failures[0] < cutoff:
                    entry.failures.popleft()
                if len(entry.failures) >= int(config.failure_threshold):
                    entry.state = "open"
                    entry.opened_at = now_ts
            else:
                # Sliding-window decay: prune expired failures, do NOT clear.
                while entry.failures and entry.failures[0] < cutoff:
                    entry.failures.popleft()

    # -- bounded-memory backstops -----------------------------------------

    def _gc_expired(self, now_ts: float) -> None:
        """Amortized reclaim of silent CLOSED keys (bounded memory, Rule 4).

        A CLOSED key whose most-recent failure is older than its window (or which
        has none) holds no live breaker state yet retains memory. This sweep
        reclaims those, keeping the map sized to CURRENTLY-active keys. It NEVER
        touches an OPEN or HALF_OPEN key (a tripped/held breaker MUST persist
        across its cooldown regardless of how long ago it tripped). Runs at most
        once per :data:`_GC_INTERVAL_SECONDS` of observed time.

        Must be called while holding ``self._lock``.
        """
        last = self._last_gc_ts
        if last is not None and (now_ts - last) < self._GC_INTERVAL_SECONDS:
            return
        self._last_gc_ts = now_ts
        self._reclaim_expired(now_ts)

    def _reclaim_expired(self, now_ts: float) -> None:
        """Reclaim ONLY fully-expired-window CLOSED keys.

        The fail-CLOSED half of the memory bound: an OPEN / HALF_OPEN key is
        NEVER evicted, because evicting a tripped key would reset its hold to
        CLOSED -- a fail-OPEN breaker bypass (a flood of junk keys could evict a
        throttled ``(role, action)`` and clear its block). When expired CLOSED
        keys alone cannot free room, :meth:`check` REFUSES the new key instead.

        Must be called while holding ``self._lock``.
        """
        expired = [
            k
            for k, s in self._tracker.items()
            if s.state == "closed"
            and (not s.failures or s.failures[-1] < now_ts - s.window_seconds)
        ]
        for k in expired:
            del self._tracker[k]
        if expired:
            # Schema-safe: COUNT only -- never the (role, action) keys
            # (PII-adjacent per observability.md Rule 8). DEBUG so an amortized
            # sweep cannot flood aggregators.
            logger.debug(
                "PactCircuitBreaker: reclaimed %d silent closed key(s); "
                "%d live key(s) remain (tripped keys never evicted)",
                len(expired),
                len(self._tracker),
            )
