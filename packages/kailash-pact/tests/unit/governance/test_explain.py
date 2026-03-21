# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for governance convenience/explain API functions.

Verifies that describe_address(), explain_envelope(), and explain_access()
produce correct human-readable traces for governance decisions.
"""

from __future__ import annotations

import pytest

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TrustPostureLevel,
)
from pact.governance.access import KnowledgeSharePolicy, PactBridge
from pact.governance.clearance import RoleClearance
from pact.governance.compilation import CompiledOrg
from pact.governance.envelopes import RoleEnvelope
from pact.governance.explain import describe_address, explain_access, explain_envelope
from pact.governance.knowledge import KnowledgeItem
from pact.governance.store import MemoryEnvelopeStore

# Import the university example to build fixtures
from pact.examples.university.org import create_university_org
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def university_org() -> CompiledOrg:
    """Compiled university organization."""
    compiled_org, _org_def = create_university_org()
    return compiled_org


@pytest.fixture
def clearances(university_org: CompiledOrg) -> dict[str, RoleClearance]:
    """Clearance assignments for all university roles."""
    return create_university_clearances(university_org)


@pytest.fixture
def bridges() -> list[PactBridge]:
    """Cross-Functional Bridges for the university."""
    return create_university_bridges()


@pytest.fixture
def ksps() -> list[KnowledgeSharePolicy]:
    """Knowledge Share Policies for the university."""
    return create_university_ksps()


@pytest.fixture
def envelope_store() -> MemoryEnvelopeStore:
    """An envelope store with a sample envelope for CS Chair."""
    store = MemoryEnvelopeStore()

    # Provost defines envelope for Dean of Engineering
    provost_env = RoleEnvelope(
        id="env-dean-eng",
        defining_role_address="D1-R1-D1-R1",
        target_role_address="D1-R1-D1-R1-D1-R1",
        envelope=ConstraintEnvelopeConfig(
            id="provost-dean-eng-envelope",
            description="Provost's envelope for Dean of Engineering",
            financial=FinancialConstraintConfig(max_spend_usd=50000.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "approve", "plan"]
            ),
        ),
    )
    store.save_role_envelope(provost_env)

    # Dean of Engineering defines envelope for CS Chair
    dean_env = RoleEnvelope(
        id="env-cs-chair",
        defining_role_address="D1-R1-D1-R1-D1-R1",
        target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
        envelope=ConstraintEnvelopeConfig(
            id="dean-cs-chair-envelope",
            description="Dean's envelope for CS Chair",
            financial=FinancialConstraintConfig(max_spend_usd=10000.0),
            operational=OperationalConstraintConfig(allowed_actions=["read", "write", "approve"]),
        ),
    )
    store.save_role_envelope(dean_env)

    return store


# ---------------------------------------------------------------------------
# Tests: describe_address
# ---------------------------------------------------------------------------


class TestDescribeAddress:
    """Tests for describe_address() function."""

    def test_describe_address_root(self, university_org: CompiledOrg) -> None:
        """Root address (D1-R1 = President) produces readable description."""
        desc = describe_address("D1-R1", university_org)
        assert "President" in desc

    def test_describe_address_deep(self, university_org: CompiledOrg) -> None:
        """Deep address (CS Chair) shows full ancestry path."""
        # D1-R1-D1-R1-D1-R1-T1-R1 = CS Chair
        desc = describe_address("D1-R1-D1-R1-D1-R1-T1-R1", university_org)
        assert "CS Chair" in desc
        # Should mention containing units
        assert "CS Department" in desc or "School of Engineering" in desc

    def test_describe_address_unknown(self, university_org: CompiledOrg) -> None:
        """Unknown address produces informative result, not an exception."""
        desc = describe_address("D99-R99", university_org)
        # Should indicate the address is not found rather than crashing
        assert "D99-R99" in desc
        assert "not found" in desc.lower() or "unknown" in desc.lower()

    def test_describe_address_includes_department(self, university_org: CompiledOrg) -> None:
        """Description includes the department/team name when applicable."""
        # VP Administration
        desc = describe_address("D1-R1-D2-R1", university_org)
        assert "VP Administration" in desc

    def test_describe_address_standalone_role(self, university_org: CompiledOrg) -> None:
        """CS Faculty Member (non-head role) gets a meaningful description."""
        desc = describe_address("D1-R1-D1-R1-D1-R1-T1-R1-R1", university_org)
        assert "CS Faculty Member" in desc


# ---------------------------------------------------------------------------
# Tests: explain_envelope
# ---------------------------------------------------------------------------


class TestExplainEnvelope:
    """Tests for explain_envelope() function."""

    def test_explain_envelope_with_ancestors(
        self,
        university_org: CompiledOrg,
        envelope_store: MemoryEnvelopeStore,
    ) -> None:
        """CS Chair explanation shows both Provost's and Dean's envelope contributions."""
        explanation = explain_envelope(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            compiled_org=university_org,
            envelope_store=envelope_store,
        )

        # Should mention the CS Chair role
        assert "CS Chair" in explanation or "D1-R1-D1-R1-D1-R1-T1-R1" in explanation

        # Should show financial dimension information
        assert "financial" in explanation.lower() or "spend" in explanation.lower()

        # Should reference envelope contributions from ancestors
        assert "10000" in explanation or "10,000" in explanation

    def test_explain_envelope_no_envelopes(
        self,
        university_org: CompiledOrg,
    ) -> None:
        """Role with no envelopes reports maximally permissive."""
        empty_store = MemoryEnvelopeStore()

        explanation = explain_envelope(
            role_address="D1-R1",  # President - no envelopes defined
            compiled_org=university_org,
            envelope_store=empty_store,
        )

        # Should indicate no envelopes found
        assert (
            "no envelope" in explanation.lower()
            or "none" in explanation.lower()
            or "maximally permissive" in explanation.lower()
            or "unconstrained" in explanation.lower()
        )


# ---------------------------------------------------------------------------
# Tests: explain_access
# ---------------------------------------------------------------------------


class TestExplainAccess:
    """Tests for explain_access() function."""

    def test_explain_access_allowed_same_unit(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        ksps: list[KnowledgeSharePolicy],
        bridges: list[PactBridge],
    ) -> None:
        """Access within same unit shows same-unit path in trace."""
        # CS Chair accessing CS Department data
        cs_dept_data = KnowledgeItem(
            item_id="cs-course-data",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1-R1-D1-R1-D1-R1-T1",
            description="CS course materials",
        )

        trace = explain_access(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            knowledge_item=cs_dept_data,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )

        # Trace should show all 5 steps
        assert "Step 1" in trace or "step 1" in trace.lower()
        assert "Step 2" in trace or "step 2" in trace.lower()
        # Should indicate the result
        assert "ALLOW" in trace.upper() or "PASS" in trace.upper()
        # Should mention same unit or containment
        assert "same" in trace.lower() or "4a" in trace

    def test_explain_access_denied_barrier(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        ksps: list[KnowledgeSharePolicy],
        bridges: list[PactBridge],
    ) -> None:
        """Access denied by information barrier shows denial reason."""
        # CS Faculty trying to access Student Affairs disciplinary records
        # (no structural path, no KSP, no bridge)
        disciplinary_records = KnowledgeItem(
            item_id="disc-case-001",
            classification=ConfidentialityLevel.CONFIDENTIAL,
            owning_unit_address="D1-R1-D3",
            compartments=frozenset({"student-records"}),
            description="Disciplinary records",
        )

        trace = explain_access(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1-R1",
            knowledge_item=disciplinary_records,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )

        # Should indicate denial
        assert "DENY" in trace.upper() or "DENIED" in trace.upper() or "FAIL" in trace.upper()

    def test_explain_access_allowed_via_bridge(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        ksps: list[KnowledgeSharePolicy],
        bridges: list[PactBridge],
    ) -> None:
        """Access via bridge shows bridge path in trace."""
        # Provost accessing Administration budget data via bridge
        admin_budget = KnowledgeItem(
            item_id="admin-budget-2026",
            classification=ConfidentialityLevel.RESTRICTED,
            owning_unit_address="D1-R1-D2",
            description="Admin budget data",
        )

        trace = explain_access(
            role_address="D1-R1-D1-R1",  # Provost
            knowledge_item=admin_budget,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )

        # Should show allowed and mention bridge
        assert "ALLOW" in trace.upper() or "PASS" in trace.upper()
        assert "bridge" in trace.lower()

    def test_explain_access_includes_step_numbers(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        ksps: list[KnowledgeSharePolicy],
        bridges: list[PactBridge],
    ) -> None:
        """Trace always includes numbered steps (1-5)."""
        item = KnowledgeItem(
            item_id="test-item",
            classification=ConfidentialityLevel.PUBLIC,
            owning_unit_address="D1-R1-D1-R1-D1-R1-T1",
            description="Test item",
        )

        trace = explain_access(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            knowledge_item=item,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )

        # Should have step labels
        assert "Step 1" in trace or "step 1" in trace.lower()
        assert "clearance" in trace.lower() or "Clearance" in trace

    def test_explain_access_denied_classification(
        self,
        university_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        ksps: list[KnowledgeSharePolicy],
        bridges: list[PactBridge],
    ) -> None:
        """Access denied at classification check shows clear failure reason."""
        # CS Faculty (RESTRICTED clearance) trying to access SECRET data
        secret_data = KnowledgeItem(
            item_id="secret-research",
            classification=ConfidentialityLevel.SECRET,
            owning_unit_address="D1-R1-D1-R1-D1-R1-T1",
            compartments=frozenset({"human-subjects"}),
            description="Secret research data",
        )

        trace = explain_access(
            role_address="D1-R1-D1-R1-D1-R1-T1-R1-R1",  # CS Faculty (RESTRICTED)
            knowledge_item=secret_data,
            posture=TrustPostureLevel.DELEGATED,
            compiled_org=university_org,
            clearances=clearances,
            ksps=ksps,
            bridges=bridges,
        )

        # Should show step 2 failure (classification)
        assert "Step 2" in trace or "step 2" in trace.lower() or "classification" in trace.lower()
        assert "DENY" in trace.upper() or "FAIL" in trace.upper()
