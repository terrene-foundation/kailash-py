# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for the three-layer envelope model (M3: TODO-3001 through TODO-3006).

Covers:
- TODO-3001: intersect_envelopes -- per-dimension intersection with deny-overrides
- TODO-3002: RoleEnvelope -- standing constraints with monotonic tightening
- TODO-3003: TaskEnvelope -- ephemeral narrowing with expiry
- TODO-3004: compute_effective_envelope -- ancestor chain intersection
- TODO-3005: default_envelope_for_posture -- conservative defaults per trust posture
- TODO-3006: check_degenerate_envelope -- overly tight detection
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pact.build.config.schema import (
    CommunicationConstraintConfig,
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
    TrustPostureLevel,
)
from pact.governance.envelopes import (
    RoleEnvelope,
    TaskEnvelope,
    check_degenerate_envelope,
    compute_effective_envelope,
    default_envelope_for_posture,
    intersect_envelopes,
    MonotonicTighteningError,
)


# ---------------------------------------------------------------------------
# Helpers -- build constraint configs for tests
# ---------------------------------------------------------------------------


def _make_envelope(
    *,
    envelope_id: str = "test",
    max_spend: float = 1000.0,
    allowed_actions: list[str] | None = None,
    blocked_actions: list[str] | None = None,
    max_actions_per_day: int | None = None,
    active_hours_start: str | None = None,
    active_hours_end: str | None = None,
    blackout_periods: list[str] | None = None,
    read_paths: list[str] | None = None,
    write_paths: list[str] | None = None,
    confidentiality: ConfidentialityLevel = ConfidentialityLevel.CONFIDENTIAL,
    internal_only: bool = False,
    allowed_channels: list[str] | None = None,
    max_delegation_depth: int | None = None,
    financial: FinancialConstraintConfig | None = "default",  # type: ignore[assignment]
    api_cost_budget_usd: float | None = None,
    requires_approval_above_usd: float | None = None,
) -> ConstraintEnvelopeConfig:
    """Helper to build a ConstraintEnvelopeConfig with sensible defaults."""
    if financial == "default":
        fin = FinancialConstraintConfig(
            max_spend_usd=max_spend,
            api_cost_budget_usd=api_cost_budget_usd,
            requires_approval_above_usd=requires_approval_above_usd,
        )
    else:
        fin = financial

    return ConstraintEnvelopeConfig(
        id=envelope_id,
        confidentiality_clearance=confidentiality,
        financial=fin,
        operational=OperationalConstraintConfig(
            allowed_actions=allowed_actions or [],
            blocked_actions=blocked_actions or [],
            max_actions_per_day=max_actions_per_day,
        ),
        temporal=TemporalConstraintConfig(
            active_hours_start=active_hours_start,
            active_hours_end=active_hours_end,
            blackout_periods=blackout_periods or [],
        ),
        data_access=DataAccessConstraintConfig(
            read_paths=read_paths or [],
            write_paths=write_paths or [],
        ),
        communication=CommunicationConstraintConfig(
            internal_only=internal_only,
            allowed_channels=allowed_channels or [],
        ),
        max_delegation_depth=max_delegation_depth,
    )


# ===========================================================================
# TODO-3001: intersect_envelopes
# ===========================================================================


