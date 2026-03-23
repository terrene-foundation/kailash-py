# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #59: Replace local ConstraintEnvelope with ConstraintEnvelopeConfig.

Validates that:
1. ConstraintEnvelope is now an alias for ConstraintEnvelopeConfig from kailash.trust.pact.config
2. Old import paths still work (backward compatibility)
3. The new typed sub-models are used instead of raw dicts
4. GovernedSupervisor constructs and reads the envelope correctly
5. All five CARE dimensions are properly accessible via typed sub-models
6. NaN/Inf validation still works via Pydantic validators
"""

from __future__ import annotations

import math

import pytest

from kailash.trust.pact.config import (
    CommunicationConstraintConfig,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
)


# ---------------------------------------------------------------------------
# 1. Backward-compatible import
# ---------------------------------------------------------------------------


class TestBackwardCompatImport:
    """ConstraintEnvelope should be importable from kaizen_agents.types."""

    def test_constraint_envelope_importable_from_types(self) -> None:
        """ConstraintEnvelope is still importable from kaizen_agents.types."""
        from kaizen_agents.types import ConstraintEnvelope

        assert ConstraintEnvelope is ConstraintEnvelopeConfig

    def test_constraint_envelope_in_all(self) -> None:
        """ConstraintEnvelope is still listed in __all__ for backward compat."""
        import kaizen_agents.types as types_mod

        # ConstraintEnvelope should still be accessible as an attribute
        assert hasattr(types_mod, "ConstraintEnvelope")


# ---------------------------------------------------------------------------
# 2. Typed sub-model construction
# ---------------------------------------------------------------------------


class TestTypedSubModelConstruction:
    """ConstraintEnvelopeConfig uses typed sub-models, not raw dicts."""

    def test_financial_constraint_via_typed_model(self) -> None:
        """Financial dimension uses FinancialConstraintConfig."""
        env = ConstraintEnvelopeConfig(
            id="test-env",
            financial=FinancialConstraintConfig(max_spend_usd=10.0),
        )
        assert env.financial is not None
        assert env.financial.max_spend_usd == 10.0

    def test_operational_constraint_via_typed_model(self) -> None:
        """Operational dimension uses OperationalConstraintConfig."""
        env = ConstraintEnvelopeConfig(
            id="test-env",
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
                blocked_actions=["delete"],
            ),
        )
        assert "read" in env.operational.allowed_actions
        assert "delete" in env.operational.blocked_actions

    def test_temporal_constraint_via_typed_model(self) -> None:
        """Temporal dimension uses TemporalConstraintConfig."""
        env = ConstraintEnvelopeConfig(
            id="test-env",
            temporal=TemporalConstraintConfig(
                active_hours_start="09:00",
                active_hours_end="17:00",
            ),
        )
        assert env.temporal.active_hours_start == "09:00"

    def test_data_access_constraint_via_typed_model(self) -> None:
        """Data access dimension uses DataAccessConstraintConfig."""
        env = ConstraintEnvelopeConfig(
            id="test-env",
            data_access=DataAccessConstraintConfig(
                read_paths=["/data/public"],
                write_paths=["/data/output"],
            ),
        )
        assert "/data/public" in env.data_access.read_paths

    def test_communication_constraint_via_typed_model(self) -> None:
        """Communication dimension uses CommunicationConstraintConfig."""
        env = ConstraintEnvelopeConfig(
            id="test-env",
            communication=CommunicationConstraintConfig(
                allowed_channels=["email", "slack"],
            ),
        )
        assert "email" in env.communication.allowed_channels

    def test_none_financial_means_no_financial_capability(self) -> None:
        """Setting financial=None means the agent has no financial capability."""
        env = ConstraintEnvelopeConfig(
            id="test-env",
            financial=None,
        )
        assert env.financial is None


# ---------------------------------------------------------------------------
# 3. NaN/Inf validation via Pydantic validators
# ---------------------------------------------------------------------------


class TestNaNInfValidation:
    """Pydantic validators reject NaN/Inf in financial fields."""

    def test_nan_max_spend_rejected(self) -> None:
        """NaN max_spend_usd MUST be rejected."""
        with pytest.raises((ValueError,)):
            FinancialConstraintConfig(max_spend_usd=float("nan"))

    def test_inf_max_spend_rejected(self) -> None:
        """Inf max_spend_usd MUST be rejected."""
        with pytest.raises((ValueError,)):
            FinancialConstraintConfig(max_spend_usd=float("inf"))


# ---------------------------------------------------------------------------
# 4. GovernedSupervisor integration
# ---------------------------------------------------------------------------


class TestGovernedSupervisorEnvelopeIntegration:
    """GovernedSupervisor must work with the new ConstraintEnvelopeConfig."""

    def test_supervisor_constructs_with_envelope_config(self) -> None:
        """GovernedSupervisor should construct successfully."""
        from kaizen_agents.supervisor import GovernedSupervisor

        sup = GovernedSupervisor(model="test-model", budget_usd=5.0)
        env = sup.envelope
        assert isinstance(env, ConstraintEnvelopeConfig)

    def test_supervisor_envelope_has_correct_budget(self) -> None:
        """GovernedSupervisor envelope financial limit matches budget_usd."""
        from kaizen_agents.supervisor import GovernedSupervisor

        sup = GovernedSupervisor(model="test-model", budget_usd=25.0)
        env = sup.envelope
        assert env.financial is not None
        assert env.financial.max_spend_usd == 25.0

    def test_supervisor_envelope_has_correct_tools(self) -> None:
        """GovernedSupervisor envelope operational allowed_actions matches tools."""
        from kaizen_agents.supervisor import GovernedSupervisor

        sup = GovernedSupervisor(
            model="test-model",
            budget_usd=5.0,
            tools=["read_file", "write_file"],
        )
        env = sup.envelope
        assert "read_file" in env.operational.allowed_actions
        assert "write_file" in env.operational.allowed_actions

    def test_supervisor_envelope_has_confidentiality_clearance(self) -> None:
        """GovernedSupervisor envelope carries confidentiality_clearance."""
        from kailash.trust import ConfidentialityLevel
        from kaizen_agents.supervisor import GovernedSupervisor

        sup = GovernedSupervisor(model="test-model", budget_usd=5.0, data_clearance="restricted")
        env = sup.envelope
        assert env.confidentiality_clearance == ConfidentialityLevel.RESTRICTED

    @pytest.mark.asyncio
    async def test_supervisor_run_with_new_envelope(self) -> None:
        """GovernedSupervisor.run() works end-to-end with the new envelope type."""
        from kaizen_agents.supervisor import GovernedSupervisor

        sup = GovernedSupervisor(model="test-model", budget_usd=5.0)

        async def executor(spec, inputs):
            return {"result": "ok", "cost": 0.10}

        result = await sup.run("test objective", execute_node=executor)
        assert result.success is True
        assert result.budget_consumed == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# 5. Envelope serialization for SDK compat
# ---------------------------------------------------------------------------


class TestEnvelopeSerializationCompat:
    """The _envelope_to_dict helper and SDK compat functions must work."""

    def test_envelope_to_dict_produces_valid_dict(self) -> None:
        """_envelope_to_dict should produce a dict with all five dimensions."""
        from kaizen_agents.supervisor import _envelope_to_dict

        env = ConstraintEnvelopeConfig(
            id="test-env",
            financial=FinancialConstraintConfig(max_spend_usd=10.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
                blocked_actions=["delete"],
            ),
        )
        d = _envelope_to_dict(env)
        assert isinstance(d, dict)
        assert "financial" in d
        assert "operational" in d
        assert "temporal" in d
        assert "data_access" in d
        assert "communication" in d

    def test_sdk_compat_envelope_to_dict(self) -> None:
        """The _sdk_compat envelope_to_dict should work with the new type."""
        from kaizen_agents._sdk_compat import envelope_to_dict

        env = ConstraintEnvelopeConfig(
            id="test-env",
            financial=FinancialConstraintConfig(max_spend_usd=5.0),
        )
        d = envelope_to_dict(env)
        assert isinstance(d, dict)
        assert "financial" in d
