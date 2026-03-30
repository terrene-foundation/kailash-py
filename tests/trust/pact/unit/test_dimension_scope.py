# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for dimension-scoped delegations (#170).

Covers:
- DelegationRecord.dimension_scope field (default, custom, validation)
- DelegationRecord serialization (to_signing_payload, to_dict, from_dict)
- intersect_envelopes() with dimension_scope parameter
- Backward compatibility (missing dimension_scope in from_dict)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kailash.trust.chain import (
    ALL_DIMENSIONS,
    VALID_DIMENSION_NAMES,
    DelegationRecord,
)
from kailash.trust.pact.config import (
    CommunicationConstraintConfig,
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
)
from kailash.trust.pact.envelopes import intersect_envelopes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_delegation(
    *,
    delegation_id: str = "del-001",
    dimension_scope: frozenset[str] | None = None,
) -> DelegationRecord:
    """Build a minimal DelegationRecord with optional dimension_scope."""
    kwargs: dict = {
        "id": delegation_id,
        "delegator_id": "agent-parent",
        "delegatee_id": "agent-child",
        "task_id": "task-001",
        "capabilities_delegated": ["read", "write"],
        "constraint_subset": ["max_spend:100"],
        "delegated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "signature": "sig-placeholder",
    }
    if dimension_scope is not None:
        kwargs["dimension_scope"] = dimension_scope
    return DelegationRecord(**kwargs)


def _make_envelope(
    *,
    envelope_id: str = "env-test",
    max_spend: float = 1000.0,
    allowed_actions: list[str] | None = None,
    read_paths: list[str] | None = None,
    write_paths: list[str] | None = None,
    internal_only: bool = False,
    allowed_channels: list[str] | None = None,
    active_hours_start: str | None = None,
    active_hours_end: str | None = None,
) -> ConstraintEnvelopeConfig:
    """Build a ConstraintEnvelopeConfig with sensible defaults."""
    return ConstraintEnvelopeConfig(
        id=envelope_id,
        confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        financial=FinancialConstraintConfig(max_spend_usd=max_spend),
        operational=OperationalConstraintConfig(
            allowed_actions=allowed_actions or ["read", "write", "deploy"],
        ),
        temporal=TemporalConstraintConfig(
            active_hours_start=active_hours_start,
            active_hours_end=active_hours_end,
        ),
        data_access=DataAccessConstraintConfig(
            read_paths=read_paths or ["/data/public", "/data/team"],
            write_paths=write_paths or ["/data/team"],
        ),
        communication=CommunicationConstraintConfig(
            internal_only=internal_only,
            allowed_channels=allowed_channels or ["internal", "email", "slack"],
        ),
    )


# ---------------------------------------------------------------------------
# DelegationRecord -- dimension_scope field
# ---------------------------------------------------------------------------


