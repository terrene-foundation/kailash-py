# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Flagship scenario test — Financial Services information barrier enforcement.

Implements PACT thesis Section 7.1: advisory analyst blocked from trading data.

Organization Structure:
  R1 Board of Directors (external)
    D1 Executive Office
      D1-R1 CEO
        D1-R1-D1 Compliance Division
          D1-R1-D1-R1 CCO
            D1-R1-D1-R1-T1 AML/CFT Team
              D1-R1-D1-R1-T1-R1 AML Officer
        D1-R1-D2 Advisory Division
          D1-R1-D2-R1 Head of Advisory
            D1-R1-D2-R1-T1 Client Advisory Team
              D1-R1-D2-R1-T1-R1 Senior Advisor
        D1-R1-D3 Trading Division
          D1-R1-D3-R1 Head of Trading
            D1-R1-D3-R1-T1 Equities Desk
              D1-R1-D3-R1-T1-R1 Senior Trader

Key governance setup:
- CCO has standing bridges to BOTH Advisory and Trading (compliance monitoring)
- AML Officer has SECRET clearance for 'aml-investigations' compartment
- Head of Trading has CONFIDENTIAL clearance (NO investigation access)
- NO KSP between Advisory and Trading — this IS the information barrier

Seven test scenarios verify the access enforcement algorithm produces the
correct allow/deny decisions for the flagship demo.
"""

from __future__ import annotations

import pytest

from pact.build.config.schema import (
    ConfidentialityLevel,
    DepartmentConfig,
    TeamConfig,
    TrustPostureLevel,
)
from pact.build.org.builder import OrgDefinition
from pact.governance.access import (
    KnowledgeSharePolicy,
    PactBridge,
    can_access,
)
from pact.governance.clearance import RoleClearance
from pact.governance.compilation import CompiledOrg, RoleDefinition, compile_org
from pact.governance.knowledge import KnowledgeItem


# ---------------------------------------------------------------------------
# Fixture: Full financial services org
# ---------------------------------------------------------------------------


@pytest.fixture
def finserv_org() -> CompiledOrg:
    """Financial services org from PACT thesis Section 7.1."""
    roles = [
        RoleDefinition(
            role_id="r-bod",
            name="Board of Directors",
            reports_to_role_id=None,
            is_external=True,
        ),
        RoleDefinition(
            role_id="r-ceo",
            name="CEO",
            reports_to_role_id="r-bod",
            is_primary_for_unit="d-exec",
        ),
        RoleDefinition(
            role_id="r-cco",
            name="Chief Compliance Officer",
            reports_to_role_id="r-ceo",
            is_primary_for_unit="d-compliance",
        ),
        RoleDefinition(
            role_id="r-aml",
            name="AML Officer",
            reports_to_role_id="r-cco",
            is_primary_for_unit="t-aml",
        ),
        RoleDefinition(
            role_id="r-adv-head",
            name="Head of Advisory",
            reports_to_role_id="r-ceo",
            is_primary_for_unit="d-advisory",
        ),
        RoleDefinition(
            role_id="r-advisor",
            name="Senior Advisor",
            reports_to_role_id="r-adv-head",
            is_primary_for_unit="t-client-advisory",
        ),
        RoleDefinition(
            role_id="r-trd-head",
            name="Head of Trading",
            reports_to_role_id="r-ceo",
            is_primary_for_unit="d-trading",
        ),
        RoleDefinition(
            role_id="r-trader",
            name="Senior Trader",
            reports_to_role_id="r-trd-head",
            is_primary_for_unit="t-equities",
        ),
    ]

    departments = [
        DepartmentConfig(department_id="d-exec", name="Executive Office"),
        DepartmentConfig(department_id="d-compliance", name="Compliance Division"),
        DepartmentConfig(department_id="d-advisory", name="Advisory Division"),
        DepartmentConfig(department_id="d-trading", name="Trading Division"),
    ]

    teams = [
        TeamConfig(id="t-aml", name="AML/CFT Team", workspace="ws-aml"),
        TeamConfig(id="t-client-advisory", name="Client Advisory Team", workspace="ws-advisory"),
        TeamConfig(id="t-equities", name="Equities Desk", workspace="ws-trading"),
    ]

    org = OrgDefinition(
        org_id="finserv-001",
        name="Financial Services Corp",
        departments=departments,
        teams=teams,
        roles=roles,
    )
    return compile_org(org)


@pytest.fixture
def clearances(finserv_org: CompiledOrg) -> dict[str, RoleClearance]:
    """Clearance assignments for all roles in the financial services org."""
    return {
        # CCO: SECRET clearance, compliance compartments
        "D1-R1-D1-R1": RoleClearance(
            role_address="D1-R1-D1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
            compartments=frozenset({"compliance-monitoring"}),
            nda_signed=True,
        ),
        # AML Officer: SECRET clearance, aml-investigations compartment
        "D1-R1-D1-R1-T1-R1": RoleClearance(
            role_address="D1-R1-D1-R1-T1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
            compartments=frozenset({"aml-investigations"}),
            nda_signed=True,
        ),
        # Head of Advisory: CONFIDENTIAL, no investigation compartments
        "D1-R1-D2-R1": RoleClearance(
            role_address="D1-R1-D2-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
        ),
        # Senior Advisor: CONFIDENTIAL
        "D1-R1-D2-R1-T1-R1": RoleClearance(
            role_address="D1-R1-D2-R1-T1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
        ),
        # Head of Trading: CONFIDENTIAL, no investigation compartments
        "D1-R1-D3-R1": RoleClearance(
            role_address="D1-R1-D3-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
        ),
        # Senior Trader: CONFIDENTIAL
        "D1-R1-D3-R1-T1-R1": RoleClearance(
            role_address="D1-R1-D3-R1-T1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
        ),
        # CEO: SECRET clearance
        "D1-R1": RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.SECRET,
            nda_signed=True,
        ),
    }


@pytest.fixture
def cco_bridges() -> list[PactBridge]:
    """CCO standing bridges to Advisory and Trading for compliance monitoring."""
    return [
        PactBridge(
            id="bridge-cco-advisory",
            role_a_address="D1-R1-D1-R1",  # CCO
            role_b_address="D1-R1-D2-R1",  # Head of Advisory
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            bilateral=True,
        ),
        PactBridge(
            id="bridge-cco-trading",
            role_a_address="D1-R1-D1-R1",  # CCO
            role_b_address="D1-R1-D3-R1",  # Head of Trading
            bridge_type="standing",
            max_classification=ConfidentialityLevel.CONFIDENTIAL,
            bilateral=True,
        ),
    ]


@pytest.fixture
def trading_positions() -> KnowledgeItem:
    """Trading positions data owned by the Trading Division."""
    return KnowledgeItem(
        item_id="trading-positions-q1",
        classification=ConfidentialityLevel.CONFIDENTIAL,
        owning_unit_address="D1-R1-D3",
        description="Q1 2026 trading positions",
    )


@pytest.fixture
def advisory_data() -> KnowledgeItem:
    """Client advisory data owned by the Advisory Division."""
    return KnowledgeItem(
        item_id="client-advisory-report",
        classification=ConfidentialityLevel.CONFIDENTIAL,
        owning_unit_address="D1-R1-D2",
        description="Client advisory investment recommendations",
    )


@pytest.fixture
def aml_investigation() -> KnowledgeItem:
    """AML investigation data — SECRET with compartment."""
    return KnowledgeItem(
        item_id="aml-investigation-2026-001",
        classification=ConfidentialityLevel.SECRET,
        owning_unit_address="D1-R1-D1-R1-T1",
        compartments=frozenset({"aml-investigations"}),
        description="Active AML investigation case file",
    )


@pytest.fixture
def equities_data() -> KnowledgeItem:
    """Equities desk data — owned by the Equities team."""
    return KnowledgeItem(
        item_id="equities-desk-positions",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D3-R1-T1",
        description="Equities desk current positions",
    )


@pytest.fixture
def client_advisory_data() -> KnowledgeItem:
    """Client advisory team data."""
    return KnowledgeItem(
        item_id="client-portfolio-analysis",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D2-R1-T1",
        description="Client portfolio analysis",
    )


# ---------------------------------------------------------------------------
# Scenario 1: Advisory Analyst requests Trading positions -> BLOCKED
# ---------------------------------------------------------------------------


class TestScenario1AdvisoryBlockedFromTrading:
    """The FLAGSHIP scenario: information barrier prevents advisory from seeing trading data.

    Senior Advisor (D1-R1-D2-R1-T1-R1) requests trading positions owned by
    Trading Division (D1-R1-D3). There is NO KSP between Advisory and Trading,
    and NO bridge connecting them. The access algorithm MUST deny this.
    """

    def test_advisor_cannot_access_trading_positions(
        self,
        finserv_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        cco_bridges: list[PactBridge],
        trading_positions: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D2-R1-T1-R1",  # Senior Advisor
            knowledge_item=trading_positions,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=finserv_org,
            clearances=clearances,
            ksps=[],  # NO KSP between Advisory and Trading
            bridges=cco_bridges,  # CCO bridges exist but don't help the advisor
        )
        assert decision.allowed is False, (
            f"Information barrier BREACHED! Senior Advisor accessed trading data. "
            f"Reason: {decision.reason}"
        )

    def test_head_of_advisory_cannot_access_trading_positions(
        self,
        finserv_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        cco_bridges: list[PactBridge],
        trading_positions: KnowledgeItem,
    ) -> None:
        """Even the head of advisory division cannot access trading data."""
        decision = can_access(
            role_address="D1-R1-D2-R1",  # Head of Advisory
            knowledge_item=trading_positions,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=finserv_org,
            clearances=clearances,
            ksps=[],
            bridges=cco_bridges,
        )
        assert decision.allowed is False


# ---------------------------------------------------------------------------
# Scenario 2: CCO reads Advisory data via bridge -> ALLOWED
# ---------------------------------------------------------------------------


class TestScenario2CCOReadsAdvisory:
    """CCO has a standing bridge to Advisory Division."""

    def test_cco_reads_advisory_data(
        self,
        finserv_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        cco_bridges: list[PactBridge],
        advisory_data: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D1-R1",  # CCO
            knowledge_item=advisory_data,
            posture=TrustPostureLevel.CONTINUOUS_INSIGHT,
            compiled_org=finserv_org,
            clearances=clearances,
            ksps=[],
            bridges=cco_bridges,
        )
        assert decision.allowed is True, (
            f"CCO should have bridge access to Advisory data. " f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 3: CCO reads Trading data via bridge -> ALLOWED
# ---------------------------------------------------------------------------


class TestScenario3CCOReadsTrading:
    """CCO has a standing bridge to Trading Division."""

    def test_cco_reads_trading_data(
        self,
        finserv_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        cco_bridges: list[PactBridge],
        trading_positions: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D1-R1",  # CCO
            knowledge_item=trading_positions,
            posture=TrustPostureLevel.CONTINUOUS_INSIGHT,
            compiled_org=finserv_org,
            clearances=clearances,
            ksps=[],
            bridges=cco_bridges,
        )
        assert decision.allowed is True, (
            f"CCO should have bridge access to Trading data. " f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 4: AML Officer reads AML investigation data -> ALLOWED
# ---------------------------------------------------------------------------


class TestScenario4AMLOfficerReadsInvestigation:
    """AML Officer has SECRET clearance with aml-investigations compartment."""

    def test_aml_officer_reads_investigation(
        self,
        finserv_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        cco_bridges: list[PactBridge],
        aml_investigation: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D1-R1-T1-R1",  # AML Officer
            knowledge_item=aml_investigation,
            posture=TrustPostureLevel.CONTINUOUS_INSIGHT,
            compiled_org=finserv_org,
            clearances=clearances,
            ksps=[],
            bridges=cco_bridges,
        )
        assert decision.allowed is True, (
            f"AML Officer should access AML investigation data. " f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 5: Head of Trading requests AML investigation data -> BLOCKED
# ---------------------------------------------------------------------------


class TestScenario5TradingBlockedFromInvestigation:
    """Head of Trading has no compartment access to AML investigation data."""

    def test_trading_head_blocked_from_aml_data(
        self,
        finserv_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        cco_bridges: list[PactBridge],
        aml_investigation: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D3-R1",  # Head of Trading
            knowledge_item=aml_investigation,
            posture=TrustPostureLevel.CONTINUOUS_INSIGHT,
            compiled_org=finserv_org,
            clearances=clearances,
            ksps=[],
            bridges=cco_bridges,
        )
        assert decision.allowed is False, (
            f"Head of Trading should NOT access AML investigation data. "
            f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 6: Senior Trader reads Equities Desk data -> ALLOWED
# ---------------------------------------------------------------------------


class TestScenario6TraderReadsSameUnit:
    """Senior Trader in Equities Desk reads Equities Desk data (same unit)."""

    def test_trader_reads_own_team_data(
        self,
        finserv_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        cco_bridges: list[PactBridge],
        equities_data: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D3-R1-T1-R1",  # Senior Trader
            knowledge_item=equities_data,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=finserv_org,
            clearances=clearances,
            ksps=[],
            bridges=cco_bridges,
        )
        assert decision.allowed is True, (
            f"Senior Trader should access Equities Desk data (same unit). "
            f"Reason: {decision.reason}"
        )


# ---------------------------------------------------------------------------
# Scenario 7: Senior Advisor reads Client Advisory data -> ALLOWED
# ---------------------------------------------------------------------------


class TestScenario7AdvisorReadsSameUnit:
    """Senior Advisor reads Client Advisory Team data (same unit)."""

    def test_advisor_reads_own_team_data(
        self,
        finserv_org: CompiledOrg,
        clearances: dict[str, RoleClearance],
        cco_bridges: list[PactBridge],
        client_advisory_data: KnowledgeItem,
    ) -> None:
        decision = can_access(
            role_address="D1-R1-D2-R1-T1-R1",  # Senior Advisor
            knowledge_item=client_advisory_data,
            posture=TrustPostureLevel.SHARED_PLANNING,
            compiled_org=finserv_org,
            clearances=clearances,
            ksps=[],
            bridges=cco_bridges,
        )
        assert decision.allowed is True, (
            f"Senior Advisor should access Client Advisory data (same unit). "
            f"Reason: {decision.reason}"
        )
