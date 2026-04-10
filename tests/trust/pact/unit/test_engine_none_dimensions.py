# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Regression tests for GH #390: verify_action crashes when envelope dimensions are None.

When a ConstraintEnvelopeConfig has None for any of the five constraint
dimensions (financial, operational, temporal, data_access, communication),
_evaluate_against_envelope must skip that dimension entirely (unconstrained /
maximally permissive) rather than raising AttributeError which the outer
try/except converts to BLOCKED -- the opposite of the intended behavior.

Covers:
- Each dimension individually as None
- All dimensions None simultaneously
- Mixed None/set dimensions
- Existing non-None envelopes still evaluated correctly
"""

from __future__ import annotations

from typing import Any

import pytest
from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.clearance import RoleClearance
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.config import (
    CommunicationConstraintConfig,
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.store import MemoryAccessPolicyStore, MemoryClearanceStore
from kailash.trust.pact.verdict import GovernanceVerdict
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Target role address used throughout: CS Chair in the university example.
# D1-R1-D1-R1-D1-R1-T1-R1 is a valid leaf role in the compiled org.
_TARGET_ROLE = "D1-R1-D1-R1-D1-R1-T1-R1"
_DEFINING_ROLE = "D1-R1-D1-R1-D1-R1"  # Dean, who defines the CS Chair envelope


@pytest.fixture
def compiled_org() -> CompiledOrg:
    """Compiled university org."""
    compiled, _ = create_university_org()
    return compiled


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
    """Fresh GovernanceEngine for each test."""
    clearance_store = MemoryClearanceStore()
    for clr in clearances.values():
        clearance_store.grant_clearance(clr)

    access_store = MemoryAccessPolicyStore()
    for bridge in bridges:
        access_store.save_bridge(bridge)
    for ksp in ksps:
        access_store.save_ksp(ksp)

    return GovernanceEngine(
        compiled_org,
        clearance_store=clearance_store,
        access_policy_store=access_store,
    )


def _set_envelope(
    engine: GovernanceEngine,
    envelope_config: ConstraintEnvelopeConfig,
    *,
    envelope_id: str = "re-none-dim-test",
) -> None:
    """Helper to set a role envelope on the engine, bypassing monotonic
    tightening by using the defining role that has no parent envelope."""
    role_env = RoleEnvelope(
        id=envelope_id,
        defining_role_address=_DEFINING_ROLE,
        target_role_address=_TARGET_ROLE,
        envelope=envelope_config,
    )
    engine.set_role_envelope(role_env)


def _make_envelope_with_none_dimensions(
    *,
    operational: OperationalConstraintConfig | None = None,
    financial: FinancialConstraintConfig | None = None,
    temporal: TemporalConstraintConfig | None = None,
    data_access: DataAccessConstraintConfig | None = None,
    communication: CommunicationConstraintConfig | None = None,
) -> ConstraintEnvelopeConfig:
    """Build a ConstraintEnvelopeConfig via model_construct to allow None
    on dimensions that are normally non-Optional in the type annotations.

    This simulates what happens when envelopes are loaded from YAML/JSON
    with explicit null values or constructed via Rust SDK interop.
    """
    return ConstraintEnvelopeConfig.model_construct(
        id="env-none-dim-test",
        description="Envelope with None dimensions for GH #390 regression",
        confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        financial=financial,
        operational=operational,
        temporal=temporal,
        data_access=data_access,
        communication=communication,
        max_delegation_depth=None,
        expires_at=None,
    )


# ===========================================================================
# GH #390 Regression: individual None dimensions
# ===========================================================================


@pytest.mark.regression
class TestOperationalNone:
    """When operational is None, the operational dimension is unconstrained."""

    def test_operational_none_does_not_crash(self, engine: GovernanceEngine) -> None:
        """GH #390: operational=None must not raise AttributeError."""
        env = _make_envelope_with_none_dimensions(operational=None)
        _set_envelope(engine, env)

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="any_action_at_all",
        )
        assert isinstance(verdict, GovernanceVerdict)
        # None operational means unconstrained -- should NOT be blocked
        assert verdict.level != "blocked" or "Internal error" not in verdict.reason

    def test_operational_none_permits_any_action(
        self, engine: GovernanceEngine
    ) -> None:
        """With operational=None, any action name should be permitted."""
        env = _make_envelope_with_none_dimensions(operational=None)
        _set_envelope(engine, env)

        for action in ("read", "write", "deploy", "delete", "nuke_from_orbit"):
            verdict = engine.verify_action(
                role_address=_TARGET_ROLE,
                action=action,
            )
            assert verdict.level == "auto_approved", (
                f"Action '{action}' should be auto_approved with operational=None, "
                f"got level={verdict.level!r}, reason={verdict.reason!r}"
            )