class TestIntersectEnvelopesFinancial:
    """Financial dimension: min() of numeric limits."""

    def test_min_spend(self) -> None:
        a = _make_envelope(max_spend=1000.0)
        b = _make_envelope(max_spend=500.0)
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert result.financial.max_spend_usd == 500.0

    def test_min_api_budget(self) -> None:
        a = _make_envelope(max_spend=1000.0, api_cost_budget_usd=200.0)
        b = _make_envelope(max_spend=1000.0, api_cost_budget_usd=100.0)
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert result.financial.api_cost_budget_usd == 100.0

    def test_min_approval_threshold(self) -> None:
        a = _make_envelope(max_spend=1000.0, requires_approval_above_usd=500.0)
        b = _make_envelope(max_spend=1000.0, requires_approval_above_usd=200.0)
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert result.financial.requires_approval_above_usd == 200.0

    def test_one_none_api_budget_uses_other(self) -> None:
        a = _make_envelope(max_spend=1000.0, api_cost_budget_usd=200.0)
        b = _make_envelope(max_spend=1000.0, api_cost_budget_usd=None)
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert result.financial.api_cost_budget_usd == 200.0

    def test_both_none_api_budget_stays_none(self) -> None:
        a = _make_envelope(max_spend=1000.0, api_cost_budget_usd=None)
        b = _make_envelope(max_spend=1000.0, api_cost_budget_usd=None)
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert result.financial.api_cost_budget_usd is None

    def test_reasoning_required_union(self) -> None:
        """If either side requires reasoning, intersection does too."""
        a = _make_envelope(max_spend=1000.0)
        b = _make_envelope(max_spend=1000.0)
        a_fin = FinancialConstraintConfig(max_spend_usd=1000.0, reasoning_required=True)
        a_with_reasoning = a.model_copy(update={"financial": a_fin})
        result = intersect_envelopes(a_with_reasoning, b)
        assert result.financial is not None
        assert result.financial.reasoning_required is True

    def test_one_financial_none_returns_other(self) -> None:
        """If one envelope has no financial dimension, use the other's."""
        a = _make_envelope(max_spend=500.0)
        b = _make_envelope(financial=None)
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert result.financial.max_spend_usd == 500.0

    def test_both_financial_none_stays_none(self) -> None:
        a = _make_envelope(financial=None)
        b = _make_envelope(financial=None)
        result = intersect_envelopes(a, b)
        assert result.financial is None


class TestIntersectEnvelopesOperational:
    """Operational dimension: set intersection of allowed; set union of blocked."""

    def test_allowed_actions_intersection(self) -> None:
        a = _make_envelope(allowed_actions=["read", "write", "deploy"])
        b = _make_envelope(allowed_actions=["read", "write", "audit"])
        result = intersect_envelopes(a, b)
        assert set(result.operational.allowed_actions) == {"read", "write"}

    def test_blocked_actions_union(self) -> None:
        a = _make_envelope(blocked_actions=["delete"])
        b = _make_envelope(blocked_actions=["deploy"])
        result = intersect_envelopes(a, b)
        assert set(result.operational.blocked_actions) == {"delete", "deploy"}

    def test_min_max_actions_per_day(self) -> None:
        a = _make_envelope(max_actions_per_day=100)
        b = _make_envelope(max_actions_per_day=50)
        result = intersect_envelopes(a, b)
        assert result.operational.max_actions_per_day == 50

    def test_one_none_rate_limit_uses_other(self) -> None:
        a = _make_envelope(max_actions_per_day=100)
        b = _make_envelope(max_actions_per_day=None)
        result = intersect_envelopes(a, b)
        assert result.operational.max_actions_per_day == 100

    def test_blocked_overrides_allowed(self) -> None:
        """When composed allowed and blocked sets overlap, blocked takes precedence."""
        a = _make_envelope(allowed_actions=["deploy", "read"], blocked_actions=[])
        b = _make_envelope(allowed_actions=["deploy", "read"], blocked_actions=["deploy"])
        result = intersect_envelopes(a, b)
        assert "deploy" not in result.operational.allowed_actions
        assert "deploy" in result.operational.blocked_actions

    def test_empty_allowed_stays_empty(self) -> None:
        """Empty allowed_actions means nothing explicitly allowed."""
        a = _make_envelope(allowed_actions=[])
        b = _make_envelope(allowed_actions=["read", "write"])
        result = intersect_envelopes(a, b)
        assert result.operational.allowed_actions == []

    def test_reasoning_required_union(self) -> None:
        a_op = OperationalConstraintConfig(allowed_actions=[], reasoning_required=True)
        b_op = OperationalConstraintConfig(allowed_actions=[], reasoning_required=False)
        a = _make_envelope().model_copy(update={"operational": a_op})
        b = _make_envelope().model_copy(update={"operational": b_op})
        result = intersect_envelopes(a, b)
        assert result.operational.reasoning_required is True


