# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Cross-SDK diagnostics protocols and data schemas.

The three primitives exposed here — ``TraceEvent``, ``JudgeCallable``,
and ``Diagnostic`` — are the Terrene Foundation's cross-SDK contract for
agent observability, LLM-as-judge scoring, and context-managed diagnostic
sessions. Every concrete diagnostic adapter (``DLDiagnostics``,
``LLMDiagnostics``, ``AgentDiagnostics``, ``RAGDiagnostics``, ...) either
emits ``TraceEvent`` records, accepts a ``JudgeCallable``, or satisfies
the ``Diagnostic`` Protocol.

Canonical schema: ``schemas/trace-event.v1.json`` at the repo root is the
language-neutral contract. Python emitters and Rust emitters MUST produce
byte-identical JSON + byte-identical SHA-256 fingerprints for identical
logical input (see ``compute_trace_event_fingerprint``).

Related rules:
  - ``rules/event-payload-classification.md`` — classified-PK hashing
    contract (``"sha256:<8-hex>"`` prefix) used for ``payload_hash``.
  - ``rules/agent-reasoning.md`` — why ``JudgeResult.winner`` is
    structured instead of regex-parsed from free-form LLM output.
  - ``rules/eatp.md`` — ``@dataclass`` frozen-by-default, explicit
    ``to_dict()`` / ``from_dict()``.

This module has zero runtime logic and zero optional dependencies.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Protocol, runtime_checkable

logger_name = __name__  # deliberately NOT binding a logger at module scope —
# zero-side-effect import is the contract for a protocol-only module.

__all__ = [
    "Diagnostic",
    "JudgeCallable",
    "JudgeInput",
    "JudgeResult",
    "JudgeWinner",
    "TraceEvent",
    "TraceEventType",
    "TraceEventStatus",
    "compute_trace_event_fingerprint",
]


# Type alias for the structured judge verdict. Idiomatic Python 3.11+ form
# that gives mypy / pyright static enforcement alongside the runtime
# frozenset check in ``JudgeResult.__post_init__``. The Rust equivalent
# is ``enum Winner { A, B, Tie }`` + ``Option<Winner>`` on the field.
JudgeWinner = Optional[Literal["A", "B", "tie"]]


# ---------------------------------------------------------------------------
# TraceEvent
# ---------------------------------------------------------------------------


class TraceEventType(str, Enum):
    """Enumerated event types for a TraceEvent.

    Cross-SDK contract — the exact set of values MUST match kailash-rs
    ``trace_event::EventType``. New values require cross-SDK coordination
    before landing in either repo (per ``rules/eatp.md`` §"Cross-SDK
    Alignment").
    """

    AGENT_RUN_START = "agent.run.start"
    AGENT_RUN_END = "agent.run.end"
    AGENT_STEP = "agent.step"
    TOOL_CALL_START = "tool.call.start"
    TOOL_CALL_END = "tool.call.end"
    LLM_CALL_START = "llm.call.start"
    LLM_CALL_END = "llm.call.end"
    JUDGE_VERDICT = "judge.verdict"
    LOOP_SUSPECTED = "loop.suspected"
    BUDGET_EXCEEDED = "budget.exceeded"
    ERROR = "error"


