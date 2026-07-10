# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Universal outbound-effect governance interceptor (issue #1517 leg-b).

A single, domain-neutral seam that wraps ANY outbound effect an agent produces
-- HTTP requests, LLM completions, tool/MCP invocations -- in a governance
envelope BEFORE the effect leaves the process. The interceptor is a SEAM, not a
per-call API: transports install a governed dispatch callable once (via
:func:`wrap_transport` / :func:`wrap_transport_async` or the process-global
:func:`install_interceptor`), and every subsequent outbound call an agent makes
is governed transparently, with NO change to the agent's own code.

Design:

- :class:`OutboundEffect` -- a normalized, transport-agnostic descriptor of one
  outbound call (kind + operation + target + cost estimate + caller + metadata).
  The transport layer knows how to build one; the governance layer never needs
  to know which transport produced it. This is what makes the seam universal.
- :class:`EffectGovernor` -- the pluggable "should this effect proceed?"
  contract. :class:`EngineEffectGovernor` is the default, REUSING the canonical
  :class:`~kailash.trust.pact.engine.GovernanceEngine` envelope/verdict
  primitive -- it does NOT invent a parallel envelope.
- :class:`OutboundEffectInterceptor` -- the seam itself: evaluate -> record
  audit -> (allow) invoke transport / (refuse) raise. Fail-closed: any error in
  evaluation refuses the effect; the transport is NEVER invoked on refusal.

Security invariants (per pact-governance.md / trust-plane-security.md):

1. Fail-closed -- any exception during governance evaluation REFUSES the effect
   (the transport dispatch is never called). An effect that cannot be governed
   is never emitted.
2. NaN/Inf defense -- math.isfinite() on every numeric field (cost estimate) at
   construction; non-finite values are rejected (they bypass numeric envelope
   comparisons).
3. Bounded audit -- the in-memory audit trail is a deque(maxlen=N); it cannot
   grow without bound under a hostile effect stream.
4. Frozen records -- OutboundEffect / OutboundVerdict are frozen dataclasses;
   an audited decision cannot be mutated after the fact.
5. Audit-before-effect -- the governance decision is recorded to the audit
   trail (and any sink) BEFORE the transport dispatch runs, so the record
   survives even if the effect itself crashes.
6. No secrets in logs -- only kind/operation/target are logged; request bodies,
   arguments, prompts, and headers are never logged.
7. Thread-safe -- audit mutation acquires self._lock; the governor delegates to
   GovernanceEngine which holds its own lock.
