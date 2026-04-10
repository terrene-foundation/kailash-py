# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for KnowledgeFilter pre-retrieval lifecycle gate.

Covers:
- Filter denies -> access denied before data retrieval (step_failed=0)
- Filter narrows scope -> narrowed query used, access check still runs
- No filter -> backward compat (existing behavior unchanged)
- Filter decision logged in audit chain
- Filter error -> fail-closed (DENIED)
- Filter returns non-FilterDecision -> fail-closed (DENIED)
- KnowledgeQuery and FilterDecision serialization
- KnowledgeFilter Protocol runtime checkability
"""

from __future__ import annotations

from typing import Any

import pytest
from kailash.trust.pact.access import AccessDecision
from kailash.trust.pact.audit import AuditChain
from kailash.trust.pact.clearance import RoleClearance
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.config import ConfidentialityLevel, TrustPostureLevel
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.knowledge import (
    FilterDecision,
    KnowledgeFilter,
    KnowledgeItem,
    KnowledgeQuery,
)
from kailash.trust.pact.store import MemoryClearanceStore
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org

# ---------------------------------------------------------------------------
# Test filter implementations (Tier 1 -- mocking allowed in unit tests)
# ---------------------------------------------------------------------------


class DenyAllFilter:
    """A filter that denies all queries."""

    def filter_before_retrieval(
        self,
        role_address: str,
        query: KnowledgeQuery,
        envelope: Any,
    ) -> FilterDecision:
        return FilterDecision(
            allowed=False,
            reason="Denied by DenyAllFilter",
        )


class AllowAllFilter:
    """A filter that allows all queries."""

    def filter_before_retrieval(
        self,
        role_address: str,
        query: KnowledgeQuery,
        envelope: Any,
    ) -> FilterDecision:
        return FilterDecision(
            allowed=True,
            reason="Allowed by AllowAllFilter",
        )


class NarrowingFilter:
    """A filter that narrows the query scope to PUBLIC only."""

    def filter_before_retrieval(
        self,
        role_address: str,
        query: KnowledgeQuery,
        envelope: Any,
    ) -> FilterDecision:
        narrowed = KnowledgeQuery(
            item_ids=query.item_ids,
            classifications=frozenset({"PUBLIC"}),
            owning_units=query.owning_units,
            description=f"Narrowed: {query.description}",
        )
        return FilterDecision(
            allowed=True,
            filtered_scope=narrowed,
            reason="Narrowed to PUBLIC classifications only",
        )


class ExplodingFilter:
    """A filter that raises an exception."""

    def filter_before_retrieval(
        self,
        role_address: str,
        query: KnowledgeQuery,
        envelope: Any,
    ) -> FilterDecision:
        raise RuntimeError("Filter implementation error")


class BadReturnFilter:
    """A filter that returns the wrong type."""

    def filter_before_retrieval(
        self,
        role_address: str,
        query: KnowledgeQuery,
        envelope: Any,
    ) -> Any:
        return {"allowed": True}  # type: ignore[return-value] -- deliberately wrong


class RecordingFilter:
    """A filter that records calls for assertion."""

    def __init__(self, decision: FilterDecision) -> None:
        self.calls: list[tuple[str, KnowledgeQuery, Any]] = []
        self._decision = decision

    def filter_before_retrieval(
        self,
        role_address: str,
        query: KnowledgeQuery,
        envelope: Any,
    ) -> FilterDecision:
        self.calls.append((role_address, query, envelope))
        return self._decision


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def compiled_org() -> CompiledOrg:
    """Compiled university org."""
    compiled, _ = create_university_org()
    return compiled


@pytest.fixture
def org_definition() -> Any:
    """OrgDefinition for the university."""
    _, org_def = create_university_org()
    return org_def


@pytest.fixture
def clearances(compiled_org: CompiledOrg) -> dict[str, RoleClearance]:
    """Clearance assignments for all university roles."""
    return create_university_clearances(compiled_org)


@pytest.fixture
def public_item() -> KnowledgeItem:
    """A PUBLIC knowledge item owned by the top department."""
    return KnowledgeItem(
        item_id="public-report",
        classification=ConfidentialityLevel.PUBLIC,
        owning_unit_address="D1",
        description="Annual public report",
    )


@pytest.fixture
def confidential_item() -> KnowledgeItem:
    """A CONFIDENTIAL knowledge item."""
    return KnowledgeItem(
        item_id="budget-q1",
        classification=ConfidentialityLevel.CONFIDENTIAL,
        owning_unit_address="D1",
        description="Q1 budget data",
    )


def _make_engine(
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],
    *,
    knowledge_filter: KnowledgeFilter | None = None,
    audit_chain: AuditChain | None = None,
) -> GovernanceEngine:
    """Build an engine with populated clearance store."""
    clearance_store = MemoryClearanceStore()
    for clr in clearances.values():
        clearance_store.grant_clearance(clr)

    return GovernanceEngine(
        compiled_org,
        clearance_store=clearance_store,
        knowledge_filter=knowledge_filter,
        audit_chain=audit_chain,
    )


# ---------------------------------------------------------------------------
# KnowledgeQuery tests
# ---------------------------------------------------------------------------


class TestKnowledgeQuery:
    """KnowledgeQuery frozen dataclass behavior and serialization."""

    def test_default_construction(self) -> None:
        q = KnowledgeQuery()
        assert q.item_ids is None
        assert q.classifications is None
        assert q.owning_units is None
        assert q.description == ""

    def test_full_construction(self) -> None:
        q = KnowledgeQuery(
            item_ids=frozenset({"a", "b"}),
            classifications=frozenset({"PUBLIC", "RESTRICTED"}),
            owning_units=frozenset({"D1", "D1-R1-D2"}),
            description="Test query",
        )
        assert q.item_ids == frozenset({"a", "b"})
        assert q.classifications == frozenset({"PUBLIC", "RESTRICTED"})
        assert q.owning_units == frozenset({"D1", "D1-R1-D2"})
        assert q.description == "Test query"

    def test_frozen_immutability(self) -> None:
        q = KnowledgeQuery()
        with pytest.raises(AttributeError):
            q.description = "modified"  # type: ignore[misc]

    def test_to_dict_roundtrip(self) -> None:
        q = KnowledgeQuery(
            item_ids=frozenset({"x", "y"}),
            classifications=frozenset({"SECRET"}),
            owning_units=frozenset({"D1-R1-T1"}),
            description="Roundtrip test",
        )
        d = q.to_dict()
        assert isinstance(d["item_ids"], list)
        q2 = KnowledgeQuery.from_dict(d)
        assert q2.item_ids == q.item_ids
        assert q2.classifications == q.classifications
        assert q2.owning_units == q.owning_units
        assert q2.description == q.description

    def test_to_dict_none_fields(self) -> None:
        q = KnowledgeQuery()
        d = q.to_dict()
        assert d["item_ids"] is None
        assert d["classifications"] is None
        assert d["owning_units"] is None

    def test_from_dict_none_fields(self) -> None:
        d = {"item_ids": None, "classifications": None, "owning_units": None}
        q = KnowledgeQuery.from_dict(d)
        assert q.item_ids is None
        assert q.classifications is None
        assert q.owning_units is None


# ---------------------------------------------------------------------------
# FilterDecision tests
# ---------------------------------------------------------------------------


class TestFilterDecision:
    """FilterDecision frozen dataclass behavior and serialization."""

    def test_deny_decision(self) -> None:
        d = FilterDecision(allowed=False, reason="Denied")
        assert not d.allowed
        assert d.reason == "Denied"
        assert d.filtered_scope is None
        assert d.audit_anchor_id  # auto-generated UUID

    def test_allow_decision(self) -> None:
        d = FilterDecision(allowed=True, reason="OK")
        assert d.allowed

    def test_narrowed_decision(self) -> None:
        narrowed = KnowledgeQuery(classifications=frozenset({"PUBLIC"}))
        d = FilterDecision(
            allowed=True,
            filtered_scope=narrowed,
            reason="Narrowed",
        )
        assert d.allowed
        assert d.filtered_scope is not None
        assert d.filtered_scope.classifications == frozenset({"PUBLIC"})

    def test_frozen_immutability(self) -> None:
        d = FilterDecision(allowed=True)
        with pytest.raises(AttributeError):
            d.allowed = False  # type: ignore[misc]

    def test_to_dict_roundtrip(self) -> None:
        narrowed = KnowledgeQuery(item_ids=frozenset({"z"}))
        d = FilterDecision(
            allowed=True,
            filtered_scope=narrowed,
            reason="Test",
            audit_anchor_id="test-id-123",
        )
        serialized = d.to_dict()
        d2 = FilterDecision.from_dict(serialized)
        assert d2.allowed == d.allowed
        assert d2.reason == d.reason
        assert d2.audit_anchor_id == d.audit_anchor_id
        assert d2.filtered_scope is not None
        assert d2.filtered_scope.item_ids == frozenset({"z"})

    def test_to_dict_no_scope(self) -> None:
        d = FilterDecision(allowed=False, reason="No")
        serialized = d.to_dict()
        assert serialized["filtered_scope"] is None
        d2 = FilterDecision.from_dict(serialized)
        assert d2.filtered_scope is None


# ---------------------------------------------------------------------------
# KnowledgeFilter Protocol tests
# ---------------------------------------------------------------------------


class TestKnowledgeFilterProtocol:
    """KnowledgeFilter runtime_checkable Protocol."""

    def test_deny_all_is_knowledge_filter(self) -> None:
        assert isinstance(DenyAllFilter(), KnowledgeFilter)

    def test_allow_all_is_knowledge_filter(self) -> None:
        assert isinstance(AllowAllFilter(), KnowledgeFilter)

    def test_narrowing_is_knowledge_filter(self) -> None:
        assert isinstance(NarrowingFilter(), KnowledgeFilter)

    def test_exploding_is_knowledge_filter(self) -> None:
        assert isinstance(ExplodingFilter(), KnowledgeFilter)

    def test_non_conforming_is_not_knowledge_filter(self) -> None:
        """An object without filter_before_retrieval is not a KnowledgeFilter."""

        class NotAFilter:
            pass

        assert not isinstance(NotAFilter(), KnowledgeFilter)


# ---------------------------------------------------------------------------
# Engine integration: filter denies -> access denied before data retrieval
# ---------------------------------------------------------------------------


class TestFilterDeniesAccess:
    """When the filter denies, access is denied at step 0 (pre-filter)."""

    def test_filter_deny_returns_access_denied(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """Filter denies -> AccessDecision(allowed=False, step_failed=0)."""
        engine = _make_engine(
            compiled_org, clearances, knowledge_filter=DenyAllFilter()
        )
        # Use first available role address
        role_address = next(iter(clearances))

        decision = engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        assert not decision.allowed
        assert decision.step_failed == 0
        assert "Pre-retrieval filter denied" in decision.reason
        assert "Denied by DenyAllFilter" in decision.reason

    def test_filter_deny_includes_audit_details(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """Filter deny decision includes filter_decision in audit_details."""
        engine = _make_engine(
            compiled_org, clearances, knowledge_filter=DenyAllFilter()
        )
        role_address = next(iter(clearances))

        decision = engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        assert decision.audit_details.get("step") == "pre_filter"
        assert "filter_decision" in decision.audit_details
        fd = decision.audit_details["filter_decision"]
        assert fd["allowed"] is False


# ---------------------------------------------------------------------------
# Engine integration: filter narrows scope
# ---------------------------------------------------------------------------


class TestFilterNarrowsScope:
    """When the filter narrows scope, the narrowed query is used."""

    def test_narrowing_filter_still_runs_access_check(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """Narrowing filter allows -> 5-step access check still runs."""
        engine = _make_engine(
            compiled_org, clearances, knowledge_filter=NarrowingFilter()
        )
        role_address = next(iter(clearances))

        decision = engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        # The 5-step algorithm still runs after the filter allows.
        # The decision depends on the 5-step algorithm, not the filter.
        # For the university example, the first role should have access
        # to a PUBLIC item owned by D1.
        assert isinstance(decision, AccessDecision)
        # step_failed should NOT be 0 (pre-filter) since filter allowed
        if not decision.allowed:
            assert decision.step_failed != 0

    def test_narrowing_filter_receives_correct_query(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """Recording filter captures the query built from the knowledge item."""
        recording = RecordingFilter(FilterDecision(allowed=True, reason="Recorded"))
        engine = _make_engine(compiled_org, clearances, knowledge_filter=recording)
        role_address = next(iter(clearances))

        engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        assert len(recording.calls) == 1
        call_role, call_query, call_envelope = recording.calls[0]
        assert call_role == role_address
        # Default query built from knowledge item
        assert call_query.item_ids == frozenset({public_item.item_id})
        assert public_item.classification.value in call_query.classifications

    def test_explicit_query_passed_to_filter(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """When an explicit query is provided, the filter receives it."""
        recording = RecordingFilter(FilterDecision(allowed=True, reason="Recorded"))
        engine = _make_engine(compiled_org, clearances, knowledge_filter=recording)
        role_address = next(iter(clearances))

        explicit_query = KnowledgeQuery(
            item_ids=frozenset({"custom-id"}),
            description="Explicit query",
        )
        engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
            query=explicit_query,
        )

        assert len(recording.calls) == 1
        _, call_query, _ = recording.calls[0]
        assert call_query is explicit_query
        assert call_query.item_ids == frozenset({"custom-id"})


# ---------------------------------------------------------------------------
# Engine integration: no filter -> backward compat
# ---------------------------------------------------------------------------


class TestNoFilterBackwardCompat:
    """When no filter is configured, existing behavior is unchanged."""

    def test_no_filter_check_access_works(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """Engine without filter runs 5-step algorithm directly."""
        engine = _make_engine(compiled_org, clearances, knowledge_filter=None)
        role_address = next(iter(clearances))

        decision = engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        assert isinstance(decision, AccessDecision)
        # step_failed should never be 0 (pre-filter) since there is no filter
        if not decision.allowed:
            assert decision.step_failed != 0

    def test_query_param_ignored_without_filter(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """The query parameter is accepted but ignored when no filter exists."""
        engine = _make_engine(compiled_org, clearances, knowledge_filter=None)
        role_address = next(iter(clearances))

        explicit_query = KnowledgeQuery(
            item_ids=frozenset({"custom-id"}),
            description="Should be ignored",
        )
        decision = engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
            query=explicit_query,
        )

        assert isinstance(decision, AccessDecision)


# ---------------------------------------------------------------------------
# Engine integration: filter decision logged in audit chain
# ---------------------------------------------------------------------------


class TestFilterAuditLogging:
    """Filter decisions are recorded in the audit chain."""

    def test_filter_deny_emits_audit(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """A denied filter decision emits a 'knowledge_filter_denied' audit entry."""
        audit = AuditChain(chain_id="test-filter-deny")
        engine = _make_engine(
            compiled_org,
            clearances,
            knowledge_filter=DenyAllFilter(),
            audit_chain=audit,
        )
        role_address = next(iter(clearances))

        engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        # Check that audit has a knowledge_filter_denied anchor
        filter_anchors = [
            a for a in audit.anchors if a.action == "knowledge_filter_denied"
        ]
        assert len(filter_anchors) >= 1
        anchor = filter_anchors[0]
        assert anchor.metadata["role_address"] == role_address
        assert anchor.metadata["item_id"] == public_item.item_id
        assert anchor.metadata["barrier_enforced"] is True

    def test_filter_allow_emits_audit(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """An allowed filter decision emits a 'knowledge_filter_allowed' audit entry."""
        audit = AuditChain(chain_id="test-filter-allow")
        engine = _make_engine(
            compiled_org,
            clearances,
            knowledge_filter=AllowAllFilter(),
            audit_chain=audit,
        )
        role_address = next(iter(clearances))

        engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        filter_anchors = [
            a for a in audit.anchors if a.action == "knowledge_filter_allowed"
        ]
        assert len(filter_anchors) >= 1
        anchor = filter_anchors[0]
        assert anchor.metadata["role_address"] == role_address
        assert anchor.metadata["narrowed"] is False

    def test_narrowing_filter_audit_shows_narrowed(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """A narrowing filter marks narrowed=True in the audit entry."""
        audit = AuditChain(chain_id="test-filter-narrow")
        engine = _make_engine(
            compiled_org,
            clearances,
            knowledge_filter=NarrowingFilter(),
            audit_chain=audit,
        )
        role_address = next(iter(clearances))

        engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        filter_anchors = [
            a for a in audit.anchors if a.action == "knowledge_filter_allowed"
        ]
        assert len(filter_anchors) >= 1
        assert filter_anchors[0].metadata["narrowed"] is True


# ---------------------------------------------------------------------------
# Engine integration: filter error -> fail-closed (DENIED)
# ---------------------------------------------------------------------------


class TestFilterErrorFailClosed:
    """Filter errors are caught and result in DENY (fail-closed)."""

    def test_filter_exception_returns_denied(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """Filter raising an exception -> AccessDecision(allowed=False)."""
        engine = _make_engine(
            compiled_org, clearances, knowledge_filter=ExplodingFilter()
        )
        role_address = next(iter(clearances))

        decision = engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        assert not decision.allowed
        assert decision.step_failed == 0
        assert "fail-closed" in decision.reason.lower()

    def test_filter_bad_return_type_returns_denied(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """Filter returning wrong type -> AccessDecision(allowed=False)."""
        engine = _make_engine(
            compiled_org, clearances, knowledge_filter=BadReturnFilter()
        )
        role_address = next(iter(clearances))

        decision = engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        assert not decision.allowed
        assert decision.step_failed == 0
        assert (
            "invalid type" in decision.reason.lower()
            or "fail-closed" in decision.reason.lower()
        )

    def test_filter_exception_audited(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """Filter exception -> still emits knowledge_filter_denied audit."""
        audit = AuditChain(chain_id="test-filter-error")
        engine = _make_engine(
            compiled_org,
            clearances,
            knowledge_filter=ExplodingFilter(),
            audit_chain=audit,
        )
        role_address = next(iter(clearances))

        engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        filter_anchors = [
            a for a in audit.anchors if a.action == "knowledge_filter_denied"
        ]
        assert len(filter_anchors) >= 1


# ---------------------------------------------------------------------------
# Engine integration: filter receives envelope snapshot
# ---------------------------------------------------------------------------


class TestFilterReceivesEnvelope:
    """The filter receives the role's EffectiveEnvelopeSnapshot."""

    def test_filter_receives_envelope_snapshot(
        self,
        compiled_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        public_item: KnowledgeItem,
    ) -> None:
        """The envelope passed to the filter has the expected shape."""
        recording = RecordingFilter(FilterDecision(allowed=True, reason="Recorded"))
        engine = _make_engine(compiled_org, clearances, knowledge_filter=recording)
        role_address = next(iter(clearances))

        engine.check_access(
            role_address,
            public_item,
            TrustPostureLevel.DELEGATING,
        )

        assert len(recording.calls) == 1
        _, _, envelope = recording.calls[0]
        # EffectiveEnvelopeSnapshot has .envelope and .version_hash
        assert hasattr(envelope, "envelope")
        assert hasattr(envelope, "version_hash")