@pytest.mark.regression
class TestFinancialNone:
    """When financial is None, the financial dimension is unconstrained."""

    def test_financial_none_skips_cost_check(self, engine: GovernanceEngine) -> None:
        """Financial=None: even large costs should pass the financial dimension."""
        env = _make_envelope_with_none_dimensions(
            operational=OperationalConstraintConfig(
                allowed_actions=["spend"],
            ),
            financial=None,
        )
        _set_envelope(engine, env)

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="spend",
            context={"cost": 999_999_999.99},
        )
        assert verdict.level == "auto_approved"


@pytest.mark.regression
class TestTemporalNone:
    """When temporal is None, the temporal dimension is unconstrained."""

    def test_temporal_none_skips_time_check(self, engine: GovernanceEngine) -> None:
        """Temporal=None: actions are permitted regardless of time of day."""
        env = _make_envelope_with_none_dimensions(
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
            ),
            temporal=None,
        )
        _set_envelope(engine, env)

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="read",
        )
        assert verdict.level == "auto_approved"


@pytest.mark.regression
class TestDataAccessNone:
    """When data_access is None, the data access dimension is unconstrained."""

    def test_data_access_none_skips_path_check(self, engine: GovernanceEngine) -> None:
        """DataAccess=None: any resource path should pass."""
        env = _make_envelope_with_none_dimensions(
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
            ),
            data_access=None,
        )
        _set_envelope(engine, env)

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="read",
            context={
                "resource_path": "/secret/vault/data",
                "access_type": "read",
            },
        )
        assert verdict.level == "auto_approved"


@pytest.mark.regression
class TestCommunicationNone:
    """When communication is None, the communication dimension is unconstrained."""

    def test_communication_none_skips_channel_check(
        self, engine: GovernanceEngine
    ) -> None:
        """Communication=None: any channel including external should pass."""
        env = _make_envelope_with_none_dimensions(
            operational=OperationalConstraintConfig(
                allowed_actions=["notify"],
            ),
            communication=None,
        )
        _set_envelope(engine, env)

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="notify",
            context={
                "channel": "external-api",
                "is_external": True,
            },
        )
        assert verdict.level == "auto_approved"


# ===========================================================================
# All dimensions None simultaneously
# ===========================================================================


@pytest.mark.regression
class TestAllDimensionsNone:
    """When ALL five dimensions are None, the envelope is maximally permissive."""

    def test_all_none_permits_any_action(self, engine: GovernanceEngine) -> None:
        """All dimensions None: any action with any context should be auto_approved."""
        env = _make_envelope_with_none_dimensions(
            operational=None,
            financial=None,
            temporal=None,
            data_access=None,
            communication=None,
        )
        _set_envelope(engine, env)

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="deploy",
            context={
                "cost": 50_000.0,
                "resource_path": "/production/database",
                "access_type": "write",
                "channel": "external",
                "is_external": True,
            },
        )
        assert verdict.level == "auto_approved", (
            f"All-None envelope should be auto_approved, "
            f"got level={verdict.level!r}, reason={verdict.reason!r}"
        )

    def test_all_none_does_not_produce_internal_error(
        self, engine: GovernanceEngine
    ) -> None:
        """All-None must not trigger the fail-closed error handler."""
        env = _make_envelope_with_none_dimensions()
        _set_envelope(engine, env)

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="read",
        )
        assert "Internal error" not in verdict.reason


