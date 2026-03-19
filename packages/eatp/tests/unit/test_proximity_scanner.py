# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for ProximityScanner (G2).

Verifies constraint utilization proximity scanning, threshold-based
escalation, monotonic verdict guarantees, and enforcer integration.
"""

from __future__ import annotations

import pytest

from eatp.chain import VerificationLevel
from eatp.constraints.dimension import ConstraintCheckResult
from eatp.enforce.proximity import (
    CONSERVATIVE_PROXIMITY,
    ProximityAlert,
    ProximityConfig,
    ProximityScanner,
)
from eatp.enforce.strict import Verdict


# ---------------------------------------------------------------------------
# 2.1 — ProximityConfig
# ---------------------------------------------------------------------------


class TestProximityConfig:
    """G2: ProximityConfig dataclass validation."""

    def test_default_thresholds(self):
        """Defaults must be flag=0.80, hold=0.95 (D1 cross-SDK aligned)."""
        config = ProximityConfig()
        assert config.flag_threshold == 0.80
        assert config.hold_threshold == 0.95

    def test_conservative_preset(self):
        """CONSERVATIVE_PROXIMITY must be flag=0.70, hold=0.90."""
        assert CONSERVATIVE_PROXIMITY.flag_threshold == 0.70
        assert CONSERVATIVE_PROXIMITY.hold_threshold == 0.90

    def test_custom_thresholds(self):
        """Custom thresholds must be accepted."""
        config = ProximityConfig(flag_threshold=0.50, hold_threshold=0.75)
        assert config.flag_threshold == 0.50
        assert config.hold_threshold == 0.75

    def test_flag_must_be_less_than_hold(self):
        """flag_threshold >= hold_threshold must be rejected."""
        with pytest.raises(ValueError, match="must be less than"):
            ProximityConfig(flag_threshold=0.95, hold_threshold=0.80)

    def test_flag_equals_hold_rejected(self):
        """flag_threshold == hold_threshold must be rejected."""
        with pytest.raises(ValueError, match="must be less than"):
            ProximityConfig(flag_threshold=0.80, hold_threshold=0.80)

    def test_flag_out_of_range(self):
        """flag_threshold outside (0, 1) must be rejected."""
        with pytest.raises(ValueError):
            ProximityConfig(flag_threshold=0.0, hold_threshold=0.95)
        with pytest.raises(ValueError):
            ProximityConfig(flag_threshold=1.0, hold_threshold=0.95)

    def test_hold_out_of_range(self):
        """hold_threshold outside (0, 1] must be rejected."""
        with pytest.raises(ValueError):
            ProximityConfig(flag_threshold=0.80, hold_threshold=0.0)

    def test_dimension_overrides(self):
        """Per-dimension overrides must be stored."""
        config = ProximityConfig(dimension_overrides={"cost_limit": (0.50, 0.70)})
        assert config.dimension_overrides["cost_limit"] == (0.50, 0.70)


# ---------------------------------------------------------------------------
# 2.1 — ProximityScanner.scan()
# ---------------------------------------------------------------------------


class TestProximityScannerScan:
    """G2: ProximityScanner scanning logic."""

    def test_no_results_returns_empty(self):
        """Empty results must produce zero alerts."""
        scanner = ProximityScanner()
        assert scanner.scan([]) == []

    def test_below_flag_no_alert(self):
        """79% usage must NOT trigger alert (below 80% flag)."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=79.0, limit=100.0, remaining=21.0)
        alerts = scanner.scan([result], "cost_limit")
        assert alerts == []

    def test_at_flag_threshold_triggers_flag(self):
        """80% usage must trigger FLAGGED alert."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=80.0, limit=100.0, remaining=20.0)
        alerts = scanner.scan([result], "cost_limit")
        assert len(alerts) == 1
        assert alerts[0].escalated_verdict == Verdict.FLAGGED
        assert alerts[0].usage_ratio == 0.80

    def test_81_percent_triggers_flag(self):
        """81% usage must trigger FLAGGED alert."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=81.0, limit=100.0, remaining=19.0)
        alerts = scanner.scan([result], "cost_limit")
        assert len(alerts) == 1
        assert alerts[0].escalated_verdict == Verdict.FLAGGED

    def test_at_hold_threshold_triggers_hold(self):
        """95% usage must trigger HELD alert."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=95.0, limit=100.0, remaining=5.0)
        alerts = scanner.scan([result], "cost_limit")
        assert len(alerts) == 1
        assert alerts[0].escalated_verdict == Verdict.HELD

    def test_96_percent_triggers_hold(self):
        """96% usage must trigger HELD alert."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=96.0, limit=100.0, remaining=4.0)
        alerts = scanner.scan([result], "cost_limit")
        assert len(alerts) == 1
        assert alerts[0].escalated_verdict == Verdict.HELD

    def test_100_percent_triggers_hold(self):
        """100% usage (at limit) must trigger HELD alert."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=True, reason="at limit", used=100.0, limit=100.0, remaining=0.0)
        alerts = scanner.scan([result], "cost_limit")
        assert len(alerts) == 1
        assert alerts[0].escalated_verdict == Verdict.HELD
        assert alerts[0].usage_ratio == 1.0

    def test_over_limit_triggers_hold(self):
        """Usage > limit must still produce HELD alert."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=False, reason="exceeded", used=110.0, limit=100.0, remaining=0.0)
        alerts = scanner.scan([result], "cost_limit")
        assert len(alerts) == 1
        assert alerts[0].escalated_verdict == Verdict.HELD
        assert alerts[0].usage_ratio == 1.10

    def test_zero_limit_skipped(self):
        """Limit of 0 must be skipped (not crash with division by zero)."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=50.0, limit=0.0, remaining=0.0)
        alerts = scanner.scan([result], "cost_limit")
        assert alerts == []

    def test_negative_limit_skipped(self):
        """Negative limit must be skipped."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=50.0, limit=-10.0, remaining=0.0)
        alerts = scanner.scan([result], "cost_limit")
        assert alerts == []

    def test_none_limit_skipped(self):
        """None limit must be skipped."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=50.0, limit=None, remaining=None)
        alerts = scanner.scan([result], "cost_limit")
        assert alerts == []

    def test_none_used_skipped(self):
        """None used must be skipped."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=None, limit=100.0, remaining=100.0)
        alerts = scanner.scan([result], "cost_limit")
        assert alerts == []

    def test_float_edge_case_just_below_flag(self):
        """0.7999999 must NOT trigger flag (float precision)."""
        scanner = ProximityScanner()
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=79.99999, limit=100.0, remaining=20.0)
        alerts = scanner.scan([result], "cost_limit")
        assert alerts == []

    def test_dimension_overrides_applied(self):
        """Per-dimension overrides must override global thresholds."""
        config = ProximityConfig(
            flag_threshold=0.80,
            hold_threshold=0.95,
            dimension_overrides={"rate_limit": (0.50, 0.70)},
        )
        scanner = ProximityScanner(config)
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=55.0, limit=100.0, remaining=45.0)
        # 55% exceeds the per-dimension flag of 50%
        alerts = scanner.scan([result], "rate_limit")
        assert len(alerts) == 1
        assert alerts[0].escalated_verdict == Verdict.FLAGGED

    def test_dimension_overrides_dont_affect_other_dims(self):
        """Overrides for one dimension must not affect others."""
        config = ProximityConfig(
            flag_threshold=0.80,
            hold_threshold=0.95,
            dimension_overrides={"rate_limit": (0.50, 0.70)},
        )
        scanner = ProximityScanner(config)
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=55.0, limit=100.0, remaining=45.0)
        # 55% does NOT exceed global flag of 80% for cost_limit
        alerts = scanner.scan([result], "cost_limit")
        assert alerts == []