class TestIntersectEnvelopesTemporal:
    """Temporal dimension: overlap of active windows; union of blackout periods."""

    def test_overlapping_active_hours(self) -> None:
        a = _make_envelope(active_hours_start="06:00", active_hours_end="20:00")
        b = _make_envelope(active_hours_start="09:00", active_hours_end="18:00")
        result = intersect_envelopes(a, b)
        assert result.temporal.active_hours_start == "09:00"
        assert result.temporal.active_hours_end == "18:00"

    def test_blackout_union(self) -> None:
        a = _make_envelope(blackout_periods=["2026-01-01"])
        b = _make_envelope(blackout_periods=["2026-12-25"])
        result = intersect_envelopes(a, b)
        assert set(result.temporal.blackout_periods) == {"2026-01-01", "2026-12-25"}

    def test_one_none_window_uses_other(self) -> None:
        a = _make_envelope(active_hours_start="09:00", active_hours_end="17:00")
        b = _make_envelope(active_hours_start=None, active_hours_end=None)
        result = intersect_envelopes(a, b)
        assert result.temporal.active_hours_start == "09:00"
        assert result.temporal.active_hours_end == "17:00"

    def test_both_none_window_stays_none(self) -> None:
        a = _make_envelope(active_hours_start=None, active_hours_end=None)
        b = _make_envelope(active_hours_start=None, active_hours_end=None)
        result = intersect_envelopes(a, b)
        assert result.temporal.active_hours_start is None
        assert result.temporal.active_hours_end is None

    def test_blackout_dedup(self) -> None:
        """Duplicate blackout periods are deduplicated."""
        a = _make_envelope(blackout_periods=["2026-01-01", "2026-12-25"])
        b = _make_envelope(blackout_periods=["2026-01-01"])
        result = intersect_envelopes(a, b)
        # Each period should appear only once
        assert result.temporal.blackout_periods.count("2026-01-01") == 1


class TestIntersectEnvelopesDataAccess:
    """Data access dimension: intersection of paths; min of confidentiality ceiling."""

    def test_read_paths_intersection(self) -> None:
        a = _make_envelope(read_paths=["/data/reports", "/data/logs", "/data/config"])
        b = _make_envelope(read_paths=["/data/reports", "/data/config"])
        result = intersect_envelopes(a, b)
        assert set(result.data_access.read_paths) == {"/data/reports", "/data/config"}

    def test_write_paths_intersection(self) -> None:
        a = _make_envelope(write_paths=["/data/output", "/data/logs"])
        b = _make_envelope(write_paths=["/data/output"])
        result = intersect_envelopes(a, b)
        assert set(result.data_access.write_paths) == {"/data/output"}

    def test_min_confidentiality_clearance(self) -> None:
        a = _make_envelope(confidentiality=ConfidentialityLevel.SECRET)
        b = _make_envelope(confidentiality=ConfidentialityLevel.RESTRICTED)
        result = intersect_envelopes(a, b)
        assert result.confidentiality_clearance == ConfidentialityLevel.RESTRICTED

    def test_blocked_data_types_union(self) -> None:
        a_da = DataAccessConstraintConfig(blocked_data_types=["pii"])
        b_da = DataAccessConstraintConfig(blocked_data_types=["financial_records"])
        a = _make_envelope().model_copy(update={"data_access": a_da})
        b = _make_envelope().model_copy(update={"data_access": b_da})
        result = intersect_envelopes(a, b)
        assert set(result.data_access.blocked_data_types) == {"pii", "financial_records"}


class TestIntersectEnvelopesCommunication:
    """Communication dimension: intersection of channels; tighter internal_only."""

    def test_allowed_channels_intersection(self) -> None:
        a = _make_envelope(allowed_channels=["email", "slack", "teams"])
        b = _make_envelope(allowed_channels=["slack", "teams", "sms"])
        result = intersect_envelopes(a, b)
        assert set(result.communication.allowed_channels) == {"slack", "teams"}

    def test_internal_only_true_wins(self) -> None:
        """If either side is internal_only, result is internal_only."""
        a = _make_envelope(internal_only=False)
        b = _make_envelope(internal_only=True)
        result = intersect_envelopes(a, b)
        assert result.communication.internal_only is True

    def test_external_requires_approval_true_wins(self) -> None:
        a_comm = CommunicationConstraintConfig(external_requires_approval=True)
        b_comm = CommunicationConstraintConfig(external_requires_approval=False)
        a = _make_envelope().model_copy(update={"communication": a_comm})
        b = _make_envelope().model_copy(update={"communication": b_comm})
        result = intersect_envelopes(a, b)
        assert result.communication.external_requires_approval is True


