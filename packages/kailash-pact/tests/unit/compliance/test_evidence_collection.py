# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SOC 2 evidence-collection tests (issue #1711).

Behavioral tests against a REAL ``InMemoryAuditStore`` populated with REAL
``AuditEvent`` records (no mocking). Covers the three load-bearing invariants:

1. No fabrication  -> unmeasured controls report ``verified=False``.
2. Tenant isolation -> cross-tenant leakage is blocked.
3. Producer<->consumer contract -> every filter matches a real emitted action.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from kailash.trust.audit_store import AuditEventType, InMemoryAuditStore
from kailash.trust.pact.audit import PactAuditAction

from pact.compliance import (
    CONTROL_SPECS,
    EMITTED_ACTION_VOCABULARY,
    EvidenceCollectionError,
    EvidenceCollector,
    EvidencePackage,
)

# Window used by every scenario.
_T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
_WINDOW_START = _T0 - timedelta(days=1)
_WINDOW_END = _T0 + timedelta(days=1)


async def _append(
    store, *, tenant_id, action, actor="agent-1", outcome="success", when=None
):
    """Append one tenant-scoped, correctly hash-chained event.

    ``tenant_id`` is not part of the audit-event hash pre-image, so we build a
    correctly-linked event via ``create_event`` and stamp the tenant via a
    frozen-dataclass replace without breaking chain integrity.
    """
    ts = (when or _T0).isoformat()
    event = store.create_event(
        actor=actor, action=action, resource="res", outcome=outcome, timestamp=ts
    )
    event = dataclasses.replace(event, tenant_id=tenant_id)
    await store.append(event)
    return event


def _find_criterion(package: EvidencePackage, control: str, criterion: str):
    ctrl = next(c for c in package.controls if c.control == control)
    return next(c for c in ctrl.criteria if c.criterion == criterion)


# ---------------------------------------------------------------------------
# Invariant 3 — producer<->consumer contract (dead-collector guard)
# ---------------------------------------------------------------------------


def test_emitted_vocabulary_is_union_of_both_producer_enums():
    expected = frozenset(
        [m.value for m in PactAuditAction] + [m.value for m in AuditEventType]
    )
    assert EMITTED_ACTION_VOCABULARY == expected


def test_every_collector_filter_matches_a_real_emitted_action():
    """No collector filter may name an action no producer emits."""
    for control_id, spec in CONTROL_SPECS.items():
        for criterion in spec.criteria:
            for action in criterion.source_actions:
                assert action in EMITTED_ACTION_VOCABULARY, (
                    f"{control_id}.{criterion.key} filters on '{action}' which no "
                    f"producer emits (dead collector)"
                )


def test_measurable_criteria_have_sources_unmeasurable_have_reason():
    """A criterion either has real sources OR a stated unverifiable reason."""
    for spec in CONTROL_SPECS.values():
        for criterion in spec.criteria:
            if criterion.kind != "records":
                # chain_integrity is measured from the hash chain, not an
                # action filter, so it legitimately carries no source_actions.
                continue
            if criterion.unverifiable_reason is None:
                assert criterion.source_actions, criterion.key
            else:
                assert not criterion.source_actions, criterion.key


# ---------------------------------------------------------------------------
# Invariant 1 — no fabrication (unmeasured -> verified=False, never a fake pass)
# ---------------------------------------------------------------------------


def test_unmeasured_controls_report_verified_false_with_reason():
    async def scenario():
        store = InMemoryAuditStore()
        # Populate real access + change records so measurable criteria pass.
        await _append(
            store, tenant_id="acme", action=PactAuditAction.CLEARANCE_GRANTED.value
        )
        await _append(
            store, tenant_id="acme", action=PactAuditAction.ENVELOPE_MODIFIED.value
        )
        collector = EvidenceCollector(store)
        return await collector.collect(
            tenant_id="acme", period_start=_WINDOW_START, period_end=_WINDOW_END
        )

    package = asyncio.run(scenario())

    mfa = _find_criterion(package, "CC6", "mfa_state")
    assert mfa.verified is False
    assert mfa.evidence_count == 0
    assert mfa.items == ()
    assert mfa.unverified_reason and "MFA" in mfa.unverified_reason

    deploy = _find_criterion(package, "CC8", "deployment_records")
    assert deploy.verified is False
    assert deploy.evidence_count == 0
    assert deploy.unverified_reason and "deployment" in deploy.unverified_reason.lower()


def test_measurable_criterion_with_zero_events_is_verified_true_not_false():
    """A measurable control with no events is honest 'measured, count 0',
    distinct from an unmeasurable 'verified=False'."""

    async def scenario():
        store = InMemoryAuditStore()  # empty store
        collector = EvidenceCollector(store)
        return await collector.collect(
            tenant_id="acme", period_start=_WINDOW_START, period_end=_WINDOW_END
        )

    package = asyncio.run(scenario())
    grants = _find_criterion(package, "CC6", "logical_access_grants")
    assert grants.verified is True  # mechanism exists
    assert grants.evidence_count == 0  # but no events this period