# ---------------------------------------------------------------------------
# 2.1 — ProximityScanner multi-dimension
# ---------------------------------------------------------------------------


class TestProximityScannerMultiDimension:
    """G2: Multi-dimension simultaneous proximity scanning."""

    def test_multi_dimension_scan(self):
        """Multiple dimensions can trigger alerts simultaneously."""
        scanner = ProximityScanner()
        results_by_dim = {
            "cost_limit": [ConstraintCheckResult(satisfied=True, reason="ok", used=85.0, limit=100.0, remaining=15.0)],
            "rate_limit": [ConstraintCheckResult(satisfied=True, reason="ok", used=96.0, limit=100.0, remaining=4.0)],
            "resources": [ConstraintCheckResult(satisfied=True, reason="ok", used=50.0, limit=100.0, remaining=50.0)],
        }
        alerts = scanner.scan_multi(results_by_dim)
        assert len(alerts) == 2  # cost (flagged) + rate (held)
        dimensions = {a.dimension for a in alerts}
        assert dimensions == {"cost_limit", "rate_limit"}

    def test_conservative_preset_at_71_percent(self):
        """71% usage with CONSERVATIVE preset must trigger FLAG."""
        scanner = ProximityScanner(CONSERVATIVE_PROXIMITY)
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=71.0, limit=100.0, remaining=29.0)
        alerts = scanner.scan([result], "cost_limit")
        assert len(alerts) == 1
        assert alerts[0].escalated_verdict == Verdict.FLAGGED

    def test_conservative_preset_at_91_percent(self):
        """91% usage with CONSERVATIVE preset must trigger HOLD."""
        scanner = ProximityScanner(CONSERVATIVE_PROXIMITY)
        result = ConstraintCheckResult(satisfied=True, reason="ok", used=91.0, limit=100.0, remaining=9.0)
        alerts = scanner.scan([result], "cost_limit")
        assert len(alerts) == 1
        assert alerts[0].escalated_verdict == Verdict.HELD