class TestIntersectEnvelopesDelegationDepth:
    """max_delegation_depth: min of both values."""

    def test_min_depth(self) -> None:
        a = _make_envelope(max_delegation_depth=5)
        b = _make_envelope(max_delegation_depth=3)
        result = intersect_envelopes(a, b)
        assert result.max_delegation_depth == 3

    def test_one_none_depth_uses_other(self) -> None:
        a = _make_envelope(max_delegation_depth=5)
        b = _make_envelope(max_delegation_depth=None)
        result = intersect_envelopes(a, b)
        assert result.max_delegation_depth == 5

    def test_both_none_stays_none(self) -> None:
        a = _make_envelope(max_delegation_depth=None)
        b = _make_envelope(max_delegation_depth=None)
        result = intersect_envelopes(a, b)
        assert result.max_delegation_depth is None


class TestIntersectEnvelopesAbsentDimensions:
    """Absent (None or default) dimensions are treated as maximally permissive."""

    def test_none_financial_passes_through(self) -> None:
        """When one side has financial=None (no financial capability), the other's is used."""
        a = _make_envelope(financial=None)
        b = _make_envelope(max_spend=750.0)
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert result.financial.max_spend_usd == 750.0

    def test_result_id_is_synthetic(self) -> None:
        """The result envelope gets a synthetic ID (not from either input)."""
        a = _make_envelope(envelope_id="env-a")
        b = _make_envelope(envelope_id="env-b")
        result = intersect_envelopes(a, b)
        assert result.id != ""
        assert "intersect" in result.id.lower() or result.id.startswith("ix-")


class TestIntersectEnvelopesIdempotent:
    """intersect(A, A) should equal A on all dimensions."""

    def test_self_intersection_financial(self) -> None:
        a = _make_envelope(max_spend=500.0, api_cost_budget_usd=100.0)
        result = intersect_envelopes(a, a)
        assert result.financial is not None
        assert result.financial.max_spend_usd == 500.0
        assert result.financial.api_cost_budget_usd == 100.0

    def test_self_intersection_operational(self) -> None:
        a = _make_envelope(allowed_actions=["read", "write"], blocked_actions=["delete"])
        result = intersect_envelopes(a, a)
        assert set(result.operational.allowed_actions) == {"read", "write"}
        assert set(result.operational.blocked_actions) == {"delete"}


class TestIntersectEnvelopesCommutative:
    """intersect(A, B) == intersect(B, A) on all dimensions."""

    def test_commutative(self) -> None:
        a = _make_envelope(
            envelope_id="env-a",
            max_spend=1000.0,
            allowed_actions=["read", "write"],
            blocked_actions=["delete"],
            active_hours_start="06:00",
            active_hours_end="20:00",
            read_paths=["/data/a", "/data/b"],
            allowed_channels=["email", "slack"],
            confidentiality=ConfidentialityLevel.SECRET,
        )
        b = _make_envelope(
            envelope_id="env-b",
            max_spend=500.0,
            allowed_actions=["read", "deploy"],
            blocked_actions=["audit"],
            active_hours_start="09:00",
            active_hours_end="18:00",
            read_paths=["/data/b", "/data/c"],
            allowed_channels=["slack", "teams"],
            confidentiality=ConfidentialityLevel.CONFIDENTIAL,
        )
        r1 = intersect_envelopes(a, b)
        r2 = intersect_envelopes(b, a)

        assert r1.financial is not None and r2.financial is not None
        assert r1.financial.max_spend_usd == r2.financial.max_spend_usd
        assert set(r1.operational.allowed_actions) == set(r2.operational.allowed_actions)
        assert set(r1.operational.blocked_actions) == set(r2.operational.blocked_actions)
        assert r1.temporal.active_hours_start == r2.temporal.active_hours_start
        assert r1.temporal.active_hours_end == r2.temporal.active_hours_end
        assert set(r1.data_access.read_paths) == set(r2.data_access.read_paths)
        assert set(r1.communication.allowed_channels) == set(r2.communication.allowed_channels)
        assert r1.confidentiality_clearance == r2.confidentiality_clearance


# ===========================================================================
# TODO-3002: RoleEnvelope
# ===========================================================================


