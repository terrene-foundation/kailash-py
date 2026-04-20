# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Frozen result dataclasses for absorbed PACT governance capabilities (#567).

PR#7 of 7 in issue #567 REJECTS MLFP's `GovernanceDiagnostics` (716 LOC
parallel facade). Instead, this module defines the frozen result types
returned by first-class methods on existing PACT classes:

- ``PactEngine.verify_audit_chain(...)`` -> ``ChainVerificationResult``
- ``PactEngine.envelope_snapshot(...)`` -> ``EnvelopeSnapshot``
- ``PactEngine.iter_audit_anchors(...)`` -> ``Iterator[AuditAnchor]``
- ``CostTracker.consumption_report(...)`` -> ``ConsumptionReport``
- ``pact.governance.testing.run_negative_drills(...)`` -> ``list[NegativeDrillResult]``

All result dataclasses are ``frozen=True`` per PACT MUST Rule 1 — immutable
records survive pickling, IPC, and cannot be widened at runtime.

Security invariants:
- Fail-closed: a failed chain verification returns ``is_valid=False`` with
  a ``first_break_reason`` rather than raising (PACT MUST Rule 4).
- Monotonic: ``sequence`` counters are never reset, ``verified_count`` is
  always non-negative.
- No engine handles: snapshots carry read-only data, never ``PactEngine``
  or ``GovernanceEngine`` references (PACT MUST Rule 1).

The existing ``AuditAnchor`` (``kailash.trust.pact.audit.AuditAnchor``) is
re-exported from here as the canonical anchor iteration type — this module
does NOT re-define it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kailash.trust.pact.audit import AuditAnchor

__all__ = [
    "AuditAnchor",
    "ChainVerificationResult",
    "EnvelopeSnapshot",
    "ConsumptionReport",
    "NegativeDrillResult",
]


@dataclass(frozen=True)
class ChainVerificationResult:
    """Result of ``PactEngine.verify_audit_chain(...)``.

    Fail-closed contract (PACT MUST Rule 4):
    - A chain-integrity break populates ``is_valid=False`` with
      ``first_break_reason`` + ``first_break_sequence``. It does NOT raise.
    - ``is_valid=True`` means every verified anchor's hash matched content
      and linked to the prior anchor.

    Attributes:
        is_valid: True iff every anchor in the verified window passed integrity.
        verified_count: Number of anchors examined (post-filter).
        first_break_reason: Human-readable description of the earliest break
            detected in the window, or None when ``is_valid`` is True.
        first_break_sequence: Sequence number of the earliest break detected,
            or None when ``is_valid`` is True.
        tenant_id: The tenant scope this verification ran against, if any.
        chain_id: The underlying ``AuditChain.chain_id``.
        verified_at: When the verification completed.
    """

    is_valid: bool
    verified_count: int
    first_break_reason: str | None = None
    first_break_sequence: int | None = None
    tenant_id: str | None = None
    chain_id: str | None = None
    verified_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "verified_count": self.verified_count,
            "first_break_reason": self.first_break_reason,
            "first_break_sequence": self.first_break_sequence,
            "tenant_id": self.tenant_id,
            "chain_id": self.chain_id,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
        }


@dataclass(frozen=True)
class EnvelopeSnapshot:
    """Point-in-time snapshot of a resolved governance envelope.

    Returned by ``PactEngine.envelope_snapshot(...)``. Carries only the
    serialized clearance + constraints dictionaries — never a live
    ``GovernanceEngine`` reference (PACT MUST Rule 1).

    Attributes:
        envelope_id: Stable identifier of the envelope.
        role_address: D/T/R address the envelope resolved to.
        resolved_at: UTC timestamp of the snapshot.
        clearance: Read-only clearance mapping (confidentiality level,
            compartments, vetting status).
        constraints: Read-only constraint mapping (financial, operational,
            data_access, temporal, communication). Canonically matches
            ``ConstraintEnvelopeConfig`` fields that were non-None at
            snapshot time.
        tenant_id: The tenant scope this snapshot ran against, if any.
    """

    envelope_id: str
    role_address: str
    resolved_at: datetime
    clearance: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    tenant_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "role_address": self.role_address,
            "resolved_at": self.resolved_at.isoformat(),
            "clearance": dict(self.clearance),
            "constraints": dict(self.constraints),
            "tenant_id": self.tenant_id,
        }


@dataclass(frozen=True)
class ConsumptionReport:
    """Aggregated cost-consumption report from ``CostTracker._history``.

    Returned by ``CostTracker.consumption_report(...)``. Totals are in
    microdollars (USD * 1_000_000) for integer math safety — financial
    rollups that round floats accumulate error over thousands of entries.

    Attributes:
        total_microdollars: Sum of consumption in USD microdollars.
        entries: Number of history entries that matched the filter.
        per_envelope: Dict mapping envelope_id -> microdollars. Entries
            with ``envelope_id=None`` are grouped under the empty string.
        per_agent: Dict mapping agent_id / role address -> microdollars.
            Entries with ``agent_id=None`` are grouped under the empty
            string.
        since: Lower bound of the reported time window, if supplied.
        until: Upper bound of the reported time window, if supplied.
    """

    total_microdollars: int
    entries: int
    per_envelope: dict[str, int] = field(default_factory=dict)
    per_agent: dict[str, int] = field(default_factory=dict)
    since: datetime | None = None
    until: datetime | None = None

    @property
    def total_usd(self) -> float:
        """Convenience: total spend in USD (microdollars / 1_000_000)."""
        return self.total_microdollars / 1_000_000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_microdollars": self.total_microdollars,
            "total_usd": self.total_usd,
            "entries": self.entries,
            "per_envelope": dict(self.per_envelope),
            "per_agent": dict(self.per_agent),
            "since": self.since.isoformat() if self.since else None,
            "until": self.until.isoformat() if self.until else None,
        }


@dataclass(frozen=True)
class NegativeDrillResult:
    """Result of a single negative governance drill.

    Returned in a list by ``pact.governance.testing.run_negative_drills(...)``.
    Fail-CLOSED contract: a drill passes ONLY when it raised
    ``GovernanceHeldError`` (i.e. the engine correctly refused the action).
    Any other outcome — drill returns normally, drill raises an unexpected
    exception type — is ``passed=False``.

    Attributes:
        drill_name: Identifier of the drill (e.g. ``"unauthorized_tool_use"``).
        passed: True iff the engine correctly held/blocked the probed action.
        reason: Human-readable description of the outcome. Populated on both
            passed and failed drills to support forensic review.
        exception_type: When the drill raised, the class name of the
            exception. None when the drill returned normally.
    """

    drill_name: str
    passed: bool
    reason: str
    exception_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "drill_name": self.drill_name,
            "passed": self.passed,
            "reason": self.reason,
            "exception_type": self.exception_type,
        }