class TraceEventStatus(str, Enum):
    """Terminal status of an operation captured by a TraceEvent."""

    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TraceEvent:
    """One event in an agent or tool execution trace.

    Cross-SDK contract: see ``schemas/trace-event.v1.json`` for the
    language-neutral schema. Python emitters use this dataclass; Rust
    emitters use the matching ``serde``-derived struct. Field names,
    types, and canonicalization rules match byte-for-byte.

    Mandatory fields:
        event_id: Unique event identifier (UUID or equivalent).
        event_type: One of ``TraceEventType``.
        timestamp: UTC datetime with tzinfo. Serialized as ISO-8601 with
            explicit ``+00:00`` offset (never ``Z``).
        run_id: Correlation identifier for the enclosing agent run.
        agent_id: Identifier of the agent that emitted the event.
        cost_microdollars: Cost of this event in integer microdollars
            (``1 USD = 1_000_000 microdollars``). Integer to prevent
            float-accumulation drift across emitters (cross-SDK aligned
            with ``kaizen.cost.tracker`` + kailash-rs#38).

    Optional fields are ``None``-defaulted:

      - ``tenant_id`` — when populated, downstream sinks MUST partition
        storage, metrics, and audit rows by tenant (see
        ``rules/tenant-isolation.md`` §§4–5). ``None`` is permitted only
        for single-tenant deployments where tenant isolation does not
        apply.
      - ``payload`` — emitters MUST apply
        ``rules/event-payload-classification.md`` rules before populating
        this field: classified string PKs hash to ``payload_hash``
        (below) and are EXCLUDED from ``payload``. This is an emitter
        responsibility (not a runtime guard the Protocol enforces); the
        Protocol only defines the field shape.
      - ``payload_hash`` — ``"sha256:<8-hex>"`` format mandated by
        ``rules/event-payload-classification.md`` §2 when the payload
        holds classified values; otherwise ``None``. Eight hex chars
        (32 bits of entropy) is the cross-SDK contract: sufficient for
        forensic correlation across event + log + DB audit streams,
        insufficient for rainbow-table reversal of typical PK strings.

    Frozen to prevent post-emission mutation (which would invalidate any
    fingerprint already computed).
    """

    # Mandatory
    event_id: str
    event_type: TraceEventType
    timestamp: datetime
    run_id: str
    agent_id: str
    cost_microdollars: int

    # Optional correlation
    parent_event_id: Optional[str] = None
    trace_id: Optional[str] = None  # OTel correlation
    span_id: Optional[str] = None
    tenant_id: Optional[str] = None
    envelope_id: Optional[str] = None  # PACT envelope correlation

    # Optional operation detail
    tool_name: Optional[str] = None
    llm_model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    duration_ms: Optional[float] = None
    status: Optional[TraceEventStatus] = None

    # Optional payload. Emitters MUST apply
    # rules/event-payload-classification.md rules before populating —
    # classified string PKs hash to payload_hash (``sha256:<8-hex>``) and
    # are EXCLUDED from payload. Schema validation of payload contents is
    # the adapter's responsibility; the Protocol defines only the field
    # shape.
    payload_hash: Optional[str] = None
    payload: Optional[dict] = None

    def __post_init__(self) -> None:
        # Timestamp MUST be timezone-aware. Naive datetimes silently
        # serialize without an offset, breaking cross-SDK fingerprint
        # parity with Rust (which always emits "+00:00").
        if self.timestamp.tzinfo is None:
            raise ValueError(
                "TraceEvent.timestamp must be timezone-aware (UTC). "
                "Got a naive datetime — use datetime.now(UTC) or "
                "datetime.fromisoformat with an explicit offset."
            )
        # Cost is an integer contract. Accepting floats silently would
        # let one emitter record $0.000001 and another record 0
        # microdollars for the same operation.
        if not isinstance(self.cost_microdollars, int) or isinstance(
            self.cost_microdollars, bool
        ):
            raise TypeError(
                "TraceEvent.cost_microdollars must be an int (microdollars). "
                f"Got {type(self.cost_microdollars).__name__}."
            )
        if self.cost_microdollars < 0:
            raise ValueError(
                f"TraceEvent.cost_microdollars must be non-negative, "
                f"got {self.cost_microdollars}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict with canonical shape.

        The returned dict matches ``schemas/trace-event.v1.json`` exactly.
        Optional ``None`` fields are preserved (not dropped) so the shape
        is stable across round-trips — a Rust consumer reading this dict
        always sees the full set of known fields.
        """
        d = asdict(self)
        # Enum values → strings.
        d["event_type"] = self.event_type.value
        d["status"] = self.status.value if self.status is not None else None
        # Timestamp → ISO-8601 with explicit +00:00 offset.
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceEvent":
        """Deserialize from the canonical dict shape.

        Raises:
            KeyError: If a mandatory field is absent.
            ValueError: If an enum string is unknown or the timestamp
                cannot be parsed.
        """
        ts = data["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        status_raw = data.get("status")
        status = TraceEventStatus(status_raw) if status_raw is not None else None
        return cls(
            event_id=data["event_id"],
            event_type=TraceEventType(data["event_type"]),
            timestamp=ts,
            run_id=data["run_id"],
            agent_id=data["agent_id"],
            cost_microdollars=int(data["cost_microdollars"]),
            parent_event_id=data.get("parent_event_id"),
            trace_id=data.get("trace_id"),
            span_id=data.get("span_id"),
            tenant_id=data.get("tenant_id"),
            envelope_id=data.get("envelope_id"),
            tool_name=data.get("tool_name"),
            llm_model=data.get("llm_model"),
            prompt_tokens=data.get("prompt_tokens"),
            completion_tokens=data.get("completion_tokens"),
            duration_ms=data.get("duration_ms"),
            status=status,
            payload_hash=data.get("payload_hash"),
            payload=data.get("payload"),
        )


def compute_trace_event_fingerprint(event: TraceEvent) -> str:
    """Compute the canonical SHA-256 fingerprint of a ``TraceEvent``.

    The fingerprint is the cross-SDK correlation anchor — Python and
    Rust emitters MUST produce identical 64-hex-char digests for the
    same logical input.

    Canonicalization contract (matches ``kailash-rs#449`` audit-chain
    and ``rules/event-payload-classification.md`` §2 cost-tracker
    fingerprint):

      - ``event.to_dict()`` yields the canonical-shape dict.
      - ``json.dumps(..., sort_keys=True, separators=(",", ":"),
         ensure_ascii=True, default=str)`` produces compact JSON
         matching Rust ``serde_json::to_string(&BTreeMap)`` byte-for-byte.
      - SHA-256 of the UTF-8 bytes, hex-encoded lowercase.

    Verification in consumers uses ``hmac.compare_digest`` — never
    ``==`` on hex strings (timing side-channel; see ``rules/security.md``
    § Rust Credential Comparison and ``rules/eatp.md`` § Cryptography).
    """
    d = event.to_dict()
    canonical = json.dumps(
        d,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# JudgeCallable + JudgeInput + JudgeResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JudgeInput:
    """Input to an LLM-as-judge evaluation.

    ``candidate_b`` distinguishes the two judge modes:
      - pointwise: ``candidate_b`` is ``None`` — score ``candidate_a``.
      - pairwise: both candidates present — pick a winner.

    ``rubric`` is free-form text. The contract deliberately avoids a
    hardcoded rubric taxonomy — that decision belongs in the adapter,
    not the core protocol. Individual adapters (e.g. ``kaizen.judges``)
    MAY ship a set of standard rubrics.
    """

    prompt: str
    candidate_a: str
    candidate_b: Optional[str] = None
    reference: Optional[str] = None
    rubric: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JudgeInput":
        return cls(
            prompt=data["prompt"],
            candidate_a=data["candidate_a"],
            candidate_b=data.get("candidate_b"),
            reference=data.get("reference"),
            rubric=data.get("rubric"),
        )


@dataclass(frozen=True)
class JudgeResult:
    """Output of an LLM-as-judge evaluation.

    Structured fields — ``score`` / ``winner`` / ``reasoning`` —
    eliminate the regex-parsing anti-pattern that
    ``rules/agent-reasoning.md`` §3 BLOCKS. Adapters implementing
    ``JudgeCallable`` MUST populate these from a Signature OutputField,
    not via post-hoc regex on free-form LLM output.

    ``cost_microdollars``, ``prompt_tokens``, ``completion_tokens``
    are always non-negative integers for the same reason as
    ``TraceEvent.cost_microdollars``.
    """

    score: Optional[float]
    winner: JudgeWinner  # "A" | "B" | "tie" | None
    reasoning: Optional[str]
    judge_model: str
    cost_microdollars: int
    prompt_tokens: int
    completion_tokens: int

    # Runtime defense-in-depth alongside the static ``JudgeWinner`` type
    # alias. Kept explicit so a wire-boundary ``from_dict`` rejects
    # unknown strings loudly.
    _VALID_WINNERS = frozenset({"A", "B", "tie", None})

    def __post_init__(self) -> None:
        if self.winner not in self._VALID_WINNERS:
            raise ValueError(
                "JudgeResult.winner must be one of ('A', 'B', 'tie', None), "
                f"got {self.winner!r}."
            )
        for name, value in (
            ("cost_microdollars", self.cost_microdollars),
            ("prompt_tokens", self.prompt_tokens),
            ("completion_tokens", self.completion_tokens),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(
                    f"JudgeResult.{name} must be int, got {type(value).__name__}."
                )
            if value < 0:
                raise ValueError(
                    f"JudgeResult.{name} must be non-negative, got {value}."
                )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JudgeResult":
        return cls(
            score=data.get("score"),
            winner=data.get("winner"),
            reasoning=data.get("reasoning"),
            judge_model=data["judge_model"],
            cost_microdollars=int(data["cost_microdollars"]),
            prompt_tokens=int(data["prompt_tokens"]),
            completion_tokens=int(data["completion_tokens"]),
        )


@runtime_checkable
class JudgeCallable(Protocol):
    """Async callable protocol for LLM-as-judge scoring.

    Implementations accept a ``JudgeInput`` and return a ``JudgeResult``.
    The Protocol is async because every production implementation backs
    onto an LLM call — synchronous ``JudgeCallable`` is permitted at the
    type level but discouraged (sync LLM calls block the event loop).

    Use ``isinstance(obj, JudgeCallable)`` to verify conformance at
    wire boundaries.
    """

    async def __call__(self, judge_input: JudgeInput) -> JudgeResult: ...


# ---------------------------------------------------------------------------
# Diagnostic context-manager protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Diagnostic(Protocol):
    """Context-manager Protocol for a runtime diagnostic session.

    Every concrete diagnostic adapter (DL, RAG, Agent, Interpretability,
    Alignment) conforms to this Protocol. The adapter owns:

      - ``run_id`` — correlation identifier for this diagnostic session.
      - context-manager semantics — ``__enter__`` / ``__exit__`` so the
        caller can wrap instrumented code in a ``with`` block.
      - ``report()`` — return a dict summary of the captured diagnostic
        at the end of the session.

    ``plot()`` is intentionally NOT on this Protocol. Plotting pulls
    heavy optional deps (plotly, matplotlib); it lives on concrete
    classes gated by adapter-specific extras (``kailash[plot]``,
    ``kaizen[judges]``, etc.). ``report()`` is always available and
    always returns pure Python data.
    """

    run_id: str

    def __enter__(self) -> "Diagnostic": ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Optional[bool]: ...
    def report(self) -> dict[str, Any]: ...