# ===========================================================================
# Mixed None/set dimensions
# ===========================================================================


@pytest.mark.regression
class TestMixedDimensions:
    """Some dimensions set, some None -- only set dimensions should constrain."""

    def test_operational_set_financial_none(self, engine: GovernanceEngine) -> None:
        """Operational restricts, financial is unconstrained."""
        env = _make_envelope_with_none_dimensions(
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
                blocked_actions=["delete"],
            ),
            financial=None,
        )
        _set_envelope(engine, env)

        # Allowed action passes
        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="read",
            context={"cost": 999_999.0},
        )
        assert verdict.level == "auto_approved"

        # Blocked action is still blocked
        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="delete",
        )
        assert verdict.level == "blocked"

    def test_financial_set_operational_none(self, engine: GovernanceEngine) -> None:
        """Financial restricts, operational is unconstrained."""
        env = _make_envelope_with_none_dimensions(
            operational=None,
            financial=FinancialConstraintConfig(max_spend_usd=100.0),
        )
        _set_envelope(engine, env)

        # Any action name is fine (operational unconstrained)
        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="unknown_action",
            context={"cost": 50.0},
        )
        assert verdict.level == "auto_approved"

        # But exceeding cost limit is blocked
        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="unknown_action",
            context={"cost": 200.0},
        )
        assert verdict.level == "blocked"
        assert "financial" in verdict.reason.lower() or "cost" in verdict.reason.lower()

    def test_communication_set_others_none(self, engine: GovernanceEngine) -> None:
        """Only communication constrains -- internal_only blocks external."""
        env = _make_envelope_with_none_dimensions(
            operational=None,
            financial=None,
            temporal=None,
            data_access=None,
            communication=CommunicationConstraintConfig(
                internal_only=True,
                allowed_channels=["slack"],
            ),
        )
        _set_envelope(engine, env)

        # Internal action passes
        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="send_message",
            context={"channel": "slack", "is_external": False},
        )
        assert verdict.level == "auto_approved"

        # External action blocked
        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="send_message",
            context={"channel": "slack", "is_external": True},
        )
        assert verdict.level == "blocked"


# ===========================================================================
# Existing non-None envelopes still work (no regression on normal path)
# ===========================================================================


@pytest.mark.regression
class TestNonNoneStillWorks:
    """Sanity check: envelopes with all dimensions set still evaluate correctly."""

    def test_fully_specified_envelope_blocks_disallowed_action(
        self, engine: GovernanceEngine
    ) -> None:
        """A fully specified envelope with explicit allowed_actions blocks others."""
        env = ConstraintEnvelopeConfig(
            id="env-full",
            financial=FinancialConstraintConfig(max_spend_usd=100.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
                blocked_actions=["delete"],
            ),
            temporal=TemporalConstraintConfig(),
            data_access=DataAccessConstraintConfig(),
            communication=CommunicationConstraintConfig(),
        )
        _set_envelope(engine, env, envelope_id="re-full-test")

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="read",
        )
        assert verdict.level == "auto_approved"

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="delete",
        )
        assert verdict.level == "blocked"

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="deploy",
        )
        assert verdict.level == "blocked"

    def test_fully_specified_envelope_enforces_cost_limit(
        self, engine: GovernanceEngine
    ) -> None:
        """A fully specified envelope enforces max_spend_usd."""
        env = ConstraintEnvelopeConfig(
            id="env-cost",
            financial=FinancialConstraintConfig(max_spend_usd=50.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["spend"],
            ),
        )
        _set_envelope(engine, env, envelope_id="re-cost-test")

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="spend",
            context={"cost": 10.0},
        )
        assert verdict.level == "auto_approved"

        verdict = engine.verify_action(
            role_address=_TARGET_ROLE,
            action="spend",
            context={"cost": 100.0},
        )
        assert verdict.level == "blocked"
