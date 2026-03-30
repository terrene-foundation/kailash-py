# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for vacancy handling in verify_action() -- PACT Section 5.5.

When a role is vacant, the parent role must designate an acting occupant
within 24 hours. If no designation exists (or it has expired), all downstream
agents are auto-suspended (actions blocked).

Covers:
- Vacancy without designation blocks action
- Vacancy with valid designation allows action
- Expired designation blocks action
- designate_acting_occupant creates valid designation
- Acting occupant uses vacant role's envelope
- Acting occupant does NOT get clearance upgrades
- Ancestor vacancy blocks downstream actions
- VacancyDesignation serialization (to_dict / from_dict)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from kailash.trust.pact.compilation import (
    RoleDefinition,
    VacancyDesignation,
)
from kailash.trust.pact.config import (
    CommunicationConstraintConfig,
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DepartmentConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    OrgDefinition,
    TeamConfig,
    TrustPostureLevel,
)
from kailash.trust.pact.clearance import RoleClearance, VettingStatus
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.exceptions import PactError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _create_org_with_vacancy() -> OrgDefinition:
    """Create a minimal org with a vacant role for testing.

    Structure:
      D1 (Engineering) - R1 (VP Engineering) [filled]
        T1 (Backend) - R1 (Backend Lead) [VACANT]
          R1 (SeniorDev) [filled, reports to Backend Lead]
    """
    return OrgDefinition(
        org_id="test-vacancy-org",
        name="Test Vacancy Org",
        departments=[
            DepartmentConfig(
                department_id="d-eng",
                name="Engineering",
                workspace="ws-eng",
            ),
        ],
        teams=[
            TeamConfig(
                id="t-backend",
                name="Backend Team",
                workspace="ws-eng",
            ),
        ],
        roles=[
            RoleDefinition(
                role_id="r-vp-eng",
                name="VP Engineering",
                reports_to_role_id=None,
                is_primary_for_unit="d-eng",
                unit_id="d-eng",
                is_vacant=False,
                is_external=False,
            ),
            RoleDefinition(
                role_id="r-backend-lead",
                name="Backend Lead",
                reports_to_role_id="r-vp-eng",
                is_primary_for_unit="t-backend",
                unit_id="t-backend",
                is_vacant=True,  # VACANT
                is_external=False,
            ),
            RoleDefinition(
                role_id="r-senior-dev",
                name="Senior Developer",
                reports_to_role_id="r-backend-lead",
                unit_id="t-backend",
                is_vacant=False,
                is_external=False,
            ),
        ],
    )


@pytest.fixture
def org_def() -> OrgDefinition:
    """Org with a vacant Backend Lead role."""
    return _create_org_with_vacancy()


@pytest.fixture
def engine(org_def: OrgDefinition) -> GovernanceEngine:
    """GovernanceEngine with the vacancy org. No envelopes set by default."""
    return GovernanceEngine(org_def)


# ---------------------------------------------------------------------------
# Helper to find addresses in the compiled org
# ---------------------------------------------------------------------------


def _find_address(engine: GovernanceEngine, role_id: str) -> str:
    """Look up the positional address for a role_id in the compiled org."""
    org = engine.get_org()
    node = org.get_node_by_role_id(role_id)
    assert node is not None, f"Role '{role_id}' not found in compiled org"
    return node.address


# ---------------------------------------------------------------------------
# Test: VacancyDesignation dataclass
# ---------------------------------------------------------------------------