# ---------------------------------------------------------------------------
# Invariant 2 — tenant isolation (no cross-tenant leakage)
# ---------------------------------------------------------------------------


def test_tenant_isolation_no_cross_tenant_leakage():
    async def scenario():
        store = InMemoryAuditStore()
        await _append(
            store,
            tenant_id="acme",
            action=PactAuditAction.CLEARANCE_GRANTED.value,
            actor="acme-user",
        )
        await _append(
            store,
            tenant_id="acme",
            action=PactAuditAction.CLEARANCE_GRANTED.value,
            actor="acme-user-2",
        )
        await _append(
            store,
            tenant_id="globex",
            action=PactAuditAction.CLEARANCE_GRANTED.value,
            actor="globex-user",
        )
        # An unattributed record (no tenant) must never appear in any package.
        unattributed = store.create_event(
            actor="ghost",
            action=PactAuditAction.CLEARANCE_GRANTED.value,
            timestamp=_T0.isoformat(),
        )
        await store.append(unattributed)
        collector = EvidenceCollector(store)
        acme = await collector.collect(
            tenant_id="acme", period_start=_WINDOW_START, period_end=_WINDOW_END
        )
        globex = await collector.collect(
            tenant_id="globex", period_start=_WINDOW_START, period_end=_WINDOW_END
        )
        return acme, globex

    acme, globex = asyncio.run(scenario())

    acme_grants = _find_criterion(acme, "CC6", "logical_access_grants")
    assert acme_grants.evidence_count == 2
    actors = {item.actor for item in acme_grants.items}
    assert actors == {"acme-user", "acme-user-2"}
    assert "globex-user" not in actors
    assert "ghost" not in actors  # unattributed excluded (fail-closed)

    globex_grants = _find_criterion(globex, "CC6", "logical_access_grants")
    assert globex_grants.evidence_count == 1
    assert {item.actor for item in globex_grants.items} == {"globex-user"}


# ---------------------------------------------------------------------------
# Functional coverage
# ---------------------------------------------------------------------------


def test_cc6_and_cc8_evidence_collected_and_exportable():
    async def scenario():
        store = InMemoryAuditStore()
        await _append(
            store, tenant_id="acme", action=PactAuditAction.CLEARANCE_GRANTED.value
        )
        await _append(
            store, tenant_id="acme", action=AuditEventType.ACCESS_GRANTED.value
        )
        await _append(
            store, tenant_id="acme", action=PactAuditAction.CLEARANCE_REVOKED.value
        )
        await _append(
            store,
            tenant_id="acme",
            action=PactAuditAction.BARRIER_ENFORCED.value,
            outcome="denied",
        )
        await _append(
            store, tenant_id="acme", action=PactAuditAction.ENVELOPE_CREATED.value
        )
        await _append(
            store, tenant_id="acme", action=PactAuditAction.VACANCY_DESIGNATED.value
        )
        collector = EvidenceCollector(store)
        return await collector.collect(
            tenant_id="acme", period_start=_WINDOW_START, period_end=_WINDOW_END
        )

    package = asyncio.run(scenario())

    assert {c.control for c in package.controls} == {"CC6", "CC7", "CC8"}
    assert package.chain_verified is True

    assert _find_criterion(package, "CC6", "logical_access_grants").evidence_count == 2
    assert _find_criterion(package, "CC6", "access_revocations").evidence_count == 1
    assert _find_criterion(package, "CC6", "access_enforcement").evidence_count == 1
    assert (
        _find_criterion(package, "CC8", "governance_config_changes").evidence_count == 1
    )
    assert (
        _find_criterion(
            package, "CC8", "authorization_structure_changes"
        ).evidence_count
        == 1
    )

    # Exportable to a plain dict.
    exported = package.to_dict()
    assert exported["tenant_id"] == "acme"
    assert exported["chain_verified"] is True
    assert isinstance(exported["controls"], list)
    cc6 = next(c for c in exported["controls"] if c["control"] == "CC6")
    assert any(
        cr["criterion"] == "mfa_state" and cr["verified"] is False
        for cr in cc6["criteria"]
    )


def test_control_subset_selection():
    async def scenario():
        store = InMemoryAuditStore()
        collector = EvidenceCollector(store)
        return await collector.collect(
            tenant_id="acme",
            period_start=_WINDOW_START,
            period_end=_WINDOW_END,
            controls=["CC6"],
        )

    package = asyncio.run(scenario())
    assert {c.control for c in package.controls} == {"CC6"}


