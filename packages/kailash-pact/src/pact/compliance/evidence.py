# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SOC 2 evidence-package collector.

Derives SOC 2-aligned compliance evidence from the primitives the SDK already
emits — the hash-chained ``AuditStore`` and the PACT governance audit
vocabulary — for a single tenant over a time window. This is evidence
*tooling*, not an attestation: the deploying organization remains the attesting
party. "Governance by construction" becomes "compliance evidence by
construction."

Load-bearing invariants (each covered by a test):

1. **No fabrication** — evidence is derived ONLY from real emitted records.
   A control with no emitting source primitive reports ``verified=False`` with
   a reason, never a fabricated pass.
2. **Tenant isolation** — every collector is scoped to one ``tenant_id``;
   records belonging to other tenants (or unattributed records) are excluded.
3. **Producer↔consumer contract** — every collector filter is built from the
   real emitted action vocabulary (:mod:`pact.compliance.vocabulary`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

from kailash.trust.audit_store import AuditEvent, AuditFilter
from kailash.trust.pact.exceptions import PactError

from pact.compliance.vocabulary import CONTROL_SPECS, CriterionSpec

logger = logging.getLogger(__name__)

__all__ = [
    "EvidenceCollectionError",
    "EvidenceItem",
    "CriterionEvidence",
    "ControlEvidence",
    "EvidencePackage",
    "EvidenceCollector",
]

# A generous default scan bound. ``AuditFilter`` has no tenant filter and stops
# at ``limit`` matches, so the collector scans the window broadly and applies
# tenant + action selection in-process.
_DEFAULT_SCAN_LIMIT = 1_000_000
_DEFAULT_MAX_ITEMS = 100


class EvidenceCollectionError(PactError):
    """Raised when evidence collection cannot proceed (fail-closed)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise EvidenceCollectionError(
            "period bounds must be datetime instances",
            details={"received_type": type(value).__name__},
        )
    return value.isoformat()


# ---------------------------------------------------------------------------
# Immutable, exportable evidence records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceItem:
    """A single audit record admitted as evidence for a criterion."""

    event_id: str
    timestamp: str
    action: str
    actor: str
    outcome: str
    resource: str

    @classmethod
    def from_event(cls, event: AuditEvent) -> "EvidenceItem":
        return cls(
            event_id=event.event_id,
            timestamp=event.timestamp,
            action=event.action,
            actor=event.actor,
            outcome=event.outcome,
            resource=event.resource,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "actor": self.actor,
            "outcome": self.outcome,
            "resource": self.resource,
        }


@dataclass(frozen=True)
class CriterionEvidence:
    """Evidence for one sub-criterion of a control.

    ``verified`` is ``True`` when the SDK has a measurement mechanism for this
    criterion (its ``source_actions`` are real emitted vocabulary) — even when
    ``evidence_count`` is 0 (an honest "no such events in this window"). It is
    ``False`` only when NO producer emits the criterion's source, in which case
    ``unverified_reason`` explains why.
    """

    criterion: str
    description: str
    verified: bool
    evidence_count: int
    source_actions: tuple[str, ...]
    items: tuple[EvidenceItem, ...]
    unverified_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "description": self.description,
            "verified": self.verified,
            "evidence_count": self.evidence_count,
            "source_actions": list(self.source_actions),
            "items": [item.to_dict() for item in self.items],
            "unverified_reason": self.unverified_reason,
        }


@dataclass(frozen=True)
class ControlEvidence:
    """Evidence for one SOC 2 Common Criteria control."""

    control: str
    title: str
    criteria: tuple[CriterionEvidence, ...]

    @property
    def verified_criteria(self) -> int:
        return sum(1 for c in self.criteria if c.verified)

    @property
    def total_criteria(self) -> int:
        return len(self.criteria)

    def to_dict(self) -> dict[str, Any]:
        return {
            "control": self.control,
            "title": self.title,
            "verified_criteria": self.verified_criteria,
            "total_criteria": self.total_criteria,
            "criteria": [c.to_dict() for c in self.criteria],
        }


@dataclass(frozen=True)
class EvidencePackage:
    """A tenant- and period-scoped, exportable SOC 2 evidence package."""

    tenant_id: str
    period_start: str
    period_end: str
    generated_at: str
    controls: tuple[ControlEvidence, ...]
    chain_verified: Optional[bool] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "generated_at": self.generated_at,
            "chain_verified": self.chain_verified,
            "controls": [c.to_dict() for c in self.controls],
        }


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class EvidenceCollector:
    """Derives SOC 2 evidence packages from an emitted ``AuditStore``.

    Args:
        audit_store: Any object satisfying ``AuditStoreProtocol`` — an
            append-only, hash-chained store of emitted audit events.
        max_items_per_criterion: Cap on the number of raw evidence items
            embedded per criterion (the ``evidence_count`` is always the full
            match count).
        scan_limit: Upper bound on records scanned per window query.
    """

    def __init__(
        self,
        audit_store: Any,
        *,
        max_items_per_criterion: int = _DEFAULT_MAX_ITEMS,
        scan_limit: int = _DEFAULT_SCAN_LIMIT,
    ) -> None:
        if audit_store is None:
            raise EvidenceCollectionError("audit_store is required")
        self._store = audit_store
        self._max_items = max(0, int(max_items_per_criterion))
        self._scan_limit = max(1, int(scan_limit))

    async def collect(
        self,
        *,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime,
        controls: Optional[Sequence[str]] = None,
    ) -> EvidencePackage:
        """Collect a SOC 2 evidence package for one tenant over a window.

        Args:
            tenant_id: The tenant to scope evidence to. Records for other
                tenants (and unattributed records) are excluded (fail-closed).
            period_start: Inclusive lower time bound.
            period_end: Inclusive upper time bound.
            controls: Optional subset of control ids (e.g. ``["CC6"]``); default
                is every implemented control.

        Returns:
            An immutable, exportable :class:`EvidencePackage`.

        Raises:
            EvidenceCollectionError: On invalid tenant / period / unknown
                control (fail-closed).
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise EvidenceCollectionError(
                "tenant_id must be a non-empty string",
                details={"tenant_id": repr(tenant_id)},
            )
        start_iso = _to_iso(period_start)
        end_iso = _to_iso(period_end)
        if period_end < period_start:
            raise EvidenceCollectionError(
                "period_end must not precede period_start",
                details={"period_start": start_iso, "period_end": end_iso},
            )

        selected = self._resolve_controls(controls)
        events = await self._scan_window(tenant_id, period_start, period_end)
        chain_verified = await self._verify_chain()

        built: list[ControlEvidence] = []
        for control_id in selected:
            spec = CONTROL_SPECS[control_id]
            criteria = tuple(
                self._build_criterion(cspec, events) for cspec in spec.criteria
            )
            built.append(
                ControlEvidence(
                    control=spec.control, title=spec.title, criteria=criteria
                )
            )

        return EvidencePackage(
            tenant_id=tenant_id,
            period_start=start_iso,
            period_end=end_iso,
            generated_at=_now_iso(),
            controls=tuple(built),
            chain_verified=chain_verified,
        )

    # -- internals ----------------------------------------------------------

    def _resolve_controls(self, controls: Optional[Sequence[str]]) -> list[str]:
        if controls is None:
            return list(CONTROL_SPECS)
        resolved: list[str] = []
        for control_id in controls:
            if control_id not in CONTROL_SPECS:
                raise EvidenceCollectionError(
                    "unknown control id",
                    details={
                        "control": control_id,
                        "implemented": list(CONTROL_SPECS),
                    },
                )
            resolved.append(control_id)
        return resolved

    async def _scan_window(
        self, tenant_id: str, period_start: datetime, period_end: datetime
    ) -> list[AuditEvent]:
        flt = AuditFilter(since=period_start, until=period_end, limit=self._scan_limit)
        events = await self._store.query(flt)
        # Tenant isolation (fail-closed): only records explicitly attributed to
        # this tenant are admitted. Unattributed (tenant_id=None) and other
        # tenants' records are excluded — cross-tenant leakage is BLOCKED.
        return [
            event for event in events if getattr(event, "tenant_id", None) == tenant_id
        ]

    async def _verify_chain(self) -> Optional[bool]:
        verify = getattr(self._store, "verify_chain", None)
        if verify is None:
            return None
        try:
            return bool(await verify())
        except Exception:  # pragma: no cover - defensive; fail-closed to False
            logger.warning(
                "EvidenceCollector: audit chain verification raised -- "
                "reporting chain_verified=False (fail-closed)",
                exc_info=True,
            )
            return False

    def _build_criterion(
        self, spec: CriterionSpec, events: Iterable[AuditEvent]
    ) -> CriterionEvidence:
        # No emitting producer for this criterion -> honest verified=False.
        if spec.unverifiable_reason is not None:
            return CriterionEvidence(
                criterion=spec.key,
                description=spec.description,
                verified=False,
                evidence_count=0,
                source_actions=spec.source_actions,
                items=(),
                unverified_reason=spec.unverifiable_reason,
            )

        source = set(spec.source_actions)
        matched = [event for event in events if event.action in source]
        items = tuple(
            EvidenceItem.from_event(event) for event in matched[: self._max_items]
        )
        return CriterionEvidence(
            criterion=spec.key,
            description=spec.description,
            verified=True,
            evidence_count=len(matched),
            source_actions=spec.source_actions,
            items=items,
            unverified_reason=None,
        )
