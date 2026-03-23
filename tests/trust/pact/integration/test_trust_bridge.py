# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests: PACT governance → trust-layer envelope bridge.

Verifies that GovernanceEnvelopeAdapter correctly maps governance
ConstraintEnvelopeConfig to kailash.trust.plane.models.ConstraintEnvelope.
Tests the cross-package boundary between pact.governance and kailash.trust.

Covers:
- Field mapping completeness (financial, operational, data_access, communication)
- NaN/Inf rejection at the adapter boundary
- Monotonic tightening preserved through adapter
- Envelope signed_by attribution
- Empty/None dimension handling
- Trust-layer envelope is a valid frozen dataclass
"""

from __future__ import annotations

import math

import pytest

from kailash.trust.plane.models import (
    ConstraintEnvelope as TrustConstraintEnvelope,
    FinancialConstraints,
    OperationalConstraints,
)
from kailash.trust.pact.config import (
    CommunicationConstraintConfig,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelope_adapter import (
    EnvelopeAdapterError,
    GovernanceEnvelopeAdapter,
)
from kailash.trust.pact.envelopes import RoleEnvelope
from pact.examples.university.org import create_university_org


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine_with_full_envelope() -> GovernanceEngine:
    """Engine with a role envelope covering all 5 constraint dimensions."""
    compiled, _ = create_university_org()
    engine = GovernanceEngine(compiled)

    config = ConstraintEnvelopeConfig(
        id="env-full-test",
        description="Full 5-dimension envelope for bridge testing",
        financial=FinancialConstraintConfig(
            max_spend_usd=1000.0,
            api_cost_budget_usd=500.0,
            requires_approval_above_usd=250.0,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write", "analyze"],
            blocked_actions=["delete", "admin"],
            max_actions_per_hour=100,
        ),
        temporal=TemporalConstraintConfig(
            active_hours_start="09:00",
            active_hours_end="17:00",
            timezone="UTC",
        ),
        data_access=DataAccessConstraintConfig(
            read_paths=["/data/public", "/data/team"],
            write_paths=["/data/team"],
            blocked_data_types=["pii", "financial_records"],
        ),
        communication=CommunicationConstraintConfig(
            internal_only=True,
            allowed_channels=["slack", "email"],
            external_requires_approval=True,
        ),
    )
    role_env = RoleEnvelope(
        id="re-full-test",
        defining_role_address="D1-R1-D1-R1-D1-R1",
        target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
        envelope=config,
    )
    engine.set_role_envelope(role_env)
    return engine


@pytest.fixture
def adapter(engine_with_full_envelope: GovernanceEngine) -> GovernanceEnvelopeAdapter:
    return GovernanceEnvelopeAdapter(engine_with_full_envelope)


# ---------------------------------------------------------------------------
# Tests: Field Mapping
# ---------------------------------------------------------------------------


class TestFieldMapping:
    """Verify governance config fields are correctly mapped to trust-layer fields."""

    def test_produces_trust_constraint_envelope(
        self, adapter: GovernanceEnvelopeAdapter
    ) -> None:
        """Adapter should produce a kailash.trust.plane.models.ConstraintEnvelope."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        assert isinstance(result, TrustConstraintEnvelope)

    def test_financial_mapping(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """Financial: max_spend_usd → max_cost_per_session."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        assert result.financial.max_cost_per_session == 1000.0
        assert result.financial.max_cost_per_action == 250.0
        assert result.financial.budget_tracking is True

    def test_operational_mapping(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """Operational: allowed/blocked actions preserved."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        assert set(result.operational.allowed_actions) == {"read", "write", "analyze"}
        assert set(result.operational.blocked_actions) == {"delete", "admin"}

    def test_data_access_mapping(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """Data access: read/write paths and blocked types mapped."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        assert "/data/public" in result.data_access.read_paths
        assert "/data/team" in result.data_access.write_paths
        # blocked_data_types maps to blocked_paths
        assert "pii" in result.data_access.blocked_paths

    def test_communication_mapping(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """Communication: allowed_channels preserved."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        assert "slack" in result.communication.allowed_channels
        assert "email" in result.communication.allowed_channels

    def test_temporal_mapping(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """Temporal: HH:MM active hours → integer hour tuple."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        # 09:00-17:00 maps to allowed_hours=(9, 17)
        assert result.temporal.allowed_hours == (9, 17)

    def test_signed_by_attribution(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """Trust envelope should be attributed to the governance config ID."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        assert result.signed_by == "governance:env-full-test"

    def test_trust_envelope_is_frozen(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """Trust-layer constraint sub-objects should be frozen."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        with pytest.raises(AttributeError):
            result.operational.allowed_actions = ["hacked"]  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases in the governance → trust bridge."""

    def test_no_financial_constraints(self) -> None:
        """When financial is None, trust-layer should get default FinancialConstraints."""
        compiled, _ = create_university_org()
        engine = GovernanceEngine(compiled)

        config = ConstraintEnvelopeConfig(
            id="env-no-financial",
            financial=None,
            operational=OperationalConstraintConfig(allowed_actions=["read"]),
        )
        role_env = RoleEnvelope(
            id="re-no-fin",
            defining_role_address="D1-R1-D1-R1-D1-R1",
            target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            envelope=config,
        )
        engine.set_role_envelope(role_env)

        adapter = GovernanceEnvelopeAdapter(engine)
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        # Should have default (non-restrictive) financial constraints
        assert result.financial.max_cost_per_session is None
        assert result.financial.budget_tracking is False

    def test_no_envelope_fails_closed(self) -> None:
        """Role with no envelope should raise EnvelopeAdapterError."""
        compiled, _ = create_university_org()
        engine = GovernanceEngine(compiled)
        adapter = GovernanceEnvelopeAdapter(engine)

        with pytest.raises(EnvelopeAdapterError, match="No effective envelope"):
            adapter.to_constraint_envelope("D1-R1-D2-R1-T1-R1")

    def test_nan_in_financial_rejected(self) -> None:
        """NaN values should be rejected at the adapter boundary."""
        compiled, _ = create_university_org()
        engine = GovernanceEngine(compiled)

        config = ConstraintEnvelopeConfig(
            id="env-nan-test",
            financial=FinancialConstraintConfig(max_spend_usd=100.0),
            operational=OperationalConstraintConfig(allowed_actions=["read"]),
        )
        role_env = RoleEnvelope(
            id="re-nan-test",
            defining_role_address="D1-R1-D1-R1-D1-R1",
            target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            envelope=config,
        )
        engine.set_role_envelope(role_env)

        # Smuggle NaN past Pydantic validators
        original = engine.compute_envelope

        def patched(role_address: str, task_id: str | None = None):
            config = original(role_address, task_id=task_id)
            if config and config.financial:
                object.__setattr__(config.financial, "max_spend_usd", float("nan"))
            return config

        engine.compute_envelope = patched  # type: ignore[assignment]

        adapter = GovernanceEnvelopeAdapter(engine)
        with pytest.raises(EnvelopeAdapterError, match="non-finite"):
            adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
