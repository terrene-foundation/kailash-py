# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for per-dimension gradient thresholds (TODO-02) and gradient dereliction (TODO-03).

TODO-02: DimensionThresholds, GradientThresholdsConfig, integration with
  RoleEnvelope and validate_tightening().
TODO-03: check_gradient_dereliction() for rubber-stamping detection.
"""

from __future__ import annotations

import math

import pytest

from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    DimensionThresholds,
    FinancialConstraintConfig,
    GradientThresholdsConfig,
)
from kailash.trust.pact.envelopes import (
    MonotonicTighteningError,
    RoleEnvelope,
    check_gradient_dereliction,
)


# ---------------------------------------------------------------------------
# TODO-02: DimensionThresholds validation
# ---------------------------------------------------------------------------


class TestDimensionThresholdsValidation:
    """DimensionThresholds model accepts ordered thresholds, rejects invalid ones."""

    def test_dimension_thresholds_valid(self) -> None:
        """Correctly ordered thresholds are accepted."""
        dt = DimensionThresholds(
            auto_approve_threshold=100.0,
            flag_threshold=500.0,
            hold_threshold=1000.0,
        )
        assert dt.auto_approve_threshold == 100.0
        assert dt.flag_threshold == 500.0
        assert dt.hold_threshold == 1000.0

    def test_dimension_thresholds_equal_values_valid(self) -> None:
        """Equal thresholds are accepted (boundary case: all same value)."""
        dt = DimensionThresholds(
            auto_approve_threshold=100.0,
            flag_threshold=100.0,
            hold_threshold=100.0,
        )
        assert dt.auto_approve_threshold == 100.0

    def test_dimension_thresholds_invalid_order(self) -> None:
        """Wrong order raises ValueError: auto_approve > flag."""
        with pytest.raises(ValueError, match="Thresholds must be ordered"):
            DimensionThresholds(
                auto_approve_threshold=500.0,
                flag_threshold=100.0,
                hold_threshold=1000.0,
            )

    def test_dimension_thresholds_invalid_order_flag_gt_hold(self) -> None:
        """Wrong order raises ValueError: flag > hold."""
        with pytest.raises(ValueError, match="Thresholds must be ordered"):
            DimensionThresholds(
                auto_approve_threshold=100.0,
                flag_threshold=1000.0,
                hold_threshold=500.0,
            )

    def test_dimension_thresholds_nan_rejected(self) -> None:
        """NaN in any threshold field raises ValueError."""
        with pytest.raises(ValueError, match="finite"):
            DimensionThresholds(
                auto_approve_threshold=float("nan"),
                flag_threshold=500.0,
                hold_threshold=1000.0,
            )

    def test_dimension_thresholds_inf_rejected(self) -> None:
        """Inf in any threshold field raises ValueError."""
        with pytest.raises(ValueError, match="finite"):
            DimensionThresholds(
                auto_approve_threshold=100.0,
                flag_threshold=float("inf"),
                hold_threshold=1000.0,
            )

    def test_dimension_thresholds_neg_inf_rejected(self) -> None:
        """Negative inf in any threshold field raises ValueError."""
        with pytest.raises(ValueError, match="finite"):
            DimensionThresholds(
                auto_approve_threshold=100.0,
                flag_threshold=500.0,
                hold_threshold=float("-inf"),
            )


# ---------------------------------------------------------------------------
# TODO-02: GradientThresholdsConfig
# ---------------------------------------------------------------------------


class TestGradientThresholdsConfig:
    """GradientThresholdsConfig carries optional per-dimension thresholds."""

    def test_gradient_thresholds_config_default(self) -> None:
        """Default config has no financial thresholds."""
        cfg = GradientThresholdsConfig()
        assert cfg.financial is None

    def test_gradient_thresholds_config_with_financial(self) -> None:
        """Financial thresholds can be set."""
        dt = DimensionThresholds(
            auto_approve_threshold=100.0,
            flag_threshold=500.0,
            hold_threshold=1000.0,
        )
        cfg = GradientThresholdsConfig(financial=dt)
        assert cfg.financial is not None
        assert cfg.financial.auto_approve_threshold == 100.0


# ---------------------------------------------------------------------------
# TODO-02: RoleEnvelope with gradient_thresholds
# ---------------------------------------------------------------------------


class TestRoleEnvelopeGradientThresholds:
    """RoleEnvelope accepts an optional gradient_thresholds field."""

    def test_gradient_thresholds_on_role_envelope(self) -> None:
        """gradient_thresholds field is accepted on RoleEnvelope."""
        envelope = ConstraintEnvelopeConfig(id="env-1")
        thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=50.0,
                flag_threshold=200.0,
                hold_threshold=500.0,
            )
        )
        role_env = RoleEnvelope(
            id="re-1",
            defining_role_address="org/dept/supervisor",
            target_role_address="org/dept/worker",
            envelope=envelope,
            gradient_thresholds=thresholds,
        )
        assert role_env.gradient_thresholds is not None
        assert role_env.gradient_thresholds.financial is not None
        assert role_env.gradient_thresholds.financial.auto_approve_threshold == 50.0

    def test_gradient_thresholds_defaults_to_none(self) -> None:
        """RoleEnvelope without gradient_thresholds defaults to None."""
        envelope = ConstraintEnvelopeConfig(id="env-1")
        role_env = RoleEnvelope(
            id="re-1",
            defining_role_address="org/dept/supervisor",
            target_role_address="org/dept/worker",
            envelope=envelope,
        )
        assert role_env.gradient_thresholds is None


# ---------------------------------------------------------------------------
# TODO-02: Tightening validation for gradient thresholds
# ---------------------------------------------------------------------------


class TestGradientTighteningValidation:
    """validate_tightening checks gradient thresholds for monotonic tightening."""

    def _make_envelope(self, max_spend: float = 1000.0) -> ConstraintEnvelopeConfig:
        return ConstraintEnvelopeConfig(
            id="test",
            financial=FinancialConstraintConfig(max_spend_usd=max_spend),
        )

    def test_gradient_tightening_valid(self) -> None:
        """Child thresholds <= parent's passes validation."""
        parent = self._make_envelope()
        child = self._make_envelope()
        parent_thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=200.0,
                flag_threshold=500.0,
                hold_threshold=800.0,
            )
        )
        child_thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=100.0,
                flag_threshold=300.0,
                hold_threshold=600.0,
            )
        )
        # Should not raise
        RoleEnvelope.validate_tightening(
            parent_envelope=parent,
            child_envelope=child,
            parent_gradient_thresholds=parent_thresholds,
            child_gradient_thresholds=child_thresholds,
        )

    def test_gradient_tightening_widened(self) -> None:
        """Child auto_approve > parent auto_approve raises violation."""
        parent = self._make_envelope()
        child = self._make_envelope()
        parent_thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=100.0,
                flag_threshold=500.0,
                hold_threshold=800.0,
            )
        )
        child_thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=200.0,  # wider than parent's 100
                flag_threshold=500.0,
                hold_threshold=800.0,
            )
        )
        with pytest.raises(MonotonicTighteningError, match="auto_approve_threshold"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent,
                child_envelope=child,
                parent_gradient_thresholds=parent_thresholds,
                child_gradient_thresholds=child_thresholds,
            )

    def test_gradient_tightening_flag_widened(self) -> None:
        """Child flag_threshold > parent flag_threshold raises violation."""
        parent = self._make_envelope()
        child = self._make_envelope()
        parent_thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=100.0,
                flag_threshold=300.0,
                hold_threshold=800.0,
            )
        )
        child_thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=100.0,
                flag_threshold=500.0,  # wider than parent's 300
                hold_threshold=800.0,
            )
        )
        with pytest.raises(MonotonicTighteningError, match="flag_threshold"):
            RoleEnvelope.validate_tightening(
                parent_envelope=parent,
                child_envelope=child,
                parent_gradient_thresholds=parent_thresholds,
                child_gradient_thresholds=child_thresholds,
            )

    def test_gradient_tightening_no_parent_thresholds(self) -> None:
        """No parent gradient thresholds and child has them -- no violation."""
        parent = self._make_envelope()
        child = self._make_envelope()
        child_thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=100.0,
                flag_threshold=500.0,
                hold_threshold=800.0,
            )
        )
        # No parent thresholds means we can't verify, so skip the check
        RoleEnvelope.validate_tightening(
            parent_envelope=parent,
            child_envelope=child,
            parent_gradient_thresholds=None,
            child_gradient_thresholds=child_thresholds,
        )

    def test_gradient_tightening_no_child_thresholds(self) -> None:
        """Parent has gradient thresholds but child doesn't -- OK (child uses defaults)."""
        parent = self._make_envelope()
        child = self._make_envelope()
        parent_thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=100.0,
                flag_threshold=500.0,
                hold_threshold=800.0,
            )
        )
        # No child thresholds means child uses more restrictive defaults
        RoleEnvelope.validate_tightening(
            parent_envelope=parent,
            child_envelope=child,
            parent_gradient_thresholds=parent_thresholds,
            child_gradient_thresholds=None,
        )