def test_period_window_excludes_out_of_range_events():
    async def scenario():
        store = InMemoryAuditStore()
        await _append(
            store,
            tenant_id="acme",
            action=PactAuditAction.CLEARANCE_GRANTED.value,
            when=_T0,
        )
        # Outside the window (2 days after T0 > window_end at T0+1d).
        await _append(
            store,
            tenant_id="acme",
            action=PactAuditAction.CLEARANCE_GRANTED.value,
            when=_T0 + timedelta(days=2),
        )
        collector = EvidenceCollector(store)
        return await collector.collect(
            tenant_id="acme", period_start=_WINDOW_START, period_end=_WINDOW_END
        )

    package = asyncio.run(scenario())
    assert _find_criterion(package, "CC6", "logical_access_grants").evidence_count == 1


# ---------------------------------------------------------------------------
# Fail-closed validation
# ---------------------------------------------------------------------------


def test_empty_tenant_id_fails_closed():
    async def scenario():
        collector = EvidenceCollector(InMemoryAuditStore())
        await collector.collect(
            tenant_id="  ", period_start=_WINDOW_START, period_end=_WINDOW_END
        )

    with pytest.raises(EvidenceCollectionError):
        asyncio.run(scenario())


def test_inverted_period_fails_closed():
    async def scenario():
        collector = EvidenceCollector(InMemoryAuditStore())
        await collector.collect(
            tenant_id="acme", period_start=_WINDOW_END, period_end=_WINDOW_START
        )

    with pytest.raises(EvidenceCollectionError):
        asyncio.run(scenario())


def test_unknown_control_fails_closed():
    async def scenario():
        collector = EvidenceCollector(InMemoryAuditStore())
        await collector.collect(
            tenant_id="acme",
            period_start=_WINDOW_START,
            period_end=_WINDOW_END,
            controls=["CC99"],
        )

    with pytest.raises(EvidenceCollectionError):
        asyncio.run(scenario())


def test_none_store_fails_closed():
    with pytest.raises(EvidenceCollectionError):
        EvidenceCollector(None)


# ---------------------------------------------------------------------------
# CC7 — system operations (chain integrity + security/operational events)
# ---------------------------------------------------------------------------


def test_cc7_chain_integrity_and_operational_events():
    async def scenario():
        store = InMemoryAuditStore()
        await _append(
            store,
            tenant_id="acme",
            action=AuditEventType.CONSTRAINT_VIOLATED.value,
            outcome="denied",
        )
        await _append(
            store,
            tenant_id="acme",
            action=PactAuditAction.BARRIER_ENFORCED.value,
            outcome="denied",
        )
        await _append(
            store, tenant_id="acme", action=PactAuditAction.PLAN_SUSPENDED.value
        )
        collector = EvidenceCollector(store)
        return await collector.collect(
            tenant_id="acme",
            period_start=_WINDOW_START,
            period_end=_WINDOW_END,
            controls=["CC7"],
        )

    package = asyncio.run(scenario())

    chain = _find_criterion(package, "CC7", "audit_chain_integrity")
    assert chain.verified is True
    assert chain.evidence_count == 1
    assert chain.items[0].outcome == "success"  # intact chain

    security = _find_criterion(package, "CC7", "security_events")
    assert security.evidence_count == 2  # constraint_violated + barrier_enforced

    suspensions = _find_criterion(package, "CC7", "operational_suspensions")
    assert suspensions.evidence_count == 1

    # External monitoring/alerting is honestly unmeasured.
    monitoring = _find_criterion(package, "CC7", "monitoring_alerts")
    assert monitoring.verified is False
    assert monitoring.unverified_reason


def test_cc7_chain_integrity_unmeasurable_without_verify_chain():
    """A store that does not expose chain verification -> verified=False, not a
    fabricated pass."""

    class _QueryOnlyStore:
        """A real audit store variant exposing only query (no verify_chain)."""

        def __init__(self, inner):
            self._inner = inner

        async def query(self, flt):
            return await self._inner.query(flt)

    async def scenario():
        inner = InMemoryAuditStore()
        await _append(
            inner, tenant_id="acme", action=PactAuditAction.PLAN_SUSPENDED.value
        )
        collector = EvidenceCollector(_QueryOnlyStore(inner))
        return await collector.collect(
            tenant_id="acme",
            period_start=_WINDOW_START,
            period_end=_WINDOW_END,
            controls=["CC7"],
        )

    package = asyncio.run(scenario())
    assert package.chain_verified is None
    chain = _find_criterion(package, "CC7", "audit_chain_integrity")
    assert chain.verified is False
    assert chain.evidence_count == 0
    assert chain.unverified_reason
    # Record-based criteria still work without chain verification.
    assert (
        _find_criterion(package, "CC7", "operational_suspensions").evidence_count == 1
    )