class TestRoleEnvelope:
    """RoleEnvelope: standing operating boundary for a direct report."""

    def test_create_role_envelope(self) -> None:
        env = _make_envelope(max_spend=500.0)
        role_env = RoleEnvelope(
            id="re-001",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-D1-R1",
            envelope=env,
        )
        assert role_env.id == "re-001"
        assert role_env.defining_role_address == "D1-R1"
        assert role_env.target_role_address == "D1-R1-D1-R1"
        assert role_env.envelope.financial is not None
        assert role_env.envelope.financial.max_spend_usd == 500.0
        assert role_env.version == 1

    def test_frozen(self) -> None:
        env = _make_envelope(max_spend=500.0)
        role_env = RoleEnvelope(
            id="re-001",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-D1-R1",
            envelope=env,
        )
        with pytest.raises(AttributeError):
            role_env.version = 2  # type: ignore[misc]

    def test_timestamps_set(self) -> None:
        before = datetime.now(UTC)
        env = _make_envelope(max_spend=500.0)
        role_env = RoleEnvelope(
            id="re-001",
            defining_role_address="D1-R1",
            target_role_address="D1-R1-D1-R1",
            envelope=env,
        )
        after = datetime.now(UTC)
        assert before <= role_env.created_at <= after
        assert before <= role_env.modified_at <= after


# ===========================================================================
# TODO-3003: TaskEnvelope
# ===========================================================================


class TestTaskEnvelope:
    """TaskEnvelope: ephemeral narrowing of a RoleEnvelope."""

    def test_create_task_envelope(self) -> None:
        expires = datetime.now(UTC) + timedelta(hours=1)
        env = _make_envelope(max_spend=100.0)
        task_env = TaskEnvelope(
            id="te-001",
            task_id="task-abc",
            parent_envelope_id="re-001",
            envelope=env,
            expires_at=expires,
        )
        assert task_env.id == "te-001"
        assert task_env.task_id == "task-abc"
        assert task_env.parent_envelope_id == "re-001"

    def test_frozen(self) -> None:
        expires = datetime.now(UTC) + timedelta(hours=1)
        env = _make_envelope(max_spend=100.0)
        task_env = TaskEnvelope(
            id="te-001",
            task_id="task-abc",
            parent_envelope_id="re-001",
            envelope=env,
            expires_at=expires,
        )
        with pytest.raises(AttributeError):
            task_env.task_id = "other"  # type: ignore[misc]

    def test_is_expired_false_when_future(self) -> None:
        expires = datetime.now(UTC) + timedelta(hours=1)
        env = _make_envelope(max_spend=100.0)
        task_env = TaskEnvelope(
            id="te-001",
            task_id="task-abc",
            parent_envelope_id="re-001",
            envelope=env,
            expires_at=expires,
        )
        assert task_env.is_expired is False

    def test_is_expired_true_when_past(self) -> None:
        expires = datetime.now(UTC) - timedelta(hours=1)
        env = _make_envelope(max_spend=100.0)
        task_env = TaskEnvelope(
            id="te-001",
            task_id="task-abc",
            parent_envelope_id="re-001",
            envelope=env,
            expires_at=expires,
        )
        assert task_env.is_expired is True

    def test_created_at_default(self) -> None:
        before = datetime.now(UTC)
        expires = datetime.now(UTC) + timedelta(hours=1)
        env = _make_envelope(max_spend=100.0)
        task_env = TaskEnvelope(
            id="te-001",
            task_id="task-abc",
            parent_envelope_id="re-001",
            envelope=env,
            expires_at=expires,
        )
        after = datetime.now(UTC)
        assert before <= task_env.created_at <= after


# ===========================================================================
# TODO-3004: compute_effective_envelope
# ===========================================================================


