# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""NaN/Inf security tests for governance envelopes.

Critical security regression tests: NaN and Inf values bypass numeric
comparisons in Python (NaN < X is always False, NaN > X is always False,
action_cost > Inf is always False). These tests verify that all numeric
constraint fields reject non-finite values with clear errors.

Per trust-plane-security.md rule 3: math.isfinite() on all numeric constraint fields.
"""

from __future__ import annotations

import math

import pytest

from pact.build.config.schema import (
    CommunicationConstraintConfig,
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
)
from pact.governance.envelopes import (
    MonotonicTighteningError,
    RoleEnvelope,
    _min_optional,
    _min_optional_int,
    intersect_envelopes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_envelope(
    *,
    envelope_id: str = "test",
    max_spend: float = 1000.0,
    api_cost_budget_usd: float | None = None,
    requires_approval_above_usd: float | None = None,
    allowed_actions: list[str] | None = None,
    confidentiality: ConfidentialityLevel = ConfidentialityLevel.CONFIDENTIAL,
    max_delegation_depth: int | None = None,
) -> ConstraintEnvelopeConfig:
    """Build a ConstraintEnvelopeConfig with sensible defaults for security tests."""
    return ConstraintEnvelopeConfig(
        id=envelope_id,
        confidentiality_clearance=confidentiality,
        financial=FinancialConstraintConfig(
            max_spend_usd=max_spend,
            api_cost_budget_usd=api_cost_budget_usd,
            requires_approval_above_usd=requires_approval_above_usd,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=allowed_actions or ["read", "write"],
        ),
        temporal=TemporalConstraintConfig(),
        data_access=DataAccessConstraintConfig(),
        communication=CommunicationConstraintConfig(
            allowed_channels=["internal"],
        ),
        max_delegation_depth=max_delegation_depth,
    )


# ===========================================================================
# _min_optional: NaN/Inf guard
# ===========================================================================


class TestMinOptionalNanInf:
    """_min_optional and _min_optional_int must reject non-finite values."""

    def test_min_optional_nan_first_arg_raises(self) -> None:
        """_min_optional(NaN, 5.0) must raise ValueError, not silently return NaN."""
        with pytest.raises(ValueError, match="must be finite"):
            _min_optional(float("nan"), 5.0)

    def test_min_optional_nan_second_arg_raises(self) -> None:
        """_min_optional(5.0, NaN) must raise ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            _min_optional(5.0, float("nan"))

    def test_min_optional_inf_first_arg_raises(self) -> None:
        """_min_optional(Inf, 5.0) must raise ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            _min_optional(float("inf"), 5.0)

    def test_min_optional_inf_second_arg_raises(self) -> None:
        """_min_optional(5.0, Inf) must raise ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            _min_optional(5.0, float("inf"))

    def test_min_optional_negative_inf_raises(self) -> None:
        """_min_optional(-Inf, 5.0) must raise ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            _min_optional(float("-inf"), 5.0)

    def test_min_optional_both_nan_raises(self) -> None:
        """_min_optional(NaN, NaN) must raise ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            _min_optional(float("nan"), float("nan"))

    def test_min_optional_nan_with_none_raises(self) -> None:
        """_min_optional(NaN, None) must raise ValueError -- NaN is not None."""
        with pytest.raises(ValueError, match="must be finite"):
            _min_optional(float("nan"), None)

    def test_min_optional_none_with_nan_raises(self) -> None:
        """_min_optional(None, NaN) must raise ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            _min_optional(None, float("nan"))

    def test_min_optional_finite_values_work(self) -> None:
        """Normal finite values must continue to work correctly."""
        assert _min_optional(3.0, 5.0) == 3.0
        assert _min_optional(5.0, 3.0) == 3.0
        assert _min_optional(0.0, 100.0) == 0.0
        assert _min_optional(-1.0, 1.0) == -1.0

    def test_min_optional_none_handling_unchanged(self) -> None:
        """None semantics (unbounded/permissive) must be preserved."""
        assert _min_optional(None, None) is None
        assert _min_optional(None, 5.0) == 5.0
        assert _min_optional(5.0, None) == 5.0

    def test_min_optional_int_nan_raises(self) -> None:
        """_min_optional_int must also reject non-finite float values.

        Although typed as int|None, Python allows float('nan') to be passed
        at runtime. The guard must catch this.
        """
        with pytest.raises((ValueError, TypeError)):
            _min_optional_int(float("nan"), 5)  # type: ignore[arg-type]

    def test_min_optional_int_inf_raises(self) -> None:
        """_min_optional_int must reject Inf."""
        with pytest.raises((ValueError, TypeError)):
            _min_optional_int(float("inf"), 5)  # type: ignore[arg-type]

    def test_min_optional_int_finite_values_work(self) -> None:
        """Normal integer values must work correctly."""
        assert _min_optional_int(3, 5) == 3
        assert _min_optional_int(5, 3) == 3
        assert _min_optional_int(None, None) is None
        assert _min_optional_int(None, 5) == 5
        assert _min_optional_int(5, None) == 5


# ===========================================================================
# FinancialConstraintConfig: Pydantic NaN/Inf rejection
# ===========================================================================


class TestFinancialConfigNanInf:
    """Pydantic schema must reject NaN/Inf in financial constraint fields."""

    def test_max_spend_nan_rejected(self) -> None:
        """FinancialConstraintConfig(max_spend_usd=NaN) must raise ValidationError."""
        with pytest.raises((ValueError, Exception)):
            FinancialConstraintConfig(max_spend_usd=float("nan"))

    def test_max_spend_inf_rejected(self) -> None:
        """FinancialConstraintConfig(max_spend_usd=Inf) must raise ValidationError."""
        with pytest.raises((ValueError, Exception)):
            FinancialConstraintConfig(max_spend_usd=float("inf"))

    def test_max_spend_negative_inf_rejected(self) -> None:
        """FinancialConstraintConfig(max_spend_usd=-Inf) must raise ValidationError."""
        with pytest.raises((ValueError, Exception)):
            FinancialConstraintConfig(max_spend_usd=float("-inf"))

    def test_api_cost_budget_nan_rejected(self) -> None:
        """api_cost_budget_usd=NaN must raise ValidationError."""
        with pytest.raises((ValueError, Exception)):
            FinancialConstraintConfig(max_spend_usd=100.0, api_cost_budget_usd=float("nan"))

    def test_api_cost_budget_inf_rejected(self) -> None:
        """api_cost_budget_usd=Inf must raise ValidationError."""
        with pytest.raises((ValueError, Exception)):
            FinancialConstraintConfig(max_spend_usd=100.0, api_cost_budget_usd=float("inf"))

    def test_requires_approval_nan_rejected(self) -> None:
        """requires_approval_above_usd=NaN must raise ValidationError."""
        with pytest.raises((ValueError, Exception)):
            FinancialConstraintConfig(max_spend_usd=100.0, requires_approval_above_usd=float("nan"))

    def test_requires_approval_inf_rejected(self) -> None:
        """requires_approval_above_usd=Inf must raise ValidationError."""
        with pytest.raises((ValueError, Exception)):
            FinancialConstraintConfig(max_spend_usd=100.0, requires_approval_above_usd=float("inf"))

    def test_valid_financial_config_works(self) -> None:
        """Normal finite values must continue to work."""
        fc = FinancialConstraintConfig(
            max_spend_usd=1000.0,
            api_cost_budget_usd=500.0,
            requires_approval_above_usd=200.0,
        )
        assert fc.max_spend_usd == 1000.0
        assert fc.api_cost_budget_usd == 500.0
        assert fc.requires_approval_above_usd == 200.0

    def test_zero_spend_valid(self) -> None:
        """Zero spend is valid (PSEUDO_AGENT may have $0 budget)."""
        fc = FinancialConstraintConfig(max_spend_usd=0.0)
        assert fc.max_spend_usd == 0.0

    def test_none_optional_fields_valid(self) -> None:
        """None for optional fields is valid (means no limit set)."""
        fc = FinancialConstraintConfig(
            max_spend_usd=100.0,
            api_cost_budget_usd=None,
            requires_approval_above_usd=None,
        )
        assert fc.api_cost_budget_usd is None
        assert fc.requires_approval_above_usd is None


# ===========================================================================
# intersect_envelopes: NaN/Inf propagation blocked
# ===========================================================================


class TestIntersectEnvelopesNanInf:
    """intersect_envelopes must raise ValueError when either envelope has NaN/Inf.

    This tests the end-to-end flow: even if somehow a NaN/Inf value gets past
    the Pydantic validator (e.g., via model_construct or direct attribute
    setting), the intersection logic must still catch it.
    """

    def test_intersect_nan_spend_raises(self) -> None:
        """Envelope with NaN max_spend_usd must be rejected during intersection."""
        # Use model_construct to bypass Pydantic validation (simulating attacker)
        nan_financial = FinancialConstraintConfig.model_construct(
            max_spend_usd=float("nan"),
            api_cost_budget_usd=None,
            requires_approval_above_usd=None,
            reasoning_required=False,
        )
        nan_envelope = ConstraintEnvelopeConfig.model_construct(
            id="nan-env",
            description="",
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
            financial=nan_financial,
            operational=OperationalConstraintConfig(allowed_actions=["read"]),
            temporal=TemporalConstraintConfig(),
            data_access=DataAccessConstraintConfig(),
            communication=CommunicationConstraintConfig(allowed_channels=["internal"]),
            max_delegation_depth=None,
            expires_at=None,
        )
        normal_envelope = _make_envelope(max_spend=500.0)

        with pytest.raises(ValueError, match="must be finite|greater than"):
            intersect_envelopes(nan_envelope, normal_envelope)

    def test_intersect_inf_spend_raises(self) -> None:
        """Envelope with Inf max_spend_usd must be rejected during intersection."""
        inf_financial = FinancialConstraintConfig.model_construct(
            max_spend_usd=float("inf"),
            api_cost_budget_usd=None,
            requires_approval_above_usd=None,
            reasoning_required=False,
        )
        inf_envelope = ConstraintEnvelopeConfig.model_construct(
            id="inf-env",
            description="",
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
            financial=inf_financial,
            operational=OperationalConstraintConfig(allowed_actions=["read"]),
            temporal=TemporalConstraintConfig(),
            data_access=DataAccessConstraintConfig(),
            communication=CommunicationConstraintConfig(allowed_channels=["internal"]),
            max_delegation_depth=None,
            expires_at=None,
        )
        normal_envelope = _make_envelope(max_spend=500.0)

        with pytest.raises(ValueError, match="must be finite"):
            intersect_envelopes(inf_envelope, normal_envelope)

    def test_intersect_nan_api_budget_raises(self) -> None:
        """NaN in api_cost_budget_usd must be caught during intersection."""
        nan_financial = FinancialConstraintConfig.model_construct(
            max_spend_usd=1000.0,
            api_cost_budget_usd=float("nan"),
            requires_approval_above_usd=None,
            reasoning_required=False,
        )
        nan_envelope = ConstraintEnvelopeConfig.model_construct(
            id="nan-api-env",
            description="",
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
            financial=nan_financial,
            operational=OperationalConstraintConfig(allowed_actions=["read"]),
            temporal=TemporalConstraintConfig(),
            data_access=DataAccessConstraintConfig(),
            communication=CommunicationConstraintConfig(allowed_channels=["internal"]),
            max_delegation_depth=None,
            expires_at=None,
        )
        normal_envelope = _make_envelope(max_spend=500.0, api_cost_budget_usd=200.0)

        with pytest.raises(ValueError, match="must be finite"):
            intersect_envelopes(nan_envelope, normal_envelope)

    def test_intersect_normal_envelopes_work(self) -> None:
        """Normal envelopes must still intersect correctly (no false positives)."""
        a = _make_envelope(max_spend=1000.0, api_cost_budget_usd=500.0)
        b = _make_envelope(max_spend=600.0, api_cost_budget_usd=300.0)
        result = intersect_envelopes(a, b)
        assert result.financial is not None
        assert result.financial.max_spend_usd == 600.0
        assert result.financial.api_cost_budget_usd == 300.0


# ===========================================================================
# validate_tightening: NaN/Inf bypass prevention
# ===========================================================================


class TestValidateTighteningNanInf:
    """validate_tightening must catch NaN/Inf in financial fields.

    The bug: NaN > parent_max_spend is always False, so a child with NaN
    spend silently passes tightening validation when it should fail.
    """

    def test_child_nan_spend_raises(self) -> None:
        """Child with NaN max_spend_usd must be rejected (not silently pass)."""
        parent = _make_envelope(envelope_id="parent", max_spend=1000.0)
        nan_financial = FinancialConstraintConfig.model_construct(
            max_spend_usd=float("nan"),
            api_cost_budget_usd=None,
            requires_approval_above_usd=None,
            reasoning_required=False,
        )
        child = ConstraintEnvelopeConfig.model_construct(
            id="child-nan",
            description="",
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
            financial=nan_financial,
            operational=OperationalConstraintConfig(allowed_actions=["read"]),
            temporal=TemporalConstraintConfig(),
            data_access=DataAccessConstraintConfig(),
            communication=CommunicationConstraintConfig(allowed_channels=["internal"]),
            max_delegation_depth=None,
            expires_at=None,
        )

        with pytest.raises(ValueError, match="must be finite"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent,
                child_envelope=child,
            )

    def test_parent_nan_spend_raises(self) -> None:
        """Parent with NaN max_spend_usd must also be rejected."""
        nan_financial = FinancialConstraintConfig.model_construct(
            max_spend_usd=float("nan"),
            api_cost_budget_usd=None,
            requires_approval_above_usd=None,
            reasoning_required=False,
        )
        parent = ConstraintEnvelopeConfig.model_construct(
            id="parent-nan",
            description="",
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
            financial=nan_financial,
            operational=OperationalConstraintConfig(allowed_actions=["read", "write"]),
            temporal=TemporalConstraintConfig(),
            data_access=DataAccessConstraintConfig(),
            communication=CommunicationConstraintConfig(allowed_channels=["internal"]),
            max_delegation_depth=None,
            expires_at=None,
        )
        child = _make_envelope(envelope_id="child", max_spend=500.0)

        with pytest.raises(ValueError, match="must be finite"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent,
                child_envelope=child,
            )

    def test_child_inf_api_budget_raises(self) -> None:
        """Child with Inf api_cost_budget_usd must be rejected."""
        parent = _make_envelope(envelope_id="parent", max_spend=1000.0, api_cost_budget_usd=500.0)
        inf_financial = FinancialConstraintConfig.model_construct(
            max_spend_usd=500.0,
            api_cost_budget_usd=float("inf"),
            requires_approval_above_usd=None,
            reasoning_required=False,
        )
        child = ConstraintEnvelopeConfig.model_construct(
            id="child-inf",
            description="",
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
            financial=inf_financial,
            operational=OperationalConstraintConfig(allowed_actions=["read"]),
            temporal=TemporalConstraintConfig(),
            data_access=DataAccessConstraintConfig(),
            communication=CommunicationConstraintConfig(allowed_channels=["internal"]),
            max_delegation_depth=None,
            expires_at=None,
        )

        with pytest.raises(ValueError, match="must be finite"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent,
                child_envelope=child,
            )

    def test_valid_tightening_still_works(self) -> None:
        """Normal tightening validation must still work (no false positives)."""
        parent = _make_envelope(
            envelope_id="parent",
            max_spend=1000.0,
            api_cost_budget_usd=500.0,
        )
        child = _make_envelope(
            envelope_id="child",
            max_spend=500.0,
            api_cost_budget_usd=200.0,
            allowed_actions=["read"],
        )
        # Should not raise
        RoleEnvelope.validate_tightening(
            parent_envelope=parent,
            child_envelope=child,
        )

    def test_tightening_violation_still_detected(self) -> None:
        """Legitimate tightening violations must still be caught."""
        parent = _make_envelope(envelope_id="parent", max_spend=500.0)
        child = _make_envelope(envelope_id="child", max_spend=1000.0)
        with pytest.raises(MonotonicTighteningError):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent,
                child_envelope=child,
            )