# ---------------------------------------------------------------------------
# 2.1 — ProximityAlert
# ---------------------------------------------------------------------------


class TestProximityAlert:
    """G2: ProximityAlert dataclass."""

    def test_to_dict_roundtrip(self):
        """to_dict must produce a serializable dictionary."""
        alert = ProximityAlert(
            dimension="cost_limit",
            usage_ratio=0.85,
            used=85.0,
            limit=100.0,
            escalated_verdict=Verdict.FLAGGED,
            original_verdict=Verdict.AUTO_APPROVED,
        )
        d = alert.to_dict()
        assert d["dimension"] == "cost_limit"
        assert d["usage_ratio"] == 0.85
        assert d["used"] == 85.0
        assert d["limit"] == 100.0
        assert d["escalated_verdict"] == "flagged"
        assert d["original_verdict"] == "auto_approved"


# ---------------------------------------------------------------------------
# 2.4 — Monotonic escalation
# ---------------------------------------------------------------------------


class TestProximityEscalation:
    """G2: Monotonic verdict escalation guarantees."""

    def test_escalate_from_auto_approved_to_flagged(self):
        """AUTO_APPROVED + FLAG alert → FLAGGED."""
        scanner = ProximityScanner()
        alerts = [
            ProximityAlert(
                dimension="cost_limit",
                usage_ratio=0.85,
                used=85.0,
                limit=100.0,
                escalated_verdict=Verdict.FLAGGED,
                original_verdict=Verdict.AUTO_APPROVED,
            )
        ]
        result = scanner.escalate_verdict(Verdict.AUTO_APPROVED, alerts)
        assert result == Verdict.FLAGGED

    def test_escalate_from_auto_approved_to_held(self):
        """AUTO_APPROVED + HOLD alert → HELD."""
        scanner = ProximityScanner()
        alerts = [
            ProximityAlert(
                dimension="cost_limit",
                usage_ratio=0.96,
                used=96.0,
                limit=100.0,
                escalated_verdict=Verdict.HELD,
                original_verdict=Verdict.AUTO_APPROVED,
            )
        ]
        result = scanner.escalate_verdict(Verdict.AUTO_APPROVED, alerts)
        assert result == Verdict.HELD

    def test_no_downgrade_from_held(self):
        """HELD base + FLAG alert must NOT downgrade to FLAGGED."""
        scanner = ProximityScanner()
        alerts = [
            ProximityAlert(
                dimension="cost_limit",
                usage_ratio=0.85,
                used=85.0,
                limit=100.0,
                escalated_verdict=Verdict.FLAGGED,
                original_verdict=Verdict.AUTO_APPROVED,
            )
        ]
        result = scanner.escalate_verdict(Verdict.HELD, alerts)
        assert result == Verdict.HELD

    def test_no_downgrade_from_blocked(self):
        """BLOCKED base must never be downgraded."""
        scanner = ProximityScanner()
        alerts = [
            ProximityAlert(
                dimension="cost_limit",
                usage_ratio=0.85,
                used=85.0,
                limit=100.0,
                escalated_verdict=Verdict.FLAGGED,
                original_verdict=Verdict.AUTO_APPROVED,
            )
        ]
        result = scanner.escalate_verdict(Verdict.BLOCKED, alerts)
        assert result == Verdict.BLOCKED

    def test_empty_alerts_no_change(self):
        """Empty alerts must return base verdict unchanged."""
        scanner = ProximityScanner()
        assert scanner.escalate_verdict(Verdict.AUTO_APPROVED, []) == Verdict.AUTO_APPROVED
        assert scanner.escalate_verdict(Verdict.FLAGGED, []) == Verdict.FLAGGED
        assert scanner.escalate_verdict(Verdict.HELD, []) == Verdict.HELD
        assert scanner.escalate_verdict(Verdict.BLOCKED, []) == Verdict.BLOCKED

    def test_multiple_alerts_highest_wins(self):
        """Multiple alerts: highest escalation level wins."""
        scanner = ProximityScanner()
        alerts = [
            ProximityAlert(
                dimension="cost_limit",
                usage_ratio=0.85,
                used=85.0,
                limit=100.0,
                escalated_verdict=Verdict.FLAGGED,
                original_verdict=Verdict.AUTO_APPROVED,
            ),
            ProximityAlert(
                dimension="rate_limit",
                usage_ratio=0.96,
                used=96.0,
                limit=100.0,
                escalated_verdict=Verdict.HELD,
                original_verdict=Verdict.AUTO_APPROVED,
            ),
        ]
        result = scanner.escalate_verdict(Verdict.AUTO_APPROVED, alerts)
        assert result == Verdict.HELD