class TestVacancyDesignation:
    """Tests for the VacancyDesignation frozen dataclass."""

    def test_frozen(self) -> None:
        """VacancyDesignation is immutable (frozen=True)."""
        now = datetime.now(timezone.utc)
        d = VacancyDesignation(
            vacant_role_address="D1-R1-T1-R1",
            acting_role_address="D1-R1",
            designated_by="D1-R1",
            designated_at=now.isoformat(),
            expires_at=(now + timedelta(hours=24)).isoformat(),
        )
        with pytest.raises(AttributeError):
            d.vacant_role_address = "modified"  # type: ignore[misc]

    def test_is_expired_false_when_future(self) -> None:
        """Designation is not expired when expires_at is in the future."""
        now = datetime.now(timezone.utc)
        d = VacancyDesignation(
            vacant_role_address="D1-R1-T1-R1",
            acting_role_address="D1-R1",
            designated_by="D1-R1",
            designated_at=now.isoformat(),
            expires_at=(now + timedelta(hours=24)).isoformat(),
        )
        assert d.is_expired() is False

    def test_is_expired_true_when_past(self) -> None:
        """Designation is expired when expires_at is in the past."""
        past = datetime.now(timezone.utc) - timedelta(hours=25)
        d = VacancyDesignation(
            vacant_role_address="D1-R1-T1-R1",
            acting_role_address="D1-R1",
            designated_by="D1-R1",
            designated_at=past.isoformat(),
            expires_at=(past + timedelta(hours=24)).isoformat(),
        )
        assert d.is_expired() is True

    def test_to_dict(self) -> None:
        """to_dict serializes all fields."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=24)
        d = VacancyDesignation(
            vacant_role_address="D1-R1-T1-R1",
            acting_role_address="D1-R1",
            designated_by="D1-R1",
            designated_at=now.isoformat(),
            expires_at=expires.isoformat(),
        )
        result = d.to_dict()
        assert result["vacant_role_address"] == "D1-R1-T1-R1"
        assert result["acting_role_address"] == "D1-R1"
        assert result["designated_by"] == "D1-R1"
        assert result["designated_at"] == now.isoformat()
        assert result["expires_at"] == expires.isoformat()

    def test_from_dict_roundtrip(self) -> None:
        """from_dict(to_dict()) produces an equal object."""
        now = datetime.now(timezone.utc)
        original = VacancyDesignation(
            vacant_role_address="D1-R1-T1-R1",
            acting_role_address="D1-R1",
            designated_by="D1-R1",
            designated_at=now.isoformat(),
            expires_at=(now + timedelta(hours=24)).isoformat(),
        )
        restored = VacancyDesignation.from_dict(original.to_dict())
        assert restored == original

    def test_from_dict_rejects_bad_timestamp(self) -> None:
        """from_dict raises ValueError on malformed timestamps."""
        with pytest.raises((ValueError, KeyError)):
            VacancyDesignation.from_dict(
                {
                    "vacant_role_address": "D1-R1",
                    "acting_role_address": "D1-R1",
                    "designated_by": "D1-R1",
                    "designated_at": "not-a-timestamp",
                    "expires_at": "also-bad",
                }
            )


# ---------------------------------------------------------------------------
# Test: Vacancy without designation blocks action
# ---------------------------------------------------------------------------


class TestVacancyBlocksAction:
    """When a role is vacant and there is no acting occupant designation,
    verify_action() must return BLOCKED.
    """

    def test_vacant_role_blocks_action(self, engine: GovernanceEngine) -> None:
        """An action by a vacant role with no designation is blocked."""
        vacant_addr = _find_address(engine, "r-backend-lead")
        verdict = engine.verify_action(vacant_addr, "deploy")
        assert verdict.level == "blocked"
        assert "vacant" in verdict.reason.lower()
        assert "PACT Section 5.5" in verdict.reason

    def test_downstream_of_vacant_role_blocked(self, engine: GovernanceEngine) -> None:
        """Actions by a role that reports to a vacant role are also blocked
        (auto-suspension of downstream agents).
        """
        dev_addr = _find_address(engine, "r-senior-dev")
        verdict = engine.verify_action(dev_addr, "code_review")
        assert verdict.level == "blocked"
        assert "vacant" in verdict.reason.lower()

    def test_non_vacant_role_not_blocked(self, engine: GovernanceEngine) -> None:
        """A filled role is NOT blocked by vacancy checks."""
        vp_addr = _find_address(engine, "r-vp-eng")
        verdict = engine.verify_action(vp_addr, "review")
        # Should not be blocked by vacancy (may be auto_approved or blocked
        # by other constraints, but not by vacancy)
        assert "vacant" not in verdict.reason.lower()


# ---------------------------------------------------------------------------
# Test: Vacancy with valid designation allows action
# ---------------------------------------------------------------------------


class TestVacancyWithDesignation:
    """When a valid (non-expired) acting occupant designation exists,
    the vacancy check passes and the action proceeds to normal envelope checks.
    """

    def test_designation_unblocks_vacant_role(self, engine: GovernanceEngine) -> None:
        """After designating an acting occupant, the vacant role's actions
        are no longer blocked by vacancy.
        """
        vacant_addr = _find_address(engine, "r-backend-lead")
        vp_addr = _find_address(engine, "r-vp-eng")

        # Before designation: blocked
        verdict_before = engine.verify_action(vacant_addr, "deploy")
        assert verdict_before.level == "blocked"
        assert "vacant" in verdict_before.reason.lower()

        # Designate VP as acting occupant
        engine.designate_acting_occupant(
            vacant_role=vacant_addr,
            acting_role=vp_addr,
            designated_by=vp_addr,
        )

        # After designation: no longer blocked by vacancy
        verdict_after = engine.verify_action(vacant_addr, "deploy")
        assert "vacant" not in verdict_after.reason.lower()

    def test_designation_unblocks_downstream(self, engine: GovernanceEngine) -> None:
        """After designating an acting occupant for a vacant ancestor,
        downstream roles are no longer auto-suspended.
        """
        vacant_addr = _find_address(engine, "r-backend-lead")
        dev_addr = _find_address(engine, "r-senior-dev")
        vp_addr = _find_address(engine, "r-vp-eng")

        # Before designation: downstream blocked
        verdict_before = engine.verify_action(dev_addr, "code_review")
        assert verdict_before.level == "blocked"
        assert "vacant" in verdict_before.reason.lower()

        # Designate
        engine.designate_acting_occupant(
            vacant_role=vacant_addr,
            acting_role=vp_addr,
            designated_by=vp_addr,
        )

        # After designation: downstream no longer vacancy-blocked
        verdict_after = engine.verify_action(dev_addr, "code_review")
        assert "vacant" not in verdict_after.reason.lower()


# ---------------------------------------------------------------------------
# Test: Expired designation blocks action
# ---------------------------------------------------------------------------


class TestExpiredDesignation:
    """When the acting occupant designation has expired (past 24h),
    the vacancy check must fail and block the action.
    """

    def test_expired_designation_blocks(self, engine: GovernanceEngine) -> None:
        """An expired designation means the vacant role is again suspended."""
        vacant_addr = _find_address(engine, "r-backend-lead")
        vp_addr = _find_address(engine, "r-vp-eng")

        # Create an expired designation by manually inserting one
        past = datetime.now(timezone.utc) - timedelta(hours=25)
        expired_designation = VacancyDesignation(
            vacant_role_address=vacant_addr,
            acting_role_address=vp_addr,
            designated_by=vp_addr,
            designated_at=past.isoformat(),
            expires_at=(past + timedelta(hours=24)).isoformat(),
        )

        # Directly set the expired designation in the engine's internal store
        # (thread-safe access via the lock for testing purposes)
        with engine._lock:
            engine._vacancy_designations[vacant_addr] = expired_designation

        verdict = engine.verify_action(vacant_addr, "deploy")
        assert verdict.level == "blocked"
        assert "expired" in verdict.reason.lower()
        assert "PACT Section 5.5" in verdict.reason


# ---------------------------------------------------------------------------
# Test: designate_acting_occupant
# ---------------------------------------------------------------------------


class TestDesignateActingOccupant:
    """Tests for the designate_acting_occupant API."""

    def test_creates_valid_designation(self, engine: GovernanceEngine) -> None:
        """designate_acting_occupant returns a VacancyDesignation with correct fields."""
        vacant_addr = _find_address(engine, "r-backend-lead")
        vp_addr = _find_address(engine, "r-vp-eng")

        designation = engine.designate_acting_occupant(
            vacant_role=vacant_addr,
            acting_role=vp_addr,
            designated_by=vp_addr,
        )

        assert isinstance(designation, VacancyDesignation)
        assert designation.vacant_role_address == vacant_addr
        assert designation.acting_role_address == vp_addr
        assert designation.designated_by == vp_addr
        assert designation.is_expired() is False
        # Verify timestamps are valid ISO 8601
        datetime.fromisoformat(designation.designated_at)
        datetime.fromisoformat(designation.expires_at)

    def test_get_vacancy_designation_returns_stored(
        self, engine: GovernanceEngine
    ) -> None:
        """get_vacancy_designation returns the stored designation."""
        vacant_addr = _find_address(engine, "r-backend-lead")
        vp_addr = _find_address(engine, "r-vp-eng")

        engine.designate_acting_occupant(
            vacant_role=vacant_addr,
            acting_role=vp_addr,
            designated_by=vp_addr,
        )

        retrieved = engine.get_vacancy_designation(vacant_addr)
        assert retrieved is not None
        assert retrieved.acting_role_address == vp_addr

    def test_get_vacancy_designation_returns_none_when_missing(
        self, engine: GovernanceEngine
    ) -> None:
        """get_vacancy_designation returns None when no designation exists."""
        vp_addr = _find_address(engine, "r-vp-eng")
        assert engine.get_vacancy_designation(vp_addr) is None

    def test_rejects_non_vacant_role(self, engine: GovernanceEngine) -> None:
        """Designating for a non-vacant role raises PactError."""
        vp_addr = _find_address(engine, "r-vp-eng")

        with pytest.raises(PactError, match="not vacant"):
            engine.designate_acting_occupant(
                vacant_role=vp_addr,
                acting_role=vp_addr,
                designated_by=vp_addr,
            )

    def test_rejects_unknown_vacant_role(self, engine: GovernanceEngine) -> None:
        """Designating for an unknown role address raises PactError."""
        vp_addr = _find_address(engine, "r-vp-eng")

        with pytest.raises(PactError, match="not found"):
            engine.designate_acting_occupant(
                vacant_role="D99-R99",
                acting_role=vp_addr,
                designated_by=vp_addr,
            )

    def test_rejects_unknown_acting_role(self, engine: GovernanceEngine) -> None:
        """Designating an unknown acting role raises PactError."""
        vacant_addr = _find_address(engine, "r-backend-lead")
        vp_addr = _find_address(engine, "r-vp-eng")

        with pytest.raises(PactError, match="not found"):
            engine.designate_acting_occupant(
                vacant_role=vacant_addr,
                acting_role="D99-R99",
                designated_by=vp_addr,
            )

    def test_rejects_unknown_designator(self, engine: GovernanceEngine) -> None:
        """Designating from an unknown role raises PactError."""
        vacant_addr = _find_address(engine, "r-backend-lead")
        vp_addr = _find_address(engine, "r-vp-eng")

        with pytest.raises(PactError, match="not found"):
            engine.designate_acting_occupant(
                vacant_role=vacant_addr,
                acting_role=vp_addr,
                designated_by="D99-R99",
            )


# ---------------------------------------------------------------------------
# Test: Acting occupant uses vacant role's envelope (not clearance upgrades)
# ---------------------------------------------------------------------------


class TestActingOccupantEnvelope:
    """The acting occupant inherits the vacant role's envelope (constraints)
    but does NOT get clearance upgrades from the vacant role.
    """

    def test_acting_occupant_uses_vacant_role_envelope(
        self, engine: GovernanceEngine
    ) -> None:
        """When acting for a vacant role, the effective envelope
        is the vacant role's envelope (not the acting occupant's own).

        We set an envelope on the vacant role with allowed_actions=["deploy"]
        and verify that after designation, the vacant role address can deploy.
        """
        vacant_addr = _find_address(engine, "r-backend-lead")
        vp_addr = _find_address(engine, "r-vp-eng")

        # Set an envelope on the vacant role that allows deploy
        # Must explicitly set internal_only=False to avoid the default
        # communication constraint blocking the action
        env_config = ConstraintEnvelopeConfig(
            id="env-backend-lead",
            operational=OperationalConstraintConfig(
                allowed_actions=["deploy", "review"],
                blocked_actions=[],
            ),
            communication=CommunicationConstraintConfig(
                internal_only=False,
                external_requires_approval=False,
            ),
        )
        role_env = RoleEnvelope(
            id="re-backend-lead",
            target_role_address=vacant_addr,
            defining_role_address=vp_addr,
            envelope=env_config,
        )
        engine.set_role_envelope(role_env)

        # Designate acting occupant
        engine.designate_acting_occupant(
            vacant_role=vacant_addr,
            acting_role=vp_addr,
            designated_by=vp_addr,
        )

        # The vacant role's address should now be evaluated against the
        # vacant role's envelope, and "deploy" is allowed
        verdict = engine.verify_action(vacant_addr, "deploy")
        assert verdict.level == "auto_approved"

    def test_acting_occupant_does_not_get_clearance_upgrade(
        self, engine: GovernanceEngine
    ) -> None:
        """The acting occupant does not inherit the vacant role's clearance.

        Grant CONFIDENTIAL clearance to the vacant role and PUBLIC to the
        acting occupant. The acting occupant should NOT gain CONFIDENTIAL
        access through the designation -- the clearance check uses the
        acting occupant's own clearance.
        """
        vacant_addr = _find_address(engine, "r-backend-lead")
        vp_addr = _find_address(engine, "r-vp-eng")

        # Grant clearances
        engine.grant_clearance(
            vacant_addr,
            RoleClearance(
                role_address=vacant_addr,
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                vetting_status=VettingStatus.ACTIVE,
                compartments=frozenset(),
            ),
        )
        engine.grant_clearance(
            vp_addr,
            RoleClearance(
                role_address=vp_addr,
                max_clearance=ConfidentialityLevel.PUBLIC,
                vetting_status=VettingStatus.ACTIVE,
                compartments=frozenset(),
            ),
        )

        # Designate
        engine.designate_acting_occupant(
            vacant_role=vacant_addr,
            acting_role=vp_addr,
            designated_by=vp_addr,
        )

        # The VP's context should still have PUBLIC clearance, not CONFIDENTIAL.
        # This verifies that the acting occupant does not inherit clearance.
        ctx = engine.get_context(vp_addr)
        assert ctx.effective_clearance_level == ConfidentialityLevel.PUBLIC


# ---------------------------------------------------------------------------
# Test: Audit trail records both addresses
# ---------------------------------------------------------------------------


class TestVacancyAuditTrail:
    """Vacancy operations emit audit entries."""

    def test_designation_emits_audit(self, engine: GovernanceEngine) -> None:
        """designate_acting_occupant records an audit event."""
        vacant_addr = _find_address(engine, "r-backend-lead")
        vp_addr = _find_address(engine, "r-vp-eng")

        # This should not raise -- the audit is best-effort
        engine.designate_acting_occupant(
            vacant_role=vacant_addr,
            acting_role=vp_addr,
            designated_by=vp_addr,
        )
        # The test passes if no exception is raised. Detailed audit
        # verification would require an audit chain fixture, which is
        # covered by integration tests.

    def test_vacancy_suspension_emits_audit_details(
        self, engine: GovernanceEngine
    ) -> None:
        """When an action is blocked due to vacancy, the verdict contains
        vacancy_suspended in audit_details.
        """
        vacant_addr = _find_address(engine, "r-backend-lead")
        verdict = engine.verify_action(vacant_addr, "deploy")
        assert verdict.level == "blocked"
        assert verdict.audit_details.get("vacancy_suspended") is True