# ---------------------------------------------------------------------------
# TODO-03: Gradient dereliction detection
# ---------------------------------------------------------------------------


class TestGradientDerelictionDetection:
    """check_gradient_dereliction detects overly-permissive gradient config."""

    def test_gradient_dereliction_detected(self) -> None:
        """auto_approve at 95% of limit emits warning."""
        thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=950.0,  # 95% of 1000
                flag_threshold=960.0,
                hold_threshold=980.0,
            )
        )
        envelope = ConstraintEnvelopeConfig(
            id="test",
            financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        )
        role_env = RoleEnvelope(
            id="re-1",
            defining_role_address="org/dept/supervisor",
            target_role_address="org/dept/worker",
            envelope=envelope,
            gradient_thresholds=thresholds,
        )
        warnings = check_gradient_dereliction(role_env, envelope)
        assert len(warnings) >= 1
        assert any(
            "auto_approve" in w.lower()
            or "rubber" in w.lower()
            or "permissive" in w.lower()
            for w in warnings
        )

    def test_gradient_dereliction_acceptable(self) -> None:
        """auto_approve at 50% of limit emits no warning."""
        thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=500.0,  # 50% of 1000
                flag_threshold=700.0,
                hold_threshold=900.0,
            )
        )
        envelope = ConstraintEnvelopeConfig(
            id="test",
            financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        )
        role_env = RoleEnvelope(
            id="re-1",
            defining_role_address="org/dept/supervisor",
            target_role_address="org/dept/worker",
            envelope=envelope,
            gradient_thresholds=thresholds,
        )
        warnings = check_gradient_dereliction(role_env, envelope)
        assert len(warnings) == 0

    def test_gradient_dereliction_no_gradient(self) -> None:
        """No gradient config on RoleEnvelope -- no warnings."""
        envelope = ConstraintEnvelopeConfig(
            id="test",
            financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        )
        role_env = RoleEnvelope(
            id="re-1",
            defining_role_address="org/dept/supervisor",
            target_role_address="org/dept/worker",
            envelope=envelope,
        )
        warnings = check_gradient_dereliction(role_env, envelope)
        assert len(warnings) == 0

    def test_gradient_dereliction_no_financial_on_envelope(self) -> None:
        """Envelope has no financial config -- no warnings even with thresholds."""
        thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=950.0,
                flag_threshold=960.0,
                hold_threshold=980.0,
            )
        )
        envelope = ConstraintEnvelopeConfig(id="test")  # No financial
        role_env = RoleEnvelope(
            id="re-1",
            defining_role_address="org/dept/supervisor",
            target_role_address="org/dept/worker",
            envelope=envelope,
            gradient_thresholds=thresholds,
        )
        warnings = check_gradient_dereliction(role_env, envelope)
        assert len(warnings) == 0

    def test_gradient_dereliction_boundary_at_90_percent(self) -> None:
        """auto_approve at exactly 90% of limit -- right at boundary, emits warning."""
        thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=900.0,  # exactly 90% of 1000
                flag_threshold=950.0,
                hold_threshold=980.0,
            )
        )
        envelope = ConstraintEnvelopeConfig(
            id="test",
            financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        )
        role_env = RoleEnvelope(
            id="re-1",
            defining_role_address="org/dept/supervisor",
            target_role_address="org/dept/worker",
            envelope=envelope,
            gradient_thresholds=thresholds,
        )
        warnings = check_gradient_dereliction(role_env, envelope)
        # >= 0.9 * max_spend means dereliction
        assert len(warnings) >= 1

    def test_gradient_dereliction_just_below_90_percent(self) -> None:
        """auto_approve at 89% of limit -- just below boundary, no warning."""
        thresholds = GradientThresholdsConfig(
            financial=DimensionThresholds(
                auto_approve_threshold=890.0,  # 89% of 1000
                flag_threshold=950.0,
                hold_threshold=980.0,
            )
        )
        envelope = ConstraintEnvelopeConfig(
            id="test",
            financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        )
        role_env = RoleEnvelope(
            id="re-1",
            defining_role_address="org/dept/supervisor",
            target_role_address="org/dept/worker",
            envelope=envelope,
            gradient_thresholds=thresholds,
        )
        warnings = check_gradient_dereliction(role_env, envelope)
        assert len(warnings) == 0