# ---------------------------------------------------------------------------
# 2.2/2.3 — Enforcer integration backward compat
# ---------------------------------------------------------------------------


class TestProximityBackwardCompat:
    """G2: StrictEnforcer and ShadowEnforcer backward compatibility."""

    def test_strict_enforcer_no_args_unchanged(self):
        """StrictEnforcer() with no args must behave identically to pre-Phase-2."""
        from eatp.chain import VerificationResult
        from eatp.enforce.strict import StrictEnforcer

        enforcer = StrictEnforcer()
        # A valid result with no violations should still be AUTO_APPROVED
        result = VerificationResult(valid=True, level=VerificationLevel.STANDARD, reason="ok")
        verdict = enforcer.classify(result)
        assert verdict == Verdict.AUTO_APPROVED

    def test_shadow_enforcer_no_args_unchanged(self):
        """ShadowEnforcer() with no args must behave identically to pre-Phase-2."""
        from eatp.chain import VerificationResult
        from eatp.enforce.shadow import ShadowEnforcer

        shadow = ShadowEnforcer()
        result = VerificationResult(valid=True, level=VerificationLevel.STANDARD, reason="ok")
        verdict = shadow.check(agent_id="agent-001", action="test", result=result)
        assert verdict == Verdict.AUTO_APPROVED
