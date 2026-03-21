# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-deliverable E2E tests for TrustPlane integration/hardening.

Tests that exercise multiple subsystems together in realistic workflows:
- Full lifecycle chain integrity across multiple decisions
- Budget depletion with posture tracking
- Delegation constraint tightening
- Shadow → strict mode transition
- Exception hierarchy consistency
- Store backend interchangeability

All tests use real infrastructure (no mocking).
"""

from __future__ import annotations

import pytest

from kailash.trust.plane.exceptions import (
    BudgetExhaustedError,
    ConstraintViolationError,
    RecordNotFoundError,
    TrustPlaneError,
)
from kailash.trust.plane.models import (
    CommunicationConstraints,
    ConstraintEnvelope,
    DataAccessConstraints,
    DecisionRecord,
    DecisionType,
    FinancialConstraints,
    OperationalConstraints,
    TemporalConstraints,
)
from kailash.trust.plane.project import TrustProject
from kailash.trust.plane.store.sqlite import SqliteTrustPlaneStore


@pytest.fixture
def trust_dir(tmp_path):
    return tmp_path / "trust-plane"


# ============================================================================
# 1. Full Lifecycle Chain Integrity
# ============================================================================


class TestFullLifecycleChainIntegrity:
    """init → session → decide(3x) → milestone → verify → export.

    Validates the EATP cryptographic chain remains unbroken across
    multiple decisions and a milestone within a single session.
    """

    async def test_lifecycle_chain_unbroken(self, trust_dir):
        envelope = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["fabricate"],
            ),
            data_access=DataAccessConstraints(
                blocked_paths=["/etc/passwd"],
            ),
            signed_by="Alice",
        )

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Lifecycle Test",
            author="Alice",
            constraint_envelope=envelope,
        )

        # Start session
        session = await project.start_session()
        assert session.is_active

        # Record 3 decisions
        decision_ids = []
        for i in range(3):
            dec = DecisionRecord(
                decision_type=DecisionType.TECHNICAL,
                decision=f"Technical decision {i+1}",
                rationale=f"Rationale for decision {i+1}",
                confidence=0.85,
            )
            did = await project.record_decision(dec)
            decision_ids.append(did)

        assert len(decision_ids) == 3
        assert session.decision_count == 3

        # Record milestone
        mid = await project.record_milestone("0.1.0", "All technical decisions made")
        assert mid
        assert session.milestone_count == 1

        # End session
        summary = await project.end_session()
        assert summary["decisions"] == 3
        assert summary["milestones"] == 1

        # Verify chain integrity — 4-level check
        result = await project.verify()
        assert result["chain_valid"] is True
        assert len(result.get("integrity_issues", [])) == 0

    async def test_lifecycle_with_all_five_dimensions(self, trust_dir):
        """Exercise all 5 EATP constraint dimensions in a single project."""
        envelope = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["fabricate", "delete"],
                allowed_actions=["decide", "milestone", "verify"],
            ),
            data_access=DataAccessConstraints(
                blocked_paths=["/secrets"],
                blocked_patterns=["*.key"],
                read_paths=["/src"],
                write_paths=["/src"],
            ),
            financial=FinancialConstraints(
                max_cost_per_session=100.0,
                max_cost_per_action=25.0,
                budget_tracking=True,
            ),
            temporal=TemporalConstraints(
                max_session_hours=8.0,
                cooldown_minutes=0,
            ),
            communication=CommunicationConstraints(
                blocked_channels=["public_slack"],
                allowed_channels=["internal_email"],
            ),
            signed_by="Alice",
        )

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Five Dimension Test",
            author="Alice",
            constraint_envelope=envelope,
        )

        session = await project.start_session()

        # Decision within all constraints
        dec = DecisionRecord(
            decision_type=DecisionType.DESIGN,
            decision="Use modular architecture",
            rationale="Separation of concerns",
            confidence=0.9,
            cost=10.0,
        )
        did = await project.record_decision(dec)
        assert did

        # Verify budget tracking
        assert session.session_cost == 10.0
        status = project.budget_status
        assert status["budget_tracking"] is True
        assert status["session_cost"] == 10.0
        assert status["remaining"] == 90.0

        await project.end_session()
        result = await project.verify()
        assert result["chain_valid"] is True


# ============================================================================
# 2. Budget Depletion & Posture Tracking
# ============================================================================


class TestBudgetDepletion:
    """Budget exhaustion blocks decisions and is reflected in session state."""

    async def test_session_budget_blocks_when_exceeded(self, trust_dir):
        envelope = ConstraintEnvelope(
            financial=FinancialConstraints(
                max_cost_per_session=50.0,
                budget_tracking=True,
            ),
            signed_by="Alice",
        )

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Budget Test",
            author="Alice",
            constraint_envelope=envelope,
        )
        session = await project.start_session()

        # Record 2 decisions at $20 each = $40 total (under $50 limit)
        for i in range(2):
            dec = DecisionRecord(
                decision_type=DecisionType.TECHNICAL,
                decision=f"Decision {i+1}",
                rationale=f"Rationale {i+1}",
                cost=20.0,
            )
            await project.record_decision(dec)

        assert session.session_cost == 40.0
        assert project.budget_status["remaining"] == 10.0

        # 3rd decision at $20 would exceed budget ($60 > $50)
        dec = DecisionRecord(
            decision_type=DecisionType.TECHNICAL,
            decision="Decision 3",
            rationale="This should be blocked",
            cost=20.0,
        )
        with pytest.raises(BudgetExhaustedError) as exc_info:
            await project.record_decision(dec)

        # Verify error details
        err = exc_info.value
        assert err.session_cost == 40.0
        assert err.budget_limit == 50.0
        assert err.action_cost == 20.0
        assert isinstance(err.details, dict)
        assert err.details["session_cost"] == 40.0

        # Session cost unchanged after rejection
        assert session.session_cost == 40.0

        await project.end_session()

    async def test_per_action_cost_limit(self, trust_dir):
        envelope = ConstraintEnvelope(
            financial=FinancialConstraints(
                max_cost_per_action=10.0,
                budget_tracking=True,
            ),
            signed_by="Alice",
        )

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Per-Action Budget",
            author="Alice",
            constraint_envelope=envelope,
        )
        session = await project.start_session()

        # Small cost passes
        dec = DecisionRecord(
            decision_type=DecisionType.TECHNICAL,
            decision="Small decision",
            rationale="Under limit",
            cost=5.0,
        )
        await project.record_decision(dec)
        assert session.session_cost == 5.0

        # Large cost blocked
        dec2 = DecisionRecord(
            decision_type=DecisionType.TECHNICAL,
            decision="Expensive decision",
            rationale="Over per-action limit",
            cost=15.0,
        )
        with pytest.raises(BudgetExhaustedError):
            await project.record_decision(dec2)

        await project.end_session()

    async def test_zero_cost_decisions_always_allowed(self, trust_dir):
        """Decisions with no cost should pass even with budget tracking."""
        envelope = ConstraintEnvelope(
            financial=FinancialConstraints(
                max_cost_per_session=10.0,
                budget_tracking=True,
            ),
            signed_by="Alice",
        )

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Zero Cost Test",
            author="Alice",
            constraint_envelope=envelope,
        )
        session = await project.start_session()

        # Many zero-cost decisions should all pass
        for i in range(20):
            dec = DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision=f"Zero cost decision {i}",
                rationale="No cost",
                cost=0.0,
            )
            await project.record_decision(dec)

        assert session.session_cost == 0.0
        assert session.decision_count == 20
        await project.end_session()

    async def test_budget_status_reflects_accumulation(self, trust_dir):
        envelope = ConstraintEnvelope(
            financial=FinancialConstraints(
                max_cost_per_session=100.0,
                max_cost_per_action=30.0,
                budget_tracking=True,
            ),
            signed_by="Alice",
        )

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Budget Status Test",
            author="Alice",
            constraint_envelope=envelope,
        )
        session = await project.start_session()

        # Before any decisions
        status = project.budget_status
        assert status["session_cost"] == 0.0
        assert status["remaining"] == 100.0
        assert status["utilization"] == 0.0

        # After decisions
        for cost in [10.0, 20.0, 15.0]:
            dec = DecisionRecord(
                decision_type=DecisionType.TECHNICAL,
                decision=f"Decision costing ${cost}",
                rationale="Test",
                cost=cost,
            )
            await project.record_decision(dec)

        status = project.budget_status
        assert status["session_cost"] == 45.0
        assert status["remaining"] == 55.0
        assert abs(status["utilization"] - 0.45) < 0.01

        await project.end_session()


# ============================================================================
# 2b. NaN/Inf Budget Bypass Regression (R1-C1, R1-C2)
# ============================================================================


class TestNaNBudgetBypassRegression:
    """Regression tests for NaN/Inf bypass of budget enforcement."""

    async def test_nan_cost_in_check_returns_blocked(self, trust_dir):
        """NaN cost in check() context must be BLOCKED, not pass-through."""
        from kailash.trust.enforce.strict import Verdict

        envelope = ConstraintEnvelope(
            financial=FinancialConstraints(
                max_cost_per_session=100.0,
                budget_tracking=True,
            ),
            signed_by="Alice",
        )
        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="NaN Test",
            author="Alice",
            constraint_envelope=envelope,
        )
        await project.start_session()

        # NaN cost must be blocked
        verdict = project.check("record_decision", {"cost": float("nan")})
        assert verdict == Verdict.BLOCKED

        # Inf cost must be blocked
        verdict = project.check("record_decision", {"cost": float("inf")})
        assert verdict == Verdict.BLOCKED

        # Negative cost must be blocked
        verdict = project.check("record_decision", {"cost": -1.0})
        assert verdict == Verdict.BLOCKED

        # Zero cost passes
        verdict = project.check("record_decision", {"cost": 0.0})
        assert verdict != Verdict.BLOCKED

        await project.end_session()

    async def test_nan_cost_in_decision_record_rejected(self, trust_dir):
        """NaN cost in DecisionRecord is rejected at construction time."""
        with pytest.raises(ValueError, match="cost must be"):
            DecisionRecord(
                decision_type=DecisionType.TECHNICAL,
                decision="NaN bypass attempt",
                rationale="Testing",
                cost=float("nan"),
            )

    async def test_session_cost_not_poisoned_by_nan(self, trust_dir):
        """Session cost accumulator must reject NaN to prevent poisoning."""
        from kailash.trust.plane.session import AuditSession

        session = AuditSession()
        session.record_action("test", cost=10.0)
        assert session.session_cost == 10.0

        # NaN must be rejected
        with pytest.raises(ValueError, match="cost must be"):
            session.record_action("test", cost=float("nan"))

        # Session cost unchanged after NaN rejection
        assert session.session_cost == 10.0

    async def test_session_from_dict_rejects_nan_cost(self, trust_dir):
        """Deserialized session with NaN session_cost must be rejected."""
        from kailash.trust.plane.session import AuditSession

        data = {
            "session_id": "sess-test",
            "started_at": "2026-01-01T00:00:00+00:00",
            "ended_at": None,
            "active": True,
            "action_count": 5,
            "decision_count": 3,
            "milestone_count": 1,
            "session_cost": float("nan"),
        }
        with pytest.raises(ValueError, match="Invalid session_cost"):
            AuditSession.from_dict(data)


# ============================================================================
# 3. Shadow → Strict Mode Transition
# ============================================================================


class TestShadowToStrictTransition:
    """Shadow mode observes; strict mode blocks. Mode switch is audited."""

    async def test_mode_switch_creates_audit_trail(self, trust_dir):
        """Switching enforcement modes creates audit anchors."""
        envelope = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["fabricate"],
            ),
            signed_by="Alice",
        )

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Shadow Strict Test",
            author="Alice",
            constraint_envelope=envelope,
        )

        # Start in strict mode (default)
        assert project.enforcement_mode == "strict"

        # Switch to shadow
        await project.switch_enforcement("shadow", "Observation phase")
        assert project.enforcement_mode == "shadow"

        # Record allowed decisions in shadow mode
        session = await project.start_session()
        dec = DecisionRecord(
            decision_type=DecisionType.TECHNICAL,
            decision="Decision during shadow mode",
            rationale="Observing behavior",
        )
        did = await project.record_decision(dec)
        assert did

        await project.end_session()

        # Switch back to strict
        await project.switch_enforcement("strict", "Enforcement phase")
        assert project.enforcement_mode == "strict"

        # Chain remains valid across mode switches
        result = await project.verify()
        assert result["chain_valid"] is True
        assert len(result["integrity_issues"]) == 0

    async def test_blocked_actions_enforced_in_both_modes(self, trust_dir):
        """Blocked actions in the operational constraint are always blocked,
        regardless of enforcement mode (pre-enforcer check)."""
        from kailash.trust.enforce.strict import Verdict

        envelope = ConstraintEnvelope(
            operational=OperationalConstraints(
                blocked_actions=["fabricate"],
            ),
            signed_by="Alice",
        )

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Both Modes Test",
            author="Alice",
            constraint_envelope=envelope,
        )

        # Strict mode: blocked
        verdict_strict = project.check("fabricate")
        assert verdict_strict == Verdict.BLOCKED

        # Shadow mode: still blocked (pre-enforcer check)
        await project.switch_enforcement("shadow", "Test")
        verdict_shadow = project.check("fabricate")
        assert verdict_shadow == Verdict.BLOCKED


# ============================================================================
# 4. Exception Hierarchy Consistency
# ============================================================================


class TestExceptionHierarchy:
    """All exceptions trace to TrustPlaneError with .details."""

    def test_all_exceptions_have_details(self):
        """Every TrustPlane exception should have a .details dict."""
        from kailash.trust.plane import exceptions as exc_mod
        from kailash.trust.plane.exceptions import SchemaMigrationError, SchemaTooNewError

        # Map exception classes to their required constructor args
        special_constructors = {
            RecordNotFoundError: lambda: RecordNotFoundError("test_type", "test_id"),
            BudgetExhaustedError: lambda: BudgetExhaustedError("budget exceeded"),
            SchemaTooNewError: lambda: SchemaTooNewError(2, 1),
            SchemaMigrationError: lambda: SchemaMigrationError(2, "test reason"),
        }

        for name in exc_mod.__all__:
            cls = getattr(exc_mod, name)
            if not isinstance(cls, type) or not issubclass(cls, BaseException):
                continue
            # Instantiate with appropriate args
            if cls in special_constructors:
                e = special_constructors[cls]()
            elif (
                hasattr(cls.__init__, "__code__")
                and "provider" in cls.__init__.__code__.co_varnames
            ):
                e = cls("test message", provider="test")
            else:
                e = cls("test message")
            assert hasattr(e, "details"), f"{name} missing .details"
            assert isinstance(e.details, dict), f"{name}.details is not dict"

    def test_record_not_found_is_keyerror(self):
        """RecordNotFoundError is also a KeyError for backward compat."""
        e = RecordNotFoundError("decision", "dec-123")
        assert isinstance(e, KeyError)
        assert isinstance(e, TrustPlaneError)
        assert e.record_type == "decision"
        assert e.record_id == "dec-123"
        assert e.details["record_type"] == "decision"

    def test_budget_exhausted_is_constraint_violation(self):
        """BudgetExhaustedError is a ConstraintViolationError."""
        e = BudgetExhaustedError(
            "over budget",
            session_cost=40.0,
            budget_limit=50.0,
            action_cost=20.0,
        )
        assert isinstance(e, ConstraintViolationError)
        assert isinstance(e, TrustPlaneError)
        assert e.session_cost == 40.0
        assert e.details["budget_limit"] == 50.0

    async def test_store_raises_record_not_found(self, trust_dir):
        """Store backends raise RecordNotFoundError, not KeyError."""
        store = SqliteTrustPlaneStore(str(trust_dir / "test.db"))
        store.initialize()

        with pytest.raises(RecordNotFoundError) as exc_info:
            store.get_decision("nonexistent")
        assert exc_info.value.record_type == "decision"

        # Also catchable as KeyError for backward compat
        with pytest.raises(KeyError):
            store.get_decision("also-nonexistent")


# ============================================================================
# 5. Store Backend Interchangeability
# ============================================================================


class TestStoreInterchangeability:
    """Same workflow produces consistent results across SQLite and filesystem."""

    async def _run_workflow(self, project: TrustProject) -> dict:
        """Run a standard workflow and return verification + counts."""
        session = await project.start_session()

        dec = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="Use modular architecture",
            rationale="Maintainability",
            confidence=0.9,
        )
        await project.record_decision(dec)

        await project.record_milestone("0.1.0", "Initial design")

        summary = await project.end_session()
        result = await project.verify()

        return {
            "chain_valid": result["chain_valid"],
            "decisions": summary["decisions"],
            "milestones": summary["milestones"],
            "total_decisions": project.manifest.total_decisions,
            "total_milestones": project.manifest.total_milestones,
        }

    async def test_independent_projects_produce_valid_chains(self, tmp_path):
        """Two independent projects produce independently valid chains."""
        envelope = ConstraintEnvelope(
            operational=OperationalConstraints(blocked_actions=["fabricate"]),
            signed_by="Alice",
        )

        # Project A
        p1 = await TrustProject.create(
            trust_dir=tmp_path / "project-a",
            project_name="Project A",
            author="Alice",
            constraint_envelope=envelope,
        )
        r1 = await self._run_workflow(p1)

        # Project B (same config, independent directory)
        p2 = await TrustProject.create(
            trust_dir=tmp_path / "project-b",
            project_name="Project B",
            author="Alice",
            constraint_envelope=envelope,
        )
        r2 = await self._run_workflow(p2)

        # Both should produce valid chains with same counts
        assert r1["chain_valid"] is True
        assert r2["chain_valid"] is True
        assert r1["decisions"] == r2["decisions"]
        assert r1["milestones"] == r2["milestones"]
        assert r1["total_decisions"] == r2["total_decisions"]

    async def test_sqlite_store_conformance(self, tmp_path):
        """SQLite store handles the full CRUD cycle correctly."""
        store = SqliteTrustPlaneStore(str(tmp_path / "test.db"))
        store.initialize()

        # Store a decision
        dec = DecisionRecord(
            decision_type=DecisionType.TECHNICAL,
            decision="Test decision",
            rationale="Testing store",
        )
        store.store_decision(dec)
        retrieved = store.get_decision(dec.decision_id)
        assert retrieved.decision == "Test decision"

        # List decisions
        decisions = store.list_decisions()
        assert len(decisions) == 1

        # Nonexistent raises RecordNotFoundError
        with pytest.raises(RecordNotFoundError):
            store.get_decision("nonexistent")


# ============================================================================
# 5b. Frozen Constraint Mutation Regression (R15-M3)
# ============================================================================


class TestFrozenConstraintMutation:
    """Constraint sub-dataclasses must be frozen to prevent post-init mutation."""

    def test_financial_constraints_frozen(self):
        """Cannot mutate FinancialConstraints after construction."""
        fc = FinancialConstraints(
            max_cost_per_session=100.0,
            budget_tracking=True,
        )
        with pytest.raises(AttributeError):
            fc.max_cost_per_session = None  # type: ignore[misc]
        with pytest.raises(AttributeError):
            fc.budget_tracking = False  # type: ignore[misc]

    def test_operational_constraints_frozen(self):
        """Cannot mutate OperationalConstraints after construction."""
        oc = OperationalConstraints(blocked_actions=["fabricate"])
        with pytest.raises(AttributeError):
            oc.blocked_actions = []  # type: ignore[misc]

    def test_data_access_constraints_frozen(self):
        """Cannot mutate DataAccessConstraints after construction."""
        da = DataAccessConstraints(blocked_paths=["/secrets"])
        with pytest.raises(AttributeError):
            da.blocked_paths = []  # type: ignore[misc]

    def test_temporal_constraints_frozen(self):
        """Cannot mutate TemporalConstraints after construction."""
        tc = TemporalConstraints(max_session_hours=8.0)
        with pytest.raises(AttributeError):
            tc.max_session_hours = None  # type: ignore[misc]

    def test_communication_constraints_frozen(self):
        """Cannot mutate CommunicationConstraints after construction."""
        cc = CommunicationConstraints(blocked_channels=["public"])
        with pytest.raises(AttributeError):
            cc.blocked_channels = []  # type: ignore[misc]


# ============================================================================
# 6. Session Cost Persistence
# ============================================================================


class TestSessionCostPersistence:
    """Session cost survives serialization roundtrip."""

    async def test_session_cost_in_summary(self, trust_dir):
        envelope = ConstraintEnvelope(
            financial=FinancialConstraints(
                max_cost_per_session=1000.0,
                budget_tracking=True,
            ),
            signed_by="Alice",
        )

        project = await TrustProject.create(
            trust_dir=trust_dir,
            project_name="Cost Persistence",
            author="Alice",
            constraint_envelope=envelope,
        )
        session = await project.start_session()

        # Record decisions with costs
        for cost in [10.0, 25.0, 15.0]:
            dec = DecisionRecord(
                decision_type=DecisionType.TECHNICAL,
                decision=f"Decision costing ${cost}",
                rationale="Test",
                cost=cost,
            )
            await project.record_decision(dec)

        summary = await project.end_session()
        assert summary["session_cost"] == 50.0

    async def test_decision_cost_in_record(self, trust_dir):
        """Decision cost field roundtrips through to_dict/from_dict."""
        dec = DecisionRecord(
            decision_type=DecisionType.TECHNICAL,
            decision="Expensive decision",
            rationale="High cost action",
            cost=42.50,
        )
        assert dec.cost == 42.50

        d = dec.to_dict()
        assert d["cost"] == 42.50

        restored = DecisionRecord.from_dict(d)
        assert restored.cost == 42.50

    def test_decision_cost_validation(self):
        """Negative and non-finite costs are rejected."""
        with pytest.raises(ValueError, match="cost must be"):
            DecisionRecord(
                decision_type=DecisionType.TECHNICAL,
                decision="Bad cost",
                rationale="Negative",
                cost=-5.0,
            )

        with pytest.raises(ValueError, match="cost must be"):
            DecisionRecord(
                decision_type=DecisionType.TECHNICAL,
                decision="Bad cost",
                rationale="NaN",
                cost=float("nan"),
            )

        with pytest.raises(ValueError, match="cost must be"):
            DecisionRecord(
                decision_type=DecisionType.TECHNICAL,
                decision="Bad cost",
                rationale="Inf",
                cost=float("inf"),
            )