class TestComputeEffectiveEnvelope:
    """Compute effective envelope by walking the ancestor chain."""

    def test_single_role_envelope(self) -> None:
        """One role envelope at the target address."""
        env = _make_envelope(max_spend=500.0)
        role_envs = {
            "D1-R1": RoleEnvelope(
                id="re-001",
                defining_role_address="D1-R1",
                target_role_address="D1-R1",
                envelope=env,
            ),
        }
        result = compute_effective_envelope("D1-R1", role_envs)
        assert result is not None
        assert result.financial is not None
        assert result.financial.max_spend_usd == 500.0

    def test_ancestor_chain_intersection(self) -> None:
        """Two envelopes in ancestor chain get intersected."""
        parent_env = _make_envelope(max_spend=1000.0, allowed_actions=["read", "write"])
        child_env = _make_envelope(max_spend=500.0, allowed_actions=["read", "write", "deploy"])
        role_envs = {
            "D1-R1": RoleEnvelope(
                id="re-001",
                defining_role_address="D1-R1",
                target_role_address="D1-R1",
                envelope=parent_env,
            ),
            "D1-R1-D1-R1": RoleEnvelope(
                id="re-002",
                defining_role_address="D1-R1",
                target_role_address="D1-R1-D1-R1",
                envelope=child_env,
            ),
        }
        result = compute_effective_envelope("D1-R1-D1-R1", role_envs)
        assert result is not None
        assert result.financial is not None
        # min(1000, 500) = 500
        assert result.financial.max_spend_usd == 500.0
        # intersection of ["read", "write"] and ["read", "write", "deploy"]
        assert set(result.operational.allowed_actions) == {"read", "write"}

    def test_org_envelope_applied(self) -> None:
        """Org-level envelope is included in the intersection."""
        org_env = _make_envelope(max_spend=200.0)
        role_env = _make_envelope(max_spend=500.0)
        role_envs = {
            "D1-R1": RoleEnvelope(
                id="re-001",
                defining_role_address="D1-R1",
                target_role_address="D1-R1",
                envelope=role_env,
            ),
        }
        result = compute_effective_envelope("D1-R1", role_envs, org_envelope=org_env)
        assert result is not None
        assert result.financial is not None
        assert result.financial.max_spend_usd == 200.0

    def test_task_envelope_narrows_further(self) -> None:
        """Active task envelope intersects with effective role envelope."""
        role_env = _make_envelope(max_spend=500.0, allowed_actions=["read", "write"])
        task_env_cfg = _make_envelope(max_spend=100.0, allowed_actions=["read"])
        role_envs = {
            "D1-R1": RoleEnvelope(
                id="re-001",
                defining_role_address="D1-R1",
                target_role_address="D1-R1",
                envelope=role_env,
            ),
        }
        task = TaskEnvelope(
            id="te-001",
            task_id="task-abc",
            parent_envelope_id="re-001",
            envelope=task_env_cfg,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        result = compute_effective_envelope("D1-R1", role_envs, task_envelope=task)
        assert result is not None
        assert result.financial is not None
        assert result.financial.max_spend_usd == 100.0
        assert set(result.operational.allowed_actions) == {"read"}

    def test_expired_task_envelope_ignored(self) -> None:
        """Expired task envelope is not applied."""
        role_env = _make_envelope(max_spend=500.0)
        task_env_cfg = _make_envelope(max_spend=100.0)
        role_envs = {
            "D1-R1": RoleEnvelope(
                id="re-001",
                defining_role_address="D1-R1",
                target_role_address="D1-R1",
                envelope=role_env,
            ),
        }
        task = TaskEnvelope(
            id="te-002",
            task_id="task-xyz",
            parent_envelope_id="re-001",
            envelope=task_env_cfg,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        result = compute_effective_envelope("D1-R1", role_envs, task_envelope=task)
        assert result is not None
        assert result.financial is not None
        # Task was expired, so only role envelope applies
        assert result.financial.max_spend_usd == 500.0

    def test_no_envelopes_returns_none(self) -> None:
        """No envelopes at all returns None (maximally permissive)."""
        result = compute_effective_envelope("D1-R1", {})
        assert result is None

    def test_deep_chain_intersection(self) -> None:
        """Three-level deep chain: org -> D1-R1 -> D1-R1-D1-R1 -> D1-R1-D1-R1-T1-R1."""
        org_env = _make_envelope(max_spend=10000.0)
        l1_env = _make_envelope(max_spend=5000.0)
        l2_env = _make_envelope(max_spend=1000.0)
        l3_env = _make_envelope(max_spend=500.0)
        role_envs = {
            "D1-R1": RoleEnvelope(
                id="re-001",
                defining_role_address="D1-R1",
                target_role_address="D1-R1",
                envelope=l1_env,
            ),
            "D1-R1-D1-R1": RoleEnvelope(
                id="re-002",
                defining_role_address="D1-R1",
                target_role_address="D1-R1-D1-R1",
                envelope=l2_env,
            ),
            "D1-R1-D1-R1-T1-R1": RoleEnvelope(
                id="re-003",
                defining_role_address="D1-R1-D1-R1",
                target_role_address="D1-R1-D1-R1-T1-R1",
                envelope=l3_env,
            ),
        }
        result = compute_effective_envelope("D1-R1-D1-R1-T1-R1", role_envs, org_envelope=org_env)
        assert result is not None
        assert result.financial is not None
        # min(10000, 5000, 1000, 500) = 500
        assert result.financial.max_spend_usd == 500.0


# ===========================================================================
# TODO-3005: default_envelope_for_posture
# ===========================================================================


class TestDefaultEnvelopeForPosture:
    """Conservative defaults calibrated to trust posture level."""

    def test_pseudo_agent_no_financial(self) -> None:
        env = default_envelope_for_posture(TrustPostureLevel.PSEUDO_AGENT)
        assert env.financial is not None
        assert env.financial.max_spend_usd == 0.0

    def test_pseudo_agent_public_only(self) -> None:
        env = default_envelope_for_posture(TrustPostureLevel.PSEUDO_AGENT)
        assert env.confidentiality_clearance == ConfidentialityLevel.PUBLIC

    def test_pseudo_agent_internal_only(self) -> None:
        env = default_envelope_for_posture(TrustPostureLevel.PSEUDO_AGENT)
        assert env.communication.internal_only is True

    def test_supervised_low_financial(self) -> None:
        env = default_envelope_for_posture(TrustPostureLevel.SUPERVISED)
        assert env.financial is not None
        assert env.financial.max_spend_usd == 100.0

    def test_supervised_restricted(self) -> None:
        env = default_envelope_for_posture(TrustPostureLevel.SUPERVISED)
        assert env.confidentiality_clearance == ConfidentialityLevel.RESTRICTED

    def test_shared_planning_moderate_financial(self) -> None:
        env = default_envelope_for_posture(TrustPostureLevel.SHARED_PLANNING)
        assert env.financial is not None
        assert env.financial.max_spend_usd == 1000.0

    def test_shared_planning_confidential(self) -> None:
        env = default_envelope_for_posture(TrustPostureLevel.SHARED_PLANNING)
        assert env.confidentiality_clearance == ConfidentialityLevel.CONFIDENTIAL

    def test_continuous_insight_higher_financial(self) -> None:
        env = default_envelope_for_posture(TrustPostureLevel.CONTINUOUS_INSIGHT)
        assert env.financial is not None
        assert env.financial.max_spend_usd == 10000.0

    def test_continuous_insight_secret(self) -> None:
        env = default_envelope_for_posture(TrustPostureLevel.CONTINUOUS_INSIGHT)
        assert env.confidentiality_clearance == ConfidentialityLevel.SECRET

    def test_delegated_highest_financial(self) -> None:
        env = default_envelope_for_posture(TrustPostureLevel.DELEGATED)
        assert env.financial is not None
        assert env.financial.max_spend_usd == 100000.0

    def test_delegated_top_secret(self) -> None:
        env = default_envelope_for_posture(TrustPostureLevel.DELEGATED)
        assert env.confidentiality_clearance == ConfidentialityLevel.TOP_SECRET

    def test_posture_ordering_tightens_monotonically(self) -> None:
        """Higher postures produce more permissive envelopes (higher spend)."""
        postures = [
            TrustPostureLevel.PSEUDO_AGENT,
            TrustPostureLevel.SUPERVISED,
            TrustPostureLevel.SHARED_PLANNING,
            TrustPostureLevel.CONTINUOUS_INSIGHT,
            TrustPostureLevel.DELEGATED,
        ]
        spends = []
        for p in postures:
            env = default_envelope_for_posture(p)
            assert env.financial is not None
            spends.append(env.financial.max_spend_usd)
        # Each posture should have a higher or equal spend than the one before
        for i in range(1, len(spends)):
            assert spends[i] >= spends[i - 1], (
                f"{postures[i].value} spend {spends[i]} < "
                f"{postures[i - 1].value} spend {spends[i - 1]}"
            )

    def test_all_postures_return_valid_envelope(self) -> None:
        for posture in TrustPostureLevel:
            env = default_envelope_for_posture(posture)
            assert isinstance(env, ConstraintEnvelopeConfig)
            assert env.id != ""


# ===========================================================================
# TODO-3006: check_degenerate_envelope
# ===========================================================================


class TestCheckDegenerateEnvelope:
    """Detect envelopes so tight that no meaningful action is possible."""

    def test_normal_envelope_no_warnings(self) -> None:
        env = _make_envelope(
            max_spend=1000.0,
            allowed_actions=["read", "write"],
            read_paths=["/data"],
            allowed_channels=["slack"],
        )
        warnings = check_degenerate_envelope(env)
        assert warnings == []

    def test_zero_spend_warns(self) -> None:
        env = _make_envelope(max_spend=0.0)
        warnings = check_degenerate_envelope(env)
        assert any("financial" in w.lower() for w in warnings)

    def test_no_allowed_actions_warns(self) -> None:
        env = _make_envelope(allowed_actions=[])
        # Note: empty allowed_actions alone may not warn unless a functional
        # minimum is provided. With the default functional minimum, empty
        # allowed actions should produce a warning.
        warnings = check_degenerate_envelope(env)
        # At minimum, should flag that operational dimension is degenerate
        assert any("operational" in w.lower() or "action" in w.lower() for w in warnings)

    def test_no_channels_warns(self) -> None:
        env = _make_envelope(allowed_channels=[], internal_only=True)
        warnings = check_degenerate_envelope(env)
        assert any("communication" in w.lower() or "channel" in w.lower() for w in warnings)

    def test_custom_functional_minimum(self) -> None:
        """With a specific functional minimum, warn when below 20% of it."""
        effective = _make_envelope(max_spend=10.0)
        minimum = _make_envelope(max_spend=1000.0)
        warnings = check_degenerate_envelope(effective, functional_minimum=minimum)
        # 10 / 1000 = 1% < 20%, so financial should be flagged
        assert any("financial" in w.lower() for w in warnings)

    def test_above_threshold_no_financial_warning(self) -> None:
        """Spend above 20% of functional minimum should not warn."""
        effective = _make_envelope(max_spend=300.0)
        minimum = _make_envelope(max_spend=1000.0)
        warnings = check_degenerate_envelope(effective, functional_minimum=minimum)
        financial_warnings = [w for w in warnings if "financial" in w.lower()]
        assert financial_warnings == []

    def test_none_financial_not_degenerate(self) -> None:
        """No financial dimension means the agent simply has no financial capability."""
        env = _make_envelope(
            financial=None,
            allowed_actions=["read"],
            read_paths=["/data"],
            allowed_channels=["slack"],
        )
        warnings = check_degenerate_envelope(env)
        # Should not produce financial warnings (absence != degenerate)
        financial_warnings = [w for w in warnings if "financial" in w.lower()]
        assert financial_warnings == []

    def test_returns_list_of_strings(self) -> None:
        env = _make_envelope(max_spend=0.0, allowed_actions=[], allowed_channels=[])
        warnings = check_degenerate_envelope(env)
        assert isinstance(warnings, list)
        for w in warnings:
            assert isinstance(w, str)


# ===========================================================================
# Monotonic Tightening Validation (cross-cutting TODO-3002 invariant)
# ===========================================================================


class TestMonotonicTightening:
    """Verify that RoleEnvelope.validate_tightening rejects non-tightening envelopes."""

    def test_tighter_child_is_valid(self) -> None:
        """A child envelope tighter than the parent should be accepted."""
        parent = _make_envelope(max_spend=1000.0, allowed_actions=["read", "write"])
        child = _make_envelope(max_spend=500.0, allowed_actions=["read"])
        # Should not raise
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_equal_is_valid(self) -> None:
        """Equal envelopes satisfy monotonic tightening."""
        env = _make_envelope(max_spend=500.0, allowed_actions=["read"])
        RoleEnvelope.validate_tightening(parent_envelope=env, child_envelope=env)

    def test_looser_child_raises(self) -> None:
        """A child envelope looser than parent violates monotonic tightening."""
        parent = _make_envelope(max_spend=500.0)
        child = _make_envelope(max_spend=1000.0)
        with pytest.raises(MonotonicTighteningError):
            RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    def test_looser_confidentiality_raises(self) -> None:
        parent = _make_envelope(confidentiality=ConfidentialityLevel.RESTRICTED)
        child = _make_envelope(confidentiality=ConfidentialityLevel.SECRET)
        with pytest.raises(MonotonicTighteningError):
            RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)
