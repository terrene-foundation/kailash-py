# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for PactGovernanceMiddleware -- Kaizen middleware for governance enforcement.

Covers:
- TODO 7031: Middleware pre_execute returns correct GovernanceVerdict
- auto_approved, flagged, held, blocked scenarios
- Middleware does NOT block or raise -- it returns verdicts for caller to handle
"""

from __future__ import annotations

from typing import Any

import pytest

from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TrustPostureLevel,
)
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org
from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.clearance import RoleClearance
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.middleware import PactGovernanceMiddleware
from kailash.trust.pact.store import (
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
)
from kailash.trust.pact.verdict import GovernanceVerdict


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def university_compiled() -> tuple[CompiledOrg, Any]:
    return create_university_org()


@pytest.fixture
def compiled_org(university_compiled: tuple[CompiledOrg, Any]) -> CompiledOrg:
    return university_compiled[0]


@pytest.fixture
def clearances(compiled_org: CompiledOrg) -> dict[str, RoleClearance]:
    return create_university_clearances(compiled_org)


@pytest.fixture
def bridges() -> list[PactBridge]:
    return create_university_bridges()


@pytest.fixture
def ksps() -> list[KnowledgeSharePolicy]:
    return create_university_ksps()


@pytest.fixture
def engine(
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],
    bridges: list[PactBridge],
    ksps: list[KnowledgeSharePolicy],
) -> GovernanceEngine:
    clearance_store = MemoryClearanceStore()
    for clr in clearances.values():
        clearance_store.grant_clearance(clr)

    access_store = MemoryAccessPolicyStore()
    for bridge in bridges:
        access_store.save_bridge(bridge)
    for ksp in ksps:
        access_store.save_ksp(ksp)

    eng = GovernanceEngine(
        compiled_org,
        clearance_store=clearance_store,
        access_policy_store=access_store,
    )

    # Set up envelope for CS Chair
    envelope_config = ConstraintEnvelopeConfig(
        id="env-cs-chair",
        description="CS Chair envelope",
        financial=FinancialConstraintConfig(
            max_spend_usd=1000.0,
            requires_approval_above_usd=500.0,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write", "grade"],
            blocked_actions=["delete"],
        ),
    )
    role_env = RoleEnvelope(
        id="re-cs-chair",
        defining_role_address="D1-R1-D1-R1-D1-R1",
        target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
        envelope=envelope_config,
    )
    eng.set_role_envelope(role_env)

    return eng


CS_CHAIR_ADDR = "D1-R1-D1-R1-D1-R1-T1-R1"


@pytest.fixture
def middleware(engine: GovernanceEngine) -> PactGovernanceMiddleware:
    return PactGovernanceMiddleware(
        engine=engine,
        role_address=CS_CHAIR_ADDR,
    )


# ---------------------------------------------------------------------------
# Construction Tests
# ---------------------------------------------------------------------------


class TestConstruction:
    """Middleware construction."""

    def test_construction_succeeds(self, engine: GovernanceEngine) -> None:
        mw = PactGovernanceMiddleware(engine=engine, role_address=CS_CHAIR_ADDR)
        assert mw is not None

    def test_role_address_stored(self, middleware: PactGovernanceMiddleware) -> None:
        assert middleware.role_address == CS_CHAIR_ADDR


# ---------------------------------------------------------------------------
# pre_execute Tests
# ---------------------------------------------------------------------------


class TestPreExecute:
    """pre_execute returns GovernanceVerdict without raising exceptions."""

    def test_auto_approved_action(self, middleware: PactGovernanceMiddleware) -> None:
        """An allowed action within envelope returns auto_approved verdict."""
        verdict = middleware.pre_execute("read", context={"cost": 10.0})
        assert isinstance(verdict, GovernanceVerdict)
        assert verdict.level == "auto_approved"
        assert verdict.allowed is True

    def test_blocked_action(self, middleware: PactGovernanceMiddleware) -> None:
        """An explicitly blocked action returns blocked verdict."""
        verdict = middleware.pre_execute("delete")
        assert isinstance(verdict, GovernanceVerdict)
        assert verdict.level == "blocked"
        assert verdict.allowed is False

    def test_blocked_action_not_in_allowed_list(
        self, middleware: PactGovernanceMiddleware
    ) -> None:
        """An action not in the allowed_actions list returns blocked verdict."""
        verdict = middleware.pre_execute("deploy")
        assert isinstance(verdict, GovernanceVerdict)
        assert verdict.level == "blocked"
        assert verdict.allowed is False

    def test_held_action_over_approval_threshold(
        self, middleware: PactGovernanceMiddleware
    ) -> None:
        """An action with cost over approval threshold returns held verdict."""
        verdict = middleware.pre_execute("write", context={"cost": 600.0})
        assert isinstance(verdict, GovernanceVerdict)
        assert verdict.level == "held"
        assert verdict.allowed is False

    def test_flagged_action_near_boundary(self, engine: GovernanceEngine) -> None:
        """An action near the financial limit returns flagged verdict.

        The engine checks approval threshold BEFORE flagged zone.
        To reach FLAGGED, cost must be > 80% of max_spend AND
        <= requires_approval_above_usd. Use an envelope where
        approval threshold is above the flagged zone start.
        """
        # Override envelope: max_spend=1000, approval_threshold=900
        # Flagged zone: 800..900. Cost 850 -> FLAGGED.
        envelope_config = ConstraintEnvelopeConfig(
            id="env-cs-chair-flagged",
            description="CS Chair envelope for flagged test",
            financial=FinancialConstraintConfig(
                max_spend_usd=1000.0,
                requires_approval_above_usd=900.0,
            ),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "grade"],
            ),
        )
        role_env = RoleEnvelope(
            id="re-cs-chair-flagged",
            defining_role_address="D1-R1-D1-R1-D1-R1",
            target_role_address=CS_CHAIR_ADDR,
            envelope=envelope_config,
        )
        engine.set_role_envelope(role_env)

        mw = PactGovernanceMiddleware(engine=engine, role_address=CS_CHAIR_ADDR)
        verdict = mw.pre_execute("grade", context={"cost": 850.0})
        assert isinstance(verdict, GovernanceVerdict)
        assert verdict.level == "flagged"
        assert verdict.allowed is True

    def test_no_context_defaults_to_empty(
        self, middleware: PactGovernanceMiddleware
    ) -> None:
        """Calling pre_execute without context should use empty dict."""
        verdict = middleware.pre_execute("read")
        assert isinstance(verdict, GovernanceVerdict)
        assert verdict.level == "auto_approved"

    def test_verdict_has_role_address(
        self, middleware: PactGovernanceMiddleware
    ) -> None:
        """Verdict should include the role_address."""
        verdict = middleware.pre_execute("read")
        assert verdict.role_address == CS_CHAIR_ADDR

    def test_verdict_has_action(self, middleware: PactGovernanceMiddleware) -> None:
        """Verdict should include the action name."""
        verdict = middleware.pre_execute("grade")
        assert verdict.action == "grade"
