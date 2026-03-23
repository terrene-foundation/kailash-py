# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Property-based tests for monotonic tightening using Hypothesis (TODO-7024).

Uses Hypothesis to generate random envelope pairs and verify algebraic
invariants of the intersection operation:
  1. Intersection is tighter than both inputs (monotonicity)
  2. Intersection is commutative (a ^ b == b ^ a)
  3. Intersection is associative ((a ^ b) ^ c == a ^ (b ^ c))
  4. Intersection is idempotent (a ^ a == a)
  5. No NaN/Inf in output (safety guarantee)
  6. validate_tightening accepts intersection as valid child
"""

from __future__ import annotations

import math

from hypothesis import given, settings, strategies as st

from kailash.trust.pact.config import (
    CONFIDENTIALITY_ORDER,
    CommunicationConstraintConfig,
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
)
from kailash.trust.pact.envelopes import (
    MonotonicTighteningError,
    RoleEnvelope,
    intersect_envelopes,
)

# ---------------------------------------------------------------------------
# Hypothesis Strategies -- generate valid constraint configs
# ---------------------------------------------------------------------------

# Canonical action vocabulary that all generated envelopes draw from.
# Using a shared pool ensures intersections are non-trivially non-empty.
_ALL_ACTIONS = ["read", "write", "approve", "delete", "execute", "create", "update"]

# Canonical channel vocabulary.
_ALL_CHANNELS = ["internal", "email", "external", "api", "slack"]

# Canonical path vocabulary for data access constraints.
_ALL_READ_PATHS = [
    "/data/public",
    "/data/team",
    "/data/dept",
    "/data/org",
    "/data/classified",
]
_ALL_WRITE_PATHS = ["/data/team", "/data/dept", "/data/org", "/data/classified"]

# Canonical blocked data types.
_ALL_BLOCKED_DATA_TYPES = ["pii", "financial_records", "health_records", "credentials"]


@st.composite
def financial_constraints(draw: st.DrawFn) -> FinancialConstraintConfig:
    """Generate a valid FinancialConstraintConfig with finite values."""
    return FinancialConstraintConfig(
        max_spend_usd=draw(
            st.floats(
                min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False
            )
        ),
        api_cost_budget_usd=draw(
            st.one_of(
                st.none(),
                st.floats(
                    min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False
                ),
            )
        ),
        requires_approval_above_usd=draw(
            st.one_of(
                st.none(),
                st.floats(
                    min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False
                ),
            )
        ),
        reasoning_required=draw(st.booleans()),
    )


@st.composite
def operational_constraints(draw: st.DrawFn) -> OperationalConstraintConfig:
    """Generate a valid OperationalConstraintConfig."""
    allowed = draw(
        st.lists(st.sampled_from(_ALL_ACTIONS), min_size=1, max_size=5, unique=True)
    )
    blocked = draw(
        st.lists(st.sampled_from(_ALL_ACTIONS), min_size=0, max_size=3, unique=True)
    )
    max_per_day = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=10000)))
    max_per_hour = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=1000)))
    window_type = draw(st.sampled_from(["fixed", "rolling"]))
    return OperationalConstraintConfig(
        allowed_actions=sorted(allowed),
        blocked_actions=sorted(blocked),
        max_actions_per_day=max_per_day,
        max_actions_per_hour=max_per_hour,
        rate_limit_window_type=window_type,
        reasoning_required=draw(st.booleans()),
    )


@st.composite
def temporal_constraints(draw: st.DrawFn) -> TemporalConstraintConfig:
    """Generate a valid TemporalConstraintConfig."""
    has_hours = draw(st.booleans())
    if has_hours:
        start_h = draw(st.integers(min_value=0, max_value=23))
        start_m = draw(st.integers(min_value=0, max_value=59))
        end_h = draw(st.integers(min_value=0, max_value=23))
        end_m = draw(st.integers(min_value=0, max_value=59))
        start = f"{start_h:02d}:{start_m:02d}"
        end = f"{end_h:02d}:{end_m:02d}"
    else:
        start = None
        end = None

    blackouts = draw(
        st.lists(
            st.sampled_from(["2026-01-01", "2026-03-15", "2026-06-01", "2026-12-25"]),
            min_size=0,
            max_size=3,
            unique=True,
        )
    )
    return TemporalConstraintConfig(
        active_hours_start=start,
        active_hours_end=end,
        timezone="UTC",
        blackout_periods=sorted(blackouts),
        reasoning_required=draw(st.booleans()),
    )


@st.composite
def data_access_constraints(draw: st.DrawFn) -> DataAccessConstraintConfig:
    """Generate a valid DataAccessConstraintConfig."""
    return DataAccessConstraintConfig(
        read_paths=sorted(
            draw(
                st.lists(
                    st.sampled_from(_ALL_READ_PATHS),
                    min_size=0,
                    max_size=4,
                    unique=True,
                )
            )
        ),
        write_paths=sorted(
            draw(
                st.lists(
                    st.sampled_from(_ALL_WRITE_PATHS),
                    min_size=0,
                    max_size=3,
                    unique=True,
                )
            )
        ),
        blocked_data_types=sorted(
            draw(
                st.lists(
                    st.sampled_from(_ALL_BLOCKED_DATA_TYPES),
                    min_size=0,
                    max_size=3,
                    unique=True,
                )
            )
        ),
        reasoning_required=draw(st.booleans()),
    )


@st.composite
def communication_constraints(draw: st.DrawFn) -> CommunicationConstraintConfig:
    """Generate a valid CommunicationConstraintConfig."""
    return CommunicationConstraintConfig(
        internal_only=draw(st.booleans()),
        allowed_channels=sorted(
            draw(
                st.lists(
                    st.sampled_from(_ALL_CHANNELS), min_size=1, max_size=4, unique=True
                )
            )
        ),
        external_requires_approval=draw(st.booleans()),
        reasoning_required=draw(st.booleans()),
    )


@st.composite
def envelope_config(draw: st.DrawFn) -> ConstraintEnvelopeConfig:
    """Generate a valid ConstraintEnvelopeConfig."""
    return ConstraintEnvelopeConfig(
        id=f"test-{draw(st.integers(min_value=1, max_value=999999))}",
        description="Property test envelope",
        confidentiality_clearance=draw(st.sampled_from(list(ConfidentialityLevel))),
        financial=draw(financial_constraints()),
        operational=draw(operational_constraints()),
        temporal=draw(temporal_constraints()),
        data_access=draw(data_access_constraints()),
        communication=draw(communication_constraints()),
        max_delegation_depth=draw(
            st.one_of(st.none(), st.integers(min_value=1, max_value=100))
        ),
    )


# ---------------------------------------------------------------------------
# Property 1: Intersection is tighter than both inputs
# ---------------------------------------------------------------------------


class TestIntersectionMonotonicity:
    """Intersection result must be at most as permissive as either input."""

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_financial_tighter_than_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Financial: result.max_spend_usd <= min(a, b)."""
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert a.financial is not None
        assert b.financial is not None
        assert result.financial.max_spend_usd <= a.financial.max_spend_usd
        assert result.financial.max_spend_usd <= b.financial.max_spend_usd

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_financial_api_budget_tighter_than_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Financial: result.api_cost_budget_usd <= min(a, b) when both are set."""
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert a.financial is not None
        assert b.financial is not None
        if (
            a.financial.api_cost_budget_usd is not None
            and b.financial.api_cost_budget_usd is not None
        ):
            assert result.financial.api_cost_budget_usd is not None
            assert (
                result.financial.api_cost_budget_usd <= a.financial.api_cost_budget_usd
            )
            assert (
                result.financial.api_cost_budget_usd <= b.financial.api_cost_budget_usd
            )
        elif a.financial.api_cost_budget_usd is not None:
            # Only a has a limit -- result adopts it
            assert (
                result.financial.api_cost_budget_usd == a.financial.api_cost_budget_usd
            )
        elif b.financial.api_cost_budget_usd is not None:
            # Only b has a limit -- result adopts it
            assert (
                result.financial.api_cost_budget_usd == b.financial.api_cost_budget_usd
            )

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_financial_approval_threshold_tighter_than_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Financial: result.requires_approval_above_usd <= min(a, b) when both set."""
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert a.financial is not None
        assert b.financial is not None
        if (
            a.financial.requires_approval_above_usd is not None
            and b.financial.requires_approval_above_usd is not None
        ):
            assert result.financial.requires_approval_above_usd is not None
            assert (
                result.financial.requires_approval_above_usd
                <= a.financial.requires_approval_above_usd
            )
            assert (
                result.financial.requires_approval_above_usd
                <= b.financial.requires_approval_above_usd
            )

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_reasoning_required_tighter_than_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Reasoning: if either input requires reasoning, result must too."""
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert a.financial is not None
        assert b.financial is not None
        if a.financial.reasoning_required or b.financial.reasoning_required:
            assert result.financial.reasoning_required

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_operational_allowed_actions_subset_of_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Operational: result.allowed_actions is subset of both inputs (minus blocked)."""
        result = intersect_envelopes(a, b)
        result_actions = set(result.operational.allowed_actions)
        a_actions = set(a.operational.allowed_actions)
        b_actions = set(b.operational.allowed_actions)
        # Result must be subset of both original allowed sets
        # (blocked actions from either side are also removed)
        assert result_actions <= a_actions | set()
        assert result_actions <= b_actions | set()
        # More precisely: result is intersection of allowed minus union of blocked
        expected_allowed = (a_actions & b_actions) - (
            set(a.operational.blocked_actions) | set(b.operational.blocked_actions)
        )
        assert result_actions == expected_allowed

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_operational_blocked_actions_superset_of_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Operational: result.blocked_actions is superset of both inputs (union)."""
        result = intersect_envelopes(a, b)
        result_blocked = set(result.operational.blocked_actions)
        a_blocked = set(a.operational.blocked_actions)
        b_blocked = set(b.operational.blocked_actions)
        assert a_blocked <= result_blocked
        assert b_blocked <= result_blocked

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_operational_rate_limits_tighter(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Operational: rate limits are min() of both inputs."""
        result = intersect_envelopes(a, b)
        if (
            a.operational.max_actions_per_day is not None
            and b.operational.max_actions_per_day is not None
        ):
            assert result.operational.max_actions_per_day is not None
            assert (
                result.operational.max_actions_per_day
                <= a.operational.max_actions_per_day
            )
            assert (
                result.operational.max_actions_per_day
                <= b.operational.max_actions_per_day
            )
        if (
            a.operational.max_actions_per_hour is not None
            and b.operational.max_actions_per_hour is not None
        ):
            assert result.operational.max_actions_per_hour is not None
            assert (
                result.operational.max_actions_per_hour
                <= a.operational.max_actions_per_hour
            )
            assert (
                result.operational.max_actions_per_hour
                <= b.operational.max_actions_per_hour
            )

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_communication_channels_subset_of_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Communication: result.allowed_channels is subset of both inputs."""
        result = intersect_envelopes(a, b)
        result_channels = set(result.communication.allowed_channels)
        a_channels = set(a.communication.allowed_channels)
        b_channels = set(b.communication.allowed_channels)
        assert result_channels <= a_channels
        assert result_channels <= b_channels

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_communication_internal_only_tighter(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Communication: if either input is internal_only, result is too."""
        result = intersect_envelopes(a, b)
        if a.communication.internal_only or b.communication.internal_only:
            assert result.communication.internal_only

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_confidentiality_tighter_than_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Confidentiality: result clearance <= min(a, b) in ordering."""
        result = intersect_envelopes(a, b)
        result_order = CONFIDENTIALITY_ORDER[result.confidentiality_clearance]
        a_order = CONFIDENTIALITY_ORDER[a.confidentiality_clearance]
        b_order = CONFIDENTIALITY_ORDER[b.confidentiality_clearance]
        assert result_order <= a_order
        assert result_order <= b_order

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_data_access_read_paths_subset_of_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Data access: result.read_paths is subset of both inputs."""
        result = intersect_envelopes(a, b)
        assert set(result.data_access.read_paths) <= set(a.data_access.read_paths)
        assert set(result.data_access.read_paths) <= set(b.data_access.read_paths)

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_data_access_write_paths_subset_of_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Data access: result.write_paths is subset of both inputs."""
        result = intersect_envelopes(a, b)
        assert set(result.data_access.write_paths) <= set(a.data_access.write_paths)
        assert set(result.data_access.write_paths) <= set(b.data_access.write_paths)

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_data_access_blocked_types_superset_of_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Data access: result.blocked_data_types is superset of both inputs."""
        result = intersect_envelopes(a, b)
        assert set(a.data_access.blocked_data_types) <= set(
            result.data_access.blocked_data_types
        )
        assert set(b.data_access.blocked_data_types) <= set(
            result.data_access.blocked_data_types
        )

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_temporal_blackout_superset_of_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Temporal: result.blackout_periods is superset of both inputs."""
        result = intersect_envelopes(a, b)
        assert set(a.temporal.blackout_periods) <= set(result.temporal.blackout_periods)
        assert set(b.temporal.blackout_periods) <= set(result.temporal.blackout_periods)

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_delegation_depth_tighter_than_both(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        """Delegation: result.max_delegation_depth <= min(a, b) when both set."""
        result = intersect_envelopes(a, b)
        if a.max_delegation_depth is not None and b.max_delegation_depth is not None:
            assert result.max_delegation_depth is not None
            assert result.max_delegation_depth <= a.max_delegation_depth
            assert result.max_delegation_depth <= b.max_delegation_depth
        elif a.max_delegation_depth is not None:
            assert result.max_delegation_depth == a.max_delegation_depth
        elif b.max_delegation_depth is not None:
            assert result.max_delegation_depth == b.max_delegation_depth


# ---------------------------------------------------------------------------
# Property 2: Intersection is commutative
# ---------------------------------------------------------------------------


class TestIntersectionCommutativity:
    """intersect_envelopes(a, b) produces the same constraints as intersect_envelopes(b, a).

    Note: the id and description fields differ (they include input IDs which swap),
    so we compare only the constraint dimensions.
    """

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_financial_commutative(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        ab = intersect_envelopes(a, b)
        ba = intersect_envelopes(b, a)
        assert ab.financial is not None
        assert ba.financial is not None
        assert ab.financial.max_spend_usd == ba.financial.max_spend_usd
        assert ab.financial.api_cost_budget_usd == ba.financial.api_cost_budget_usd
        assert (
            ab.financial.requires_approval_above_usd
            == ba.financial.requires_approval_above_usd
        )
        assert ab.financial.reasoning_required == ba.financial.reasoning_required

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_operational_commutative(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        ab = intersect_envelopes(a, b)
        ba = intersect_envelopes(b, a)
        assert set(ab.operational.allowed_actions) == set(
            ba.operational.allowed_actions
        )
        assert set(ab.operational.blocked_actions) == set(
            ba.operational.blocked_actions
        )
        assert ab.operational.max_actions_per_day == ba.operational.max_actions_per_day
        assert (
            ab.operational.max_actions_per_hour == ba.operational.max_actions_per_hour
        )
        assert ab.operational.reasoning_required == ba.operational.reasoning_required

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_communication_commutative(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        ab = intersect_envelopes(a, b)
        ba = intersect_envelopes(b, a)
        assert set(ab.communication.allowed_channels) == set(
            ba.communication.allowed_channels
        )
        assert ab.communication.internal_only == ba.communication.internal_only
        assert (
            ab.communication.external_requires_approval
            == ba.communication.external_requires_approval
        )
        assert (
            ab.communication.reasoning_required == ba.communication.reasoning_required
        )

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_confidentiality_commutative(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        ab = intersect_envelopes(a, b)
        ba = intersect_envelopes(b, a)
        assert ab.confidentiality_clearance == ba.confidentiality_clearance

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_data_access_commutative(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        ab = intersect_envelopes(a, b)
        ba = intersect_envelopes(b, a)
        assert set(ab.data_access.read_paths) == set(ba.data_access.read_paths)
        assert set(ab.data_access.write_paths) == set(ba.data_access.write_paths)
        assert set(ab.data_access.blocked_data_types) == set(
            ba.data_access.blocked_data_types
        )

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_temporal_commutative(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        ab = intersect_envelopes(a, b)
        ba = intersect_envelopes(b, a)
        assert set(ab.temporal.blackout_periods) == set(ba.temporal.blackout_periods)
        assert ab.temporal.reasoning_required == ba.temporal.reasoning_required

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_delegation_depth_commutative(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        ab = intersect_envelopes(a, b)
        ba = intersect_envelopes(b, a)
        assert ab.max_delegation_depth == ba.max_delegation_depth


# ---------------------------------------------------------------------------
# Property 3: Intersection is associative
# ---------------------------------------------------------------------------


class TestIntersectionAssociativity:
    """(a ^ b) ^ c produces the same constraints as a ^ (b ^ c).

    Tests structural dimensions where associativity must hold.
    """

    @given(a=envelope_config(), b=envelope_config(), c=envelope_config())
    @settings(max_examples=200, deadline=None)
    def test_financial_associative(
        self,
        a: ConstraintEnvelopeConfig,
        b: ConstraintEnvelopeConfig,
        c: ConstraintEnvelopeConfig,
    ) -> None:
        ab_c = intersect_envelopes(intersect_envelopes(a, b), c)
        a_bc = intersect_envelopes(a, intersect_envelopes(b, c))
        assert ab_c.financial is not None
        assert a_bc.financial is not None
        assert ab_c.financial.max_spend_usd == a_bc.financial.max_spend_usd
        assert ab_c.financial.api_cost_budget_usd == a_bc.financial.api_cost_budget_usd
        assert (
            ab_c.financial.requires_approval_above_usd
            == a_bc.financial.requires_approval_above_usd
        )
        assert ab_c.financial.reasoning_required == a_bc.financial.reasoning_required

    @given(a=envelope_config(), b=envelope_config(), c=envelope_config())
    @settings(max_examples=200, deadline=None)
    def test_operational_associative(
        self,
        a: ConstraintEnvelopeConfig,
        b: ConstraintEnvelopeConfig,
        c: ConstraintEnvelopeConfig,
    ) -> None:
        ab_c = intersect_envelopes(intersect_envelopes(a, b), c)
        a_bc = intersect_envelopes(a, intersect_envelopes(b, c))
        assert set(ab_c.operational.allowed_actions) == set(
            a_bc.operational.allowed_actions
        )
        assert set(ab_c.operational.blocked_actions) == set(
            a_bc.operational.blocked_actions
        )
        assert (
            ab_c.operational.max_actions_per_day == a_bc.operational.max_actions_per_day
        )
        assert (
            ab_c.operational.max_actions_per_hour
            == a_bc.operational.max_actions_per_hour
        )

    @given(a=envelope_config(), b=envelope_config(), c=envelope_config())
    @settings(max_examples=200, deadline=None)
    def test_communication_associative(
        self,
        a: ConstraintEnvelopeConfig,
        b: ConstraintEnvelopeConfig,
        c: ConstraintEnvelopeConfig,
    ) -> None:
        ab_c = intersect_envelopes(intersect_envelopes(a, b), c)
        a_bc = intersect_envelopes(a, intersect_envelopes(b, c))
        assert set(ab_c.communication.allowed_channels) == set(
            a_bc.communication.allowed_channels
        )
        assert ab_c.communication.internal_only == a_bc.communication.internal_only
        assert (
            ab_c.communication.external_requires_approval
            == a_bc.communication.external_requires_approval
        )

    @given(a=envelope_config(), b=envelope_config(), c=envelope_config())
    @settings(max_examples=200, deadline=None)
    def test_confidentiality_associative(
        self,
        a: ConstraintEnvelopeConfig,
        b: ConstraintEnvelopeConfig,
        c: ConstraintEnvelopeConfig,
    ) -> None:
        ab_c = intersect_envelopes(intersect_envelopes(a, b), c)
        a_bc = intersect_envelopes(a, intersect_envelopes(b, c))
        assert ab_c.confidentiality_clearance == a_bc.confidentiality_clearance

    @given(a=envelope_config(), b=envelope_config(), c=envelope_config())
    @settings(max_examples=200, deadline=None)
    def test_data_access_associative(
        self,
        a: ConstraintEnvelopeConfig,
        b: ConstraintEnvelopeConfig,
        c: ConstraintEnvelopeConfig,
    ) -> None:
        ab_c = intersect_envelopes(intersect_envelopes(a, b), c)
        a_bc = intersect_envelopes(a, intersect_envelopes(b, c))
        assert set(ab_c.data_access.read_paths) == set(a_bc.data_access.read_paths)
        assert set(ab_c.data_access.write_paths) == set(a_bc.data_access.write_paths)
        assert set(ab_c.data_access.blocked_data_types) == set(
            a_bc.data_access.blocked_data_types
        )

    @given(a=envelope_config(), b=envelope_config(), c=envelope_config())
    @settings(max_examples=200, deadline=None)
    def test_temporal_associative(
        self,
        a: ConstraintEnvelopeConfig,
        b: ConstraintEnvelopeConfig,
        c: ConstraintEnvelopeConfig,
    ) -> None:
        ab_c = intersect_envelopes(intersect_envelopes(a, b), c)
        a_bc = intersect_envelopes(a, intersect_envelopes(b, c))
        assert set(ab_c.temporal.blackout_periods) == set(
            a_bc.temporal.blackout_periods
        )

    @given(a=envelope_config(), b=envelope_config(), c=envelope_config())
    @settings(max_examples=200, deadline=None)
    def test_delegation_depth_associative(
        self,
        a: ConstraintEnvelopeConfig,
        b: ConstraintEnvelopeConfig,
        c: ConstraintEnvelopeConfig,
    ) -> None:
        ab_c = intersect_envelopes(intersect_envelopes(a, b), c)
        a_bc = intersect_envelopes(a, intersect_envelopes(b, c))
        assert ab_c.max_delegation_depth == a_bc.max_delegation_depth


# ---------------------------------------------------------------------------
# Property 4: Intersection is idempotent (a ^ a == a)
# ---------------------------------------------------------------------------


class TestIntersectionIdempotency:
    """intersect_envelopes(a, a) produces the same constraints as a."""

    @given(a=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_financial_idempotent(self, a: ConstraintEnvelopeConfig) -> None:
        result = intersect_envelopes(a, a)
        assert result.financial is not None
        assert a.financial is not None
        assert result.financial.max_spend_usd == a.financial.max_spend_usd
        assert result.financial.api_cost_budget_usd == a.financial.api_cost_budget_usd
        assert (
            result.financial.requires_approval_above_usd
            == a.financial.requires_approval_above_usd
        )
        assert result.financial.reasoning_required == a.financial.reasoning_required

    @given(a=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_operational_idempotent(self, a: ConstraintEnvelopeConfig) -> None:
        result = intersect_envelopes(a, a)
        # After intersection with itself, allowed_actions = allowed - blocked
        expected_allowed = set(a.operational.allowed_actions) - set(
            a.operational.blocked_actions
        )
        assert set(result.operational.allowed_actions) == expected_allowed
        assert set(result.operational.blocked_actions) == set(
            a.operational.blocked_actions
        )
        assert (
            result.operational.max_actions_per_day == a.operational.max_actions_per_day
        )
        assert (
            result.operational.max_actions_per_hour
            == a.operational.max_actions_per_hour
        )

    @given(a=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_communication_idempotent(self, a: ConstraintEnvelopeConfig) -> None:
        result = intersect_envelopes(a, a)
        assert set(result.communication.allowed_channels) == set(
            a.communication.allowed_channels
        )
        assert result.communication.internal_only == a.communication.internal_only
        assert (
            result.communication.external_requires_approval
            == a.communication.external_requires_approval
        )

    @given(a=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_confidentiality_idempotent(self, a: ConstraintEnvelopeConfig) -> None:
        result = intersect_envelopes(a, a)
        assert result.confidentiality_clearance == a.confidentiality_clearance

    @given(a=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_data_access_idempotent(self, a: ConstraintEnvelopeConfig) -> None:
        result = intersect_envelopes(a, a)
        assert set(result.data_access.read_paths) == set(a.data_access.read_paths)
        assert set(result.data_access.write_paths) == set(a.data_access.write_paths)
        assert set(result.data_access.blocked_data_types) == set(
            a.data_access.blocked_data_types
        )

    @given(a=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_delegation_depth_idempotent(self, a: ConstraintEnvelopeConfig) -> None:
        result = intersect_envelopes(a, a)
        assert result.max_delegation_depth == a.max_delegation_depth


# ---------------------------------------------------------------------------
# Property 5: No NaN/Inf in output
# ---------------------------------------------------------------------------


class TestNoNanInfInOutput:
    """All numeric fields in the intersection result must be finite."""

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_financial_all_finite(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert math.isfinite(result.financial.max_spend_usd)
        if result.financial.api_cost_budget_usd is not None:
            assert math.isfinite(result.financial.api_cost_budget_usd)
        if result.financial.requires_approval_above_usd is not None:
            assert math.isfinite(result.financial.requires_approval_above_usd)

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_operational_rate_limits_finite(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        result = intersect_envelopes(a, b)
        if result.operational.max_actions_per_day is not None:
            assert math.isfinite(result.operational.max_actions_per_day)
        if result.operational.max_actions_per_hour is not None:
            assert math.isfinite(result.operational.max_actions_per_hour)

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_delegation_depth_finite(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        result = intersect_envelopes(a, b)
        if result.max_delegation_depth is not None:
            # max_delegation_depth is int, but verify it is not a sneaky float
            assert isinstance(result.max_delegation_depth, int)


# ---------------------------------------------------------------------------
# Property 6: validate_tightening accepts intersection as valid child
# ---------------------------------------------------------------------------


class TestIntersectionPassesTightening:
    """If child is the intersection of parent and something, tightening must pass.

    This is the key property connecting intersection to governance: the
    intersection of any parent envelope with any other envelope always produces
    a valid child under monotonic tightening.
    """

    @given(parent=envelope_config(), other=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_intersection_is_valid_child(
        self, parent: ConstraintEnvelopeConfig, other: ConstraintEnvelopeConfig
    ) -> None:
        """intersect(parent, other) always passes validate_tightening(parent, ...)."""
        child = intersect_envelopes(parent, other)
        # This must not raise MonotonicTighteningError
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)

    @given(a=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_self_intersection_is_valid_child(
        self, a: ConstraintEnvelopeConfig
    ) -> None:
        """intersect(a, a) always passes validate_tightening(a, ...)."""
        child = intersect_envelopes(a, a)
        RoleEnvelope.validate_tightening(parent_envelope=a, child_envelope=child)

    @given(
        parent=envelope_config(),
        other1=envelope_config(),
        other2=envelope_config(),
    )
    @settings(max_examples=200, deadline=None)
    def test_double_intersection_is_valid_child(
        self,
        parent: ConstraintEnvelopeConfig,
        other1: ConstraintEnvelopeConfig,
        other2: ConstraintEnvelopeConfig,
    ) -> None:
        """intersect(intersect(parent, x), y) always passes validate_tightening(parent, ...)."""
        child = intersect_envelopes(intersect_envelopes(parent, other1), other2)
        RoleEnvelope.validate_tightening(parent_envelope=parent, child_envelope=child)


# ---------------------------------------------------------------------------
# Property 7: Rolling window type is the more restrictive choice
# ---------------------------------------------------------------------------


class TestRollingWindowTightening:
    """If either envelope uses rolling rate limit windows, the result must too.

    Rolling windows are more restrictive than fixed windows because they
    prevent burst-then-idle patterns that fixed windows allow.
    """

    @given(a=envelope_config(), b=envelope_config())
    @settings(max_examples=500, deadline=None)
    def test_rolling_dominates_fixed(
        self, a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
    ) -> None:
        result = intersect_envelopes(a, b)
        if (
            a.operational.rate_limit_window_type == "rolling"
            or b.operational.rate_limit_window_type == "rolling"
        ):
            assert result.operational.rate_limit_window_type == "rolling"