class TestDelegationRecordDimensionScope:
    """Tests for DelegationRecord.dimension_scope field."""

    def test_default_is_all_dimensions(self) -> None:
        """Default dimension_scope should be ALL_DIMENSIONS (all 5)."""
        d = _make_delegation()
        assert d.dimension_scope == ALL_DIMENSIONS
        assert len(d.dimension_scope) == 5

    def test_custom_scope(self) -> None:
        """Custom dimension_scope should be preserved."""
        scope = frozenset({"financial", "operational"})
        d = _make_delegation(dimension_scope=scope)
        assert d.dimension_scope == scope
        assert "financial" in d.dimension_scope
        assert "operational" in d.dimension_scope
        assert "temporal" not in d.dimension_scope

    def test_single_dimension_scope(self) -> None:
        """A scope with a single dimension should work."""
        scope = frozenset({"financial"})
        d = _make_delegation(dimension_scope=scope)
        assert d.dimension_scope == scope
        assert len(d.dimension_scope) == 1

    def test_invalid_dimension_raises(self) -> None:
        """Unknown dimension names should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid dimension_scope"):
            _make_delegation(dimension_scope=frozenset({"financial", "bogus"}))

    def test_empty_scope_raises(self) -> None:
        """Empty dimension_scope should raise ValueError."""
        with pytest.raises(ValueError, match="at least one dimension"):
            _make_delegation(dimension_scope=frozenset())

    def test_set_coerced_to_frozenset(self) -> None:
        """Passing a plain set should be coerced to frozenset."""
        d = DelegationRecord(
            id="del-coerce",
            delegator_id="a",
            delegatee_id="b",
            task_id="t",
            capabilities_delegated=[],
            constraint_subset=[],
            delegated_at=datetime(2026, 1, 1, tzinfo=UTC),
            signature="s",
            dimension_scope={"financial", "temporal"},  # type: ignore[arg-type]
        )
        assert isinstance(d.dimension_scope, frozenset)
        assert d.dimension_scope == frozenset({"financial", "temporal"})

    def test_valid_dimension_names_constant(self) -> None:
        """VALID_DIMENSION_NAMES should contain exactly the 5 canonical names."""
        assert VALID_DIMENSION_NAMES == frozenset(
            {"financial", "operational", "temporal", "data_access", "communication"}
        )


# ---------------------------------------------------------------------------
# DelegationRecord -- serialization
# ---------------------------------------------------------------------------


class TestDelegationRecordSerialization:
    """Tests for DelegationRecord to_signing_payload, to_dict, from_dict."""

    def test_to_signing_payload_includes_dimension_scope(self) -> None:
        """to_signing_payload() must include dimension_scope as a sorted list."""
        scope = frozenset({"operational", "financial"})
        d = _make_delegation(dimension_scope=scope)
        payload = d.to_signing_payload()
        assert "dimension_scope" in payload
        assert payload["dimension_scope"] == ["financial", "operational"]

    def test_to_signing_payload_all_dimensions_sorted(self) -> None:
        """Default all-dimensions scope should produce all 5 sorted."""
        d = _make_delegation()
        payload = d.to_signing_payload()
        assert payload["dimension_scope"] == sorted(ALL_DIMENSIONS)

    def test_to_dict_includes_dimension_scope(self) -> None:
        """to_dict() must include dimension_scope as a sorted list."""
        scope = frozenset({"data_access", "communication"})
        d = _make_delegation(dimension_scope=scope)
        data = d.to_dict()
        assert "dimension_scope" in data
        assert data["dimension_scope"] == ["communication", "data_access"]

    def test_from_dict_with_dimension_scope(self) -> None:
        """from_dict() should deserialize dimension_scope correctly."""
        d = _make_delegation(dimension_scope=frozenset({"financial", "temporal"}))
        data = d.to_dict()
        restored = DelegationRecord.from_dict(data)
        assert restored.dimension_scope == frozenset({"financial", "temporal"})

    def test_from_dict_missing_dimension_scope_defaults_to_all(self) -> None:
        """from_dict() with missing dimension_scope should default to ALL_DIMENSIONS."""
        d = _make_delegation()
        data = d.to_dict()
        # Simulate legacy data without dimension_scope
        del data["dimension_scope"]
        restored = DelegationRecord.from_dict(data)
        assert restored.dimension_scope == ALL_DIMENSIONS

    def test_roundtrip_preserves_scope(self) -> None:
        """Roundtrip through to_dict/from_dict preserves dimension_scope."""
        for scope in [
            ALL_DIMENSIONS,
            frozenset({"financial"}),
            frozenset({"operational", "data_access", "communication"}),
        ]:
            d = _make_delegation(dimension_scope=scope)
            restored = DelegationRecord.from_dict(d.to_dict())
            assert restored.dimension_scope == scope, f"Failed for scope={scope}"

    def test_signing_payload_deterministic(self) -> None:
        """Signing payload dimension_scope must be deterministically sorted."""
        scope = frozenset({"communication", "temporal", "financial"})
        d = _make_delegation(dimension_scope=scope)
        p1 = d.to_signing_payload()
        p2 = d.to_signing_payload()
        assert p1["dimension_scope"] == p2["dimension_scope"]
        assert p1["dimension_scope"] == ["communication", "financial", "temporal"]


# ---------------------------------------------------------------------------
# intersect_envelopes -- dimension_scope parameter
# ---------------------------------------------------------------------------


class TestIntersectEnvelopesDimensionScope:
    """Tests for intersect_envelopes() with dimension_scope parameter."""

    def test_no_scope_intersects_all_dimensions(self) -> None:
        """Without dimension_scope, all dimensions are intersected."""
        parent = _make_envelope(
            envelope_id="parent",
            max_spend=1000.0,
            allowed_actions=["read", "write", "deploy"],
            read_paths=["/data/public", "/data/team"],
            allowed_channels=["internal", "email", "slack"],
        )
        child = _make_envelope(
            envelope_id="child",
            max_spend=500.0,
            allowed_actions=["read", "write"],
            read_paths=["/data/public"],
            allowed_channels=["internal", "email"],
        )

        result = intersect_envelopes(parent, child)

        # All dimensions intersected
        assert result.financial.max_spend_usd == 500.0
        assert sorted(result.operational.allowed_actions) == ["read", "write"]
        assert result.data_access.read_paths == ["/data/public"]
        assert sorted(result.communication.allowed_channels) == ["email", "internal"]

    def test_financial_only_scope(self) -> None:
        """With financial-only scope, only financial is intersected from child."""
        parent = _make_envelope(
            envelope_id="parent",
            max_spend=1000.0,
            allowed_actions=["read", "write", "deploy"],
            read_paths=["/data/public", "/data/team"],
            allowed_channels=["internal", "email", "slack"],
        )
        child = _make_envelope(
            envelope_id="child",
            max_spend=500.0,
            allowed_actions=["read"],  # More restrictive but NOT scoped
            read_paths=["/data/public"],  # More restrictive but NOT scoped
            allowed_channels=["internal"],  # More restrictive but NOT scoped
        )

        result = intersect_envelopes(
            parent, child, dimension_scope=frozenset({"financial"})
        )

        # Financial: intersected (child wins because tighter)
        assert result.financial.max_spend_usd == 500.0

        # Operational: inherited from parent (NOT intersected)
        assert sorted(result.operational.allowed_actions) == [
            "deploy",
            "read",
            "write",
        ]

        # Data access: inherited from parent
        assert sorted(result.data_access.read_paths) == ["/data/public", "/data/team"]

        # Communication: inherited from parent
        assert sorted(result.communication.allowed_channels) == [
            "email",
            "internal",
            "slack",
        ]

    def test_operational_and_data_access_scope(self) -> None:
        """With operational+data_access scope, only those two are intersected."""
        parent = _make_envelope(
            envelope_id="parent",
            max_spend=1000.0,
            allowed_actions=["read", "write", "deploy"],
            read_paths=["/data/public", "/data/team"],
        )
        child = _make_envelope(
            envelope_id="child",
            max_spend=100.0,  # More restrictive but NOT scoped
            allowed_actions=["read", "write"],
            read_paths=["/data/public"],
        )

        result = intersect_envelopes(
            parent,
            child,
            dimension_scope=frozenset({"operational", "data_access"}),
        )

        # Financial: inherited from parent (NOT scoped)
        assert result.financial.max_spend_usd == 1000.0

        # Operational: intersected
        assert sorted(result.operational.allowed_actions) == ["read", "write"]

        # Data access: intersected
        assert result.data_access.read_paths == ["/data/public"]

    def test_all_dimensions_scope_matches_no_scope(self) -> None:
        """Passing ALL_DIMENSIONS as scope should match no-scope behavior."""
        parent = _make_envelope(
            envelope_id="parent",
            max_spend=1000.0,
            allowed_actions=["read", "write"],
        )
        child = _make_envelope(
            envelope_id="child",
            max_spend=500.0,
            allowed_actions=["read"],
        )

        result_scoped = intersect_envelopes(
            parent, child, dimension_scope=ALL_DIMENSIONS
        )
        result_unscoped = intersect_envelopes(parent, child)

        # Financial
        assert (
            result_scoped.financial.max_spend_usd
            == result_unscoped.financial.max_spend_usd
        )
        # Operational
        assert sorted(result_scoped.operational.allowed_actions) == sorted(
            result_unscoped.operational.allowed_actions
        )

    def test_communication_scope_preserves_parent_financial(self) -> None:
        """Communication-only scope must leave financial from parent."""
        parent = _make_envelope(
            envelope_id="parent",
            max_spend=5000.0,
            allowed_channels=["internal", "email", "slack"],
        )
        child = _make_envelope(
            envelope_id="child",
            max_spend=10.0,  # Very restrictive but not scoped
            allowed_channels=["internal"],
        )

        result = intersect_envelopes(
            parent, child, dimension_scope=frozenset({"communication"})
        )

        # Financial preserved from parent
        assert result.financial.max_spend_usd == 5000.0
        # Communication intersected
        assert result.communication.allowed_channels == ["internal"]

    def test_temporal_scope(self) -> None:
        """Temporal-only scope intersects only temporal dimension."""
        parent = _make_envelope(
            envelope_id="parent",
            max_spend=1000.0,
            active_hours_start="06:00",
            active_hours_end="22:00",
        )
        child = _make_envelope(
            envelope_id="child",
            max_spend=50.0,
            active_hours_start="09:00",
            active_hours_end="17:00",
        )

        result = intersect_envelopes(
            parent, child, dimension_scope=frozenset({"temporal"})
        )

        # Financial: preserved from parent
        assert result.financial.max_spend_usd == 1000.0
        # Temporal: intersected (overlap: 09:00-17:00)
        assert result.temporal.active_hours_start == "09:00"
        assert result.temporal.active_hours_end == "17:00"

    def test_confidentiality_always_intersected(self) -> None:
        """confidentiality_clearance is always intersected regardless of scope.

        Confidentiality is not a dimension -- it's a top-level envelope field
        that governs data classification. Scoping doesn't apply to it.
        """
        parent = _make_envelope(envelope_id="parent")
        # Override confidentiality on parent
        parent = ConstraintEnvelopeConfig(
            id="parent",
            confidentiality_clearance=ConfidentialityLevel.SECRET,
            financial=parent.financial,
            operational=parent.operational,
            temporal=parent.temporal,
            data_access=parent.data_access,
            communication=parent.communication,
        )
        child = _make_envelope(envelope_id="child")
        child = ConstraintEnvelopeConfig(
            id="child",
            confidentiality_clearance=ConfidentialityLevel.RESTRICTED,
            financial=child.financial,
            operational=child.operational,
            temporal=child.temporal,
            data_access=child.data_access,
            communication=child.communication,
        )

        result = intersect_envelopes(
            parent, child, dimension_scope=frozenset({"financial"})
        )

        # Confidentiality: always intersected (min of SECRET and RESTRICTED = RESTRICTED)
        assert result.confidentiality_clearance == ConfidentialityLevel.RESTRICTED

    def test_max_delegation_depth_always_intersected(self) -> None:
        """max_delegation_depth is always intersected regardless of scope."""
        parent = _make_envelope(envelope_id="parent")
        parent_with_depth = ConstraintEnvelopeConfig(
            id="parent",
            max_delegation_depth=5,
            financial=parent.financial,
            operational=parent.operational,
            temporal=parent.temporal,
            data_access=parent.data_access,
            communication=parent.communication,
        )
        child = _make_envelope(envelope_id="child")
        child_with_depth = ConstraintEnvelopeConfig(
            id="child",
            max_delegation_depth=3,
            financial=child.financial,
            operational=child.operational,
            temporal=child.temporal,
            data_access=child.data_access,
            communication=child.communication,
        )

        result = intersect_envelopes(
            parent_with_depth,
            child_with_depth,
            dimension_scope=frozenset({"financial"}),
        )

        # max_delegation_depth: always intersected (min of 5, 3 = 3)
        assert result.max_delegation_depth == 3