"""

from __future__ import annotations

import logging
import math
import threading
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from functools import wraps
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Mapping,
    TypeVar,
)

from kailash.trust.pact.exceptions import PactError

if TYPE_CHECKING:
    from kailash.trust.pact.engine import GovernanceEngine

logger = logging.getLogger(__name__)

__all__ = [
    "EffectKind",
    "OutboundEffect",
    "OutboundVerdict",
    "OutboundEffectRefused",
    "EffectGovernor",
    "EngineEffectGovernor",
    "OutboundEffectInterceptor",
    "EffectBuilder",
    "wrap_transport",
    "wrap_transport_async",
    "install_interceptor",
    "active_interceptor",
    "clear_interceptor",
    "DEFAULT_MAX_AUDIT_ENTRIES",
]

T = TypeVar("T")

DEFAULT_MAX_AUDIT_ENTRIES = 1000


class EffectKind(str, Enum):
    """The kind of outbound effect being governed.

    Domain-neutral by construction: these are transport CATEGORIES, not
    domain concepts. Every outbound effect an agent can produce maps to one of
    these. ``OTHER`` is the catch-all for a transport not yet categorized (it is
    still fully governed -- ``OTHER`` is not a bypass).
    """

    HTTP = "http"
    LLM = "llm"
    TOOL = "tool"
    OTHER = "other"


@dataclass(frozen=True)
class OutboundEffect:
    """Normalized, transport-agnostic descriptor of one outbound effect.

    frozen=True: an effect descriptor handed to governance is an immutable
    record. The transport builds one of these from its own call parameters; the
    governance layer evaluates it without knowing which transport produced it.

    Attributes:
        kind: The transport category (:class:`EffectKind`).
        operation: The governance action name evaluated against the envelope
            (e.g. ``"http.POST"``, ``"llm.chat"``, ``"tool.search"``). This is
            the ``action`` passed to ``GovernanceEngine.verify_action``.
        target: The concrete destination (host, model name, tool name). Used for
            audit/observability; never used as a bypass.
        cost_estimate: Estimated cost of the effect for financial envelope
            checks. MUST be finite and non-negative.
        caller: The D/T/R role address (or resolved identity) of the effect's
            originator. Passed to the engine as ``role_address``. Empty string
            means "unknown caller" -- which fails closed at the engine.
        metadata: Extra transport context forwarded into the governance context
            dict. Never logged. Stored read-only (MappingProxyType).
    """

    kind: EffectKind
    operation: str
    target: str = ""
    cost_estimate: float = 0.0
    caller: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # --- kind ---
        if not isinstance(self.kind, EffectKind):
            raise ValueError(
                f"OutboundEffect.kind must be an EffectKind, got {type(self.kind).__name__!r}"
            )
        # --- operation ---
        if not isinstance(self.operation, str) or not self.operation.strip():
            raise ValueError(
                "OutboundEffect.operation must be a non-empty string "
                "(it is the governance action name)"
            )
        if not isinstance(self.target, str):
            raise ValueError("OutboundEffect.target must be a string")
        if not isinstance(self.caller, str):
            raise ValueError("OutboundEffect.caller must be a string")
        # --- cost_estimate: NaN/Inf defense (Rule 2) ---
        cost = self.cost_estimate
        if isinstance(cost, bool) or not isinstance(cost, (int, float)):
            raise ValueError(
                f"OutboundEffect.cost_estimate must be a real number, got {cost!r}"
            )
        if not math.isfinite(cost):
            raise ValueError(
                f"OutboundEffect.cost_estimate must be finite, got {cost!r}: "
                "NaN/Inf bypass numeric envelope comparisons."
            )
        if cost < 0:
            raise ValueError(
                f"OutboundEffect.cost_estimate must be non-negative, got {cost!r}"
            )
        # Freeze metadata into a read-only view (defensive; frozen dataclass).
        object.__setattr__(
            self, "metadata", MappingProxyType(dict(self.metadata or {}))
        )

    def governance_context(self) -> dict[str, Any]:
        """Build the context dict passed to ``GovernanceEngine.verify_action``.

        ``cost`` drives the financial envelope dimension. Transport metadata is
        merged UNDER ``cost`` so a hostile metadata payload cannot override the
        cost the transport computed.
        """
        ctx: dict[str, Any] = dict(self.metadata)
        ctx["cost"] = self.cost_estimate
        ctx["effect_kind"] = self.kind.value
        ctx["effect_target"] = self.target
        return ctx

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (metadata is NOT included -- it
        may carry sensitive transport context; only governance-relevant fields
        are emitted)."""
        return {
            "kind": self.kind.value,
            "operation": self.operation,
            "target": self.target,
            "cost_estimate": self.cost_estimate,
            "caller": self.caller,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OutboundEffect:
        """Reconstruct from a dict. Fail-closed on an unknown ``kind``."""
        raw_kind = data.get("kind")
        try:
            kind = EffectKind(str(raw_kind))
        except ValueError as exc:
            raise ValueError(
                f"Unknown EffectKind {raw_kind!r} -- fail-closed (refusing to "
                "reconstruct an ungoverned effect)."
            ) from exc
        return cls(
            kind=kind,
            operation=str(data.get("operation", "")),
            target=str(data.get("target", "")),
            cost_estimate=float(data.get("cost_estimate", 0.0)),
            caller=str(data.get("caller", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class OutboundVerdict:
    """Governance decision for one outbound effect.

    frozen=True: an immutable record of the decision. Wraps the underlying
    governance level/reason so the interceptor stays decoupled from whichever
    governor produced it.

    Attributes:
        allowed: True iff the effect may proceed (level auto_approved/flagged).
        level: The governance gradient level (auto_approved/flagged/held/blocked).
        reason: Human-readable explanation.
        effect: The effect this verdict is about.
        governance: Structured governance detail (e.g. GovernanceVerdict.to_dict()).
        timestamp: When the verdict was issued (UTC).
    """

    allowed: bool
    level: str
    reason: str
    effect: OutboundEffect
    governance: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "level": self.level,
            "reason": self.reason,
            "effect": self.effect.to_dict(),
            "governance": self.governance,
            "timestamp": self.timestamp.isoformat(),
        }


class OutboundEffectRefused(PactError):
    """Raised when governance refuses an outbound effect.

    The transport dispatch is NEVER invoked when this is raised -- the effect
    does not leave the process. Inherits :class:`PactError` (the PACT governance
    error family, ``.details``-carrying) so it is caught by governance handlers.

    Attributes:
        verdict: The :class:`OutboundVerdict` that caused the refusal.
    """

    def __init__(self, verdict: OutboundVerdict) -> None:
        self.verdict = verdict
        super().__init__(
            f"Outbound {verdict.effect.kind.value} effect "
            f"'{verdict.effect.operation}' REFUSED: {verdict.reason}",
            details={
                "level": verdict.level,
                "reason": verdict.reason,
                "kind": verdict.effect.kind.value,
                "operation": verdict.effect.operation,
                "target": verdict.effect.target,
                "caller": verdict.effect.caller,
            },
        )


class EffectGovernor(ABC):
    """Pluggable "should this outbound effect proceed?" contract.

    Domain-neutral: an implementation maps an :class:`OutboundEffect` to an
    :class:`OutboundVerdict` however it likes. The default
    :class:`EngineEffectGovernor` delegates to the canonical GovernanceEngine.
    Implementations MUST be fail-closed: on any internal error they MUST return
    a non-allowed verdict, never raise past :meth:`evaluate`.
    """

    @abstractmethod
    def evaluate(self, effect: OutboundEffect) -> OutboundVerdict:
        """Return a verdict for ``effect``. MUST NOT raise -- fail closed."""
        ...


class EngineEffectGovernor(EffectGovernor):
    """Default governor: REUSES ``GovernanceEngine`` for the decision.

    Maps every outbound effect onto ``engine.verify_action(caller, operation,
    {"cost": ..., ...})`` -- the canonical envelope + gradient + access
    primitive. Does NOT invent a parallel envelope model.

    Args:
        engine: The GovernanceEngine that holds the org, envelopes, and stores.
    """

    def __init__(self, engine: GovernanceEngine) -> None:
        self._engine = engine

    def evaluate(self, effect: OutboundEffect) -> OutboundVerdict:
        try:
            verdict = self._engine.verify_action(
                effect.caller,
                effect.operation,
                effect.governance_context(),
            )
            return OutboundVerdict(
                allowed=verdict.allowed,
                level=verdict.level,
                reason=verdict.reason,
                effect=effect,
                governance=verdict.to_dict(),
            )
        except Exception:  # fail-closed: never leak an ungoverned effect
            logger.exception(
                "EngineEffectGovernor: verify_action raised for kind=%s "
                "operation=%s -- fail-closed to REFUSED",
                effect.kind.value,
                effect.operation,
            )
            return OutboundVerdict(
                allowed=False,
                level="blocked",
                reason="Internal error during outbound governance -- fail-closed",
                effect=effect,
                governance={"error": "internal_error"},
            )


class OutboundEffectInterceptor:
    """The universal outbound-effect governance seam.

    Wrap any transport dispatch through :meth:`intercept` (sync) or
    :meth:`aintercept` (async). The interceptor evaluates the effect, records
    the decision to a bounded audit trail (BEFORE the effect runs), and either
    invokes the transport (allowed) or raises :class:`OutboundEffectRefused`
    (refused). The transport dispatch is NEVER called on refusal.

    Args:
        governor: The :class:`EffectGovernor` that decides each effect.
        audit_sink: Optional callable invoked with each :class:`OutboundVerdict`
            for external audit anchoring (e.g. an EATP emitter). Sink failures
            are logged and swallowed -- a broken sink MUST NOT crash the effect
            path, but it also MUST NOT allow a refused effect through.
        max_audit_entries: Bound on the in-memory audit deque.
    """

    def __init__(
        self,
        governor: EffectGovernor,
        *,
        audit_sink: Callable[[OutboundVerdict], None] | None = None,
        max_audit_entries: int = DEFAULT_MAX_AUDIT_ENTRIES,
    ) -> None:
        if not isinstance(governor, EffectGovernor):
            raise TypeError(
                "governor must be an EffectGovernor instance, got "
                f"{type(governor).__name__!r}"
            )
        if not isinstance(max_audit_entries, int) or max_audit_entries <= 0:
            raise ValueError("max_audit_entries must be a positive int")
        self._governor = governor
        self._audit_sink = audit_sink
        self._lock = threading.Lock()
        self._audit: deque[OutboundVerdict] = deque(maxlen=max_audit_entries)

    def evaluate(self, effect: OutboundEffect) -> OutboundVerdict:
        """Evaluate an effect and record the decision, WITHOUT dispatching.

        Fail-closed: if the governor itself raises (contract violation), the
        effect is refused.
        """
        try:
            verdict = self._governor.evaluate(effect)
        except Exception:
            logger.exception(
                "OutboundEffectInterceptor: governor raised for kind=%s "
                "operation=%s -- fail-closed to REFUSED",
                effect.kind.value,
                effect.operation,
            )
            verdict = OutboundVerdict(
                allowed=False,
                level="blocked",
                reason="Governor raised -- fail-closed",
                effect=effect,
                governance={"error": "governor_raised"},
            )
        # Audit-before-effect (Rule 5): record the decision before the transport
        # dispatch could possibly run.
        self._record(verdict)
        return verdict

    def _record(self, verdict: OutboundVerdict) -> None:
        with self._lock:
            self._audit.append(verdict)
        if self._audit_sink is not None:
            try:
                self._audit_sink(verdict)
            except Exception:
                logger.exception(
                    "OutboundEffectInterceptor: audit_sink raised for kind=%s "
                    "operation=%s -- swallowed (decision already recorded)",
                    verdict.effect.kind.value,
                    verdict.effect.operation,
                )

    def intercept(self, effect: OutboundEffect, invoke: Callable[[], T]) -> T:
        """Govern a SYNC outbound effect.

        Args:
            effect: The normalized effect descriptor.
            invoke: Zero-arg callable that performs the actual transport
                dispatch. Called ONLY if the effect is allowed.

        Returns:
            The transport dispatch result.

        Raises:
            OutboundEffectRefused: If governance refuses the effect (held or
                blocked). ``invoke`` is not called.
        """
        verdict = self.evaluate(effect)
        if not verdict.allowed:
            raise OutboundEffectRefused(verdict)
        return invoke()

    async def aintercept(
        self, effect: OutboundEffect, invoke: Callable[[], Awaitable[T]]
    ) -> T:
        """Govern an ASYNC outbound effect. Async mirror of :meth:`intercept`."""
        verdict = self.evaluate(effect)
        if not verdict.allowed:
            raise OutboundEffectRefused(verdict)
        return await invoke()

    def audit_log(self) -> tuple[OutboundVerdict, ...]:
        """Immutable snapshot of the bounded audit trail (oldest first)."""
        with self._lock:
            return tuple(self._audit)


# ---------------------------------------------------------------------------
# Transport seam binders -- turn any transport dispatch into a governed one.
# ---------------------------------------------------------------------------

# An EffectBuilder maps a transport call's (args, kwargs) to an OutboundEffect.
# The transport layer supplies one; the core stays domain-neutral.
EffectBuilder = Callable[[tuple[Any, ...], dict[str, Any]], OutboundEffect]


def wrap_transport(
    interceptor: OutboundEffectInterceptor,
    effect_builder: EffectBuilder,
    fn: Callable[..., T],
) -> Callable[..., T]:
    """Wrap a SYNC transport dispatch ``fn`` in the governance seam.

    Returns a callable with the same signature as ``fn``. Every call builds an
    :class:`OutboundEffect` via ``effect_builder`` and routes it through the
    interceptor. The caller of the returned function (an agent) does NOT know
    governance is happening -- that is the "no agent code change" property.
    """

    @wraps(fn)
    def governed(*args: Any, **kwargs: Any) -> T:
        effect = effect_builder(args, kwargs)
        return interceptor.intercept(effect, lambda: fn(*args, **kwargs))

    governed.__wrapped_governed__ = True  # type: ignore[attr-defined]
    return governed


def wrap_transport_async(
    interceptor: OutboundEffectInterceptor,
    effect_builder: EffectBuilder,
    fn: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    """Wrap an ASYNC transport dispatch ``fn`` in the governance seam.

    Async mirror of :func:`wrap_transport`.
    """

    @wraps(fn)
    async def governed(*args: Any, **kwargs: Any) -> T:
        effect = effect_builder(args, kwargs)
        return await interceptor.aintercept(effect, lambda: fn(*args, **kwargs))

    governed.__wrapped_governed__ = True  # type: ignore[attr-defined]
    return governed


# ---------------------------------------------------------------------------
# Process-global install registry -- transparent, no-agent-code-change install.
# ---------------------------------------------------------------------------

_active_lock = threading.Lock()
_active_interceptor: OutboundEffectInterceptor | None = None


def install_interceptor(interceptor: OutboundEffectInterceptor) -> None:
    """Install a process-global interceptor.

    Transports (or a bootstrap layer) call :func:`active_interceptor` to pick
    this up, so an operator can turn governance on for every outbound effect in
    the process WITHOUT touching any agent or transport call site.
    """
    if not isinstance(interceptor, OutboundEffectInterceptor):
        raise TypeError("install_interceptor requires an OutboundEffectInterceptor")
    global _active_interceptor
    with _active_lock:
        _active_interceptor = interceptor


def active_interceptor() -> OutboundEffectInterceptor | None:
    """Return the process-global interceptor, or None if none installed."""
    with _active_lock:
        return _active_interceptor


def clear_interceptor() -> None:
    """Remove the process-global interceptor (primarily for test isolation)."""
    global _active_interceptor
    with _active_lock:
        _active_interceptor = None
