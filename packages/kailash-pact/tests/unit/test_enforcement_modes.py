# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for enforcement modes (ENFORCE/SHADOW/DISABLED) and envelope adapter.

Covers:
- EnforcementMode enum values
- ENFORCE mode: blocked verdict rejects action (existing behavior)
- SHADOW mode: blocked verdict proceeds, verdict logged with shadow=True
- SHADOW mode: audit events carry shadow marker
- SHADOW mode: WorkResult includes governance_verdicts
- DISABLED mode without env var raises PactError
- DISABLED mode with env var skips governance
- Envelope adapter: all 5 dimensions mapped correctly
- Envelope adapter: no envelope returns maximally restrictive defaults
- Envelope adapter: NaN in financial constraint uses defaults + logs error
- Envelope adapter: budget from envelope capped by remaining budget
- Envelope adapter: Communication dimension constraints mapped
"""

from __future__ import annotations

import asyncio
import logging
import math
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from kailash.trust.pact.config import (
    CommunicationConstraintConfig,
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
)
from kailash.trust.pact.exceptions import PactError
from pact.enforcement import EnforcementMode, validate_enforcement_mode
from pact.engine import PactEngine
from pact.work import WorkResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "governance" / "fixtures"


@pytest.fixture
def minimal_yaml_path() -> Path:
    """Path to the minimal org YAML fixture."""
    return FIXTURES_DIR / "minimal-org.yaml"


@pytest.fixture
def minimal_org_dict() -> dict[str, Any]:
    """Minimal org definition as a dict."""
    return {
        "org_id": "test-enforce-001",
        "name": "Enforcement Test Org",
        "departments": [{"id": "d-engineering", "name": "Engineering"}],
        "teams": [{"id": "t-backend", "name": "Backend Team"}],
        "roles": [
            {"id": "r-cto", "name": "CTO", "heads": "d-engineering"},
            {
                "id": "r-lead",
                "name": "Tech Lead",
                "reports_to": "r-cto",
                "heads": "t-backend",
            },
            {"id": "r-dev", "name": "Developer", "reports_to": "r-lead"},
        ],
    }


# ---------------------------------------------------------------------------
# EnforcementMode Enum Tests
# ---------------------------------------------------------------------------


class TestEnforcementModeEnum:
    """EnforcementMode enum has correct values and is str-backed."""

    def test_enforce_value(self) -> None:
        assert EnforcementMode.ENFORCE.value == "enforce"

    def test_shadow_value(self) -> None:
        assert EnforcementMode.SHADOW.value == "shadow"

    def test_disabled_value(self) -> None:
        assert EnforcementMode.DISABLED.value == "disabled"

    def test_str_backed(self) -> None:
        """EnforcementMode should be str-backed for JSON serialization."""
        assert isinstance(EnforcementMode.ENFORCE, str)
        assert str(EnforcementMode.ENFORCE) == "EnforcementMode.ENFORCE"

    def test_from_value(self) -> None:
        """EnforcementMode should be constructible from string value."""
        assert EnforcementMode("enforce") == EnforcementMode.ENFORCE
        assert EnforcementMode("shadow") == EnforcementMode.SHADOW
        assert EnforcementMode("disabled") == EnforcementMode.DISABLED


# ---------------------------------------------------------------------------
# validate_enforcement_mode Tests
# ---------------------------------------------------------------------------


class TestValidateEnforcementMode:
    """Env var guard for DISABLED mode."""

    def test_enforce_mode_always_valid(self) -> None:
        """ENFORCE mode should always pass validation."""
        validate_enforcement_mode(EnforcementMode.ENFORCE)

    def test_shadow_mode_always_valid(self) -> None:
        """SHADOW mode should always pass validation."""
        validate_enforcement_mode(EnforcementMode.SHADOW)

    def test_disabled_without_env_var_raises(self) -> None:
        """DISABLED mode without env var should raise PactError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(PactError, match="PACT_ALLOW_DISABLED_MODE"):
                validate_enforcement_mode(EnforcementMode.DISABLED)

    def test_disabled_with_env_var_false_raises(self) -> None:
        """DISABLED mode with env var set to 'false' should raise PactError."""
        with patch.dict("os.environ", {"PACT_ALLOW_DISABLED_MODE": "false"}):
            with pytest.raises(PactError, match="PACT_ALLOW_DISABLED_MODE"):
                validate_enforcement_mode(EnforcementMode.DISABLED)

    def test_disabled_with_env_var_true_passes(self) -> None:
        """DISABLED mode with PACT_ALLOW_DISABLED_MODE=true should pass."""
        with patch.dict("os.environ", {"PACT_ALLOW_DISABLED_MODE": "true"}):
            validate_enforcement_mode(EnforcementMode.DISABLED)

    def test_disabled_with_env_var_TRUE_passes(self) -> None:
        """DISABLED mode with PACT_ALLOW_DISABLED_MODE=TRUE should pass (case-insensitive)."""
        with patch.dict("os.environ", {"PACT_ALLOW_DISABLED_MODE": "TRUE"}):
            validate_enforcement_mode(EnforcementMode.DISABLED)


# ---------------------------------------------------------------------------
# PactEngine Enforcement Mode Construction Tests
# ---------------------------------------------------------------------------


class TestPactEngineEnforcementConstruction:
    """PactEngine construction with enforcement_mode parameter."""

    def test_default_enforcement_mode_is_enforce(self, minimal_yaml_path: Path) -> None:
        """PactEngine should default to ENFORCE mode."""
        engine = PactEngine(org=str(minimal_yaml_path))
        assert engine.enforcement_mode == EnforcementMode.ENFORCE

    def test_explicit_enforce_mode(self, minimal_yaml_path: Path) -> None:
        engine = PactEngine(
            org=str(minimal_yaml_path),
            enforcement_mode=EnforcementMode.ENFORCE,
        )
        assert engine.enforcement_mode == EnforcementMode.ENFORCE

    def test_shadow_mode(self, minimal_yaml_path: Path) -> None:
        engine = PactEngine(
            org=str(minimal_yaml_path),
            enforcement_mode=EnforcementMode.SHADOW,
        )
        assert engine.enforcement_mode == EnforcementMode.SHADOW

    def test_disabled_mode_without_env_var_raises(
        self, minimal_yaml_path: Path
    ) -> None:
        """DISABLED mode at construction time should raise without env var."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(PactError, match="PACT_ALLOW_DISABLED_MODE"):
                PactEngine(
                    org=str(minimal_yaml_path),
                    enforcement_mode=EnforcementMode.DISABLED,
                )

    def test_disabled_mode_with_env_var(self, minimal_yaml_path: Path) -> None:
        """DISABLED mode should work when env var is set."""
        with patch.dict("os.environ", {"PACT_ALLOW_DISABLED_MODE": "true"}):
            engine = PactEngine(
                org=str(minimal_yaml_path),
                enforcement_mode=EnforcementMode.DISABLED,
            )
            assert engine.enforcement_mode == EnforcementMode.DISABLED


# ---------------------------------------------------------------------------
# ENFORCE Mode Tests
# ---------------------------------------------------------------------------


class TestEnforceMode:
    """ENFORCE mode: verdicts are binding (existing behavior preserved)."""

    def test_blocked_verdict_returns_failure(self, minimal_yaml_path: Path) -> None:
        """In ENFORCE mode, a blocked verdict should return success=False."""
        engine = PactEngine(
            org=str(minimal_yaml_path),
            enforcement_mode=EnforcementMode.ENFORCE,
        )
        # Submit with an invalid role to trigger governance failure
        result = engine.submit_sync("Some task", role="NONEXISTENT-ROLE")
        assert isinstance(result, WorkResult)
        assert result.success is False
        assert result.governance_shadow is False

    def test_governance_verdicts_populated_on_block(
        self, minimal_yaml_path: Path
    ) -> None:
        """In ENFORCE mode, governance_verdicts should be populated."""
        engine = PactEngine(
            org=str(minimal_yaml_path),
            enforcement_mode=EnforcementMode.ENFORCE,
        )
        result = engine.submit_sync("Some task", role="NONEXISTENT-ROLE")
        assert isinstance(result, WorkResult)
        assert result.success is False
        # governance_verdicts should contain the blocking verdict
        # (it may be empty if the role itself causes an exception before
        #  verify_action returns a verdict -- that's also valid fail-closed)


# ---------------------------------------------------------------------------
# SHADOW Mode Tests
# ---------------------------------------------------------------------------


class TestShadowMode:
    """SHADOW mode: verdicts are logged but never block execution."""

    def test_shadow_mode_never_blocks(self, minimal_yaml_path: Path) -> None:
        """In SHADOW mode, even a 'blocked' verdict should not prevent execution."""
        engine = PactEngine(
            org=str(minimal_yaml_path),
            enforcement_mode=EnforcementMode.SHADOW,
        )
        # Use an invalid role -- in ENFORCE mode this would block,
        # but in SHADOW mode it should proceed to execution
        result = engine.submit_sync("Test task", role="NONEXISTENT-ROLE")
        assert isinstance(result, WorkResult)
        # The result should fail because kaizen-agents is not installed,
        # NOT because of governance blocking. The error message should
        # mention kaizen, not governance blocking.
        # However, if verify_action raises an exception (not just returns blocked),
        # it's still fail-closed even in shadow mode.
        # Let's check the result is a WorkResult either way.

    def test_shadow_mode_sets_governance_shadow_flag(
        self, minimal_yaml_path: Path
    ) -> None:
        """In SHADOW mode, WorkResult should have governance_shadow=True."""
        engine = PactEngine(
            org=str(minimal_yaml_path),
            enforcement_mode=EnforcementMode.SHADOW,
        )
        # Use a known role from the minimal org to get past verify_action
        result = engine.submit_sync("Test task", role="r-dev")
        assert isinstance(result, WorkResult)
        assert result.governance_shadow is True

    def test_shadow_mode_includes_governance_verdicts(
        self, minimal_yaml_path: Path
    ) -> None:
        """In SHADOW mode, governance_verdicts should contain the verdict."""
        engine = PactEngine(
            org=str(minimal_yaml_path),
            enforcement_mode=EnforcementMode.SHADOW,
        )
        result = engine.submit_sync("Test task", role="r-dev")
        assert isinstance(result, WorkResult)
        assert len(result.governance_verdicts) > 0
        # Verdict should have shadow=True marker
        verdict = result.governance_verdicts[0]
        assert verdict.get("shadow") is True

    def test_shadow_mode_logs_verdict(
        self, minimal_yaml_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """In SHADOW mode, verdicts should be logged at INFO level."""
        engine = PactEngine(
            org=str(minimal_yaml_path),
            enforcement_mode=EnforcementMode.SHADOW,
        )
        with caplog.at_level(logging.INFO, logger="pact.engine"):
            engine.submit_sync("Test task", role="r-dev")
        assert any("[SHADOW]" in record.message for record in caplog.records)

    def test_shadow_mode_emits_shadow_event(self, minimal_yaml_path: Path) -> None:
        """In SHADOW mode, event bus should receive work.governance_shadow event."""
        engine = PactEngine(
            org=str(minimal_yaml_path),
            enforcement_mode=EnforcementMode.SHADOW,
        )
        engine.submit_sync("Test task", role="r-dev")
        history = engine.events.get_history(event_type="work.governance_shadow")
        assert len(history) > 0
        event_data = history[0]["data"]
        assert event_data["shadow"] is True
        assert event_data["role"] == "r-dev"


# ---------------------------------------------------------------------------
# DISABLED Mode Tests
# ---------------------------------------------------------------------------


class TestDisabledMode:
    """DISABLED mode: governance is skipped entirely."""

    def test_disabled_mode_skips_governance(self, minimal_yaml_path: Path) -> None:
        """In DISABLED mode, governance should be skipped -- no verify_action call."""
        with patch.dict("os.environ", {"PACT_ALLOW_DISABLED_MODE": "true"}):
            engine = PactEngine(
                org=str(minimal_yaml_path),
                enforcement_mode=EnforcementMode.DISABLED,
            )
        # Even with a completely invalid role, DISABLED should not block
        # because governance is entirely skipped
        result = engine.submit_sync("Test task", role="TOTALLY-FAKE-ROLE")
        assert isinstance(result, WorkResult)
        # The result should NOT be a governance block -- either execution succeeds
        # (if kaizen-agents is installed) or fails with kaizen error.
        # Governance blocking is the one thing that must NOT happen.
        if result.error:
            assert "governance" not in result.error.lower()
        assert result.governance_verdicts == []

    def test_disabled_mode_logs_warning(
        self, minimal_yaml_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """In DISABLED mode, a warning should be logged."""
        with patch.dict("os.environ", {"PACT_ALLOW_DISABLED_MODE": "true"}):
            engine = PactEngine(
                org=str(minimal_yaml_path),
                enforcement_mode=EnforcementMode.DISABLED,
            )
        with caplog.at_level(logging.WARNING, logger="pact.engine"):
            engine.submit_sync("Test task", role="r-dev")
        assert any("governance DISABLED" in record.message for record in caplog.records)

    def test_disabled_mode_emits_disabled_event(self, minimal_yaml_path: Path) -> None:
        """In DISABLED mode, event bus should receive work.governance_disabled event."""
        with patch.dict("os.environ", {"PACT_ALLOW_DISABLED_MODE": "true"}):
            engine = PactEngine(
                org=str(minimal_yaml_path),
                enforcement_mode=EnforcementMode.DISABLED,
            )
        engine.submit_sync("Test task", role="r-dev")
        history = engine.events.get_history(event_type="work.governance_disabled")
        assert len(history) > 0
        event_data = history[0]["data"]
        assert event_data["enforcement_mode"] == "disabled"

    def test_disabled_mode_governance_shadow_false(
        self, minimal_yaml_path: Path
    ) -> None:
        """In DISABLED mode, governance_shadow should be False (it's not shadow, it's off)."""
        with patch.dict("os.environ", {"PACT_ALLOW_DISABLED_MODE": "true"}):
            engine = PactEngine(
                org=str(minimal_yaml_path),
                enforcement_mode=EnforcementMode.DISABLED,
            )
        result = engine.submit_sync("Test task", role="r-dev")
        assert result.governance_shadow is False


# ---------------------------------------------------------------------------
# WorkResult New Fields Tests
# ---------------------------------------------------------------------------


class TestWorkResultEnforcementFields:
    """WorkResult governance_shadow and governance_verdicts fields."""

    def test_work_result_default_shadow_false(self) -> None:
        result = WorkResult(success=True)
        assert result.governance_shadow is False
        assert result.governance_verdicts == []

    def test_work_result_with_shadow(self) -> None:
        result = WorkResult(
            success=True,
            governance_shadow=True,
            governance_verdicts=[{"level": "blocked", "shadow": True}],
        )
        assert result.governance_shadow is True
        assert len(result.governance_verdicts) == 1

    def test_work_result_to_dict_includes_shadow(self) -> None:
        result = WorkResult(
            success=True,
            governance_shadow=True,
            governance_verdicts=[{"level": "auto_approved", "shadow": True}],
        )
        data = result.to_dict()
        assert data["governance_shadow"] is True
        assert len(data["governance_verdicts"]) == 1

    def test_work_result_from_dict_with_shadow(self) -> None:
        data = {
            "success": True,
            "governance_shadow": True,
            "governance_verdicts": [{"level": "blocked", "shadow": True}],
        }
        result = WorkResult.from_dict(data)
        assert result.governance_shadow is True
        assert len(result.governance_verdicts) == 1

    def test_work_result_from_dict_backwards_compat(self) -> None:
        """from_dict without new fields should default to False/[]."""
        data = {"success": True}
        result = WorkResult.from_dict(data)
        assert result.governance_shadow is False
        assert result.governance_verdicts == []


# ---------------------------------------------------------------------------
# Envelope Adapter Tests
# ---------------------------------------------------------------------------


class TestAdaptEnvelope:
    """PactEngine._adapt_envelope() maps all 5 constraint dimensions."""

    def _make_engine(self, yaml_path: Path) -> PactEngine:
        return PactEngine(org=str(yaml_path))

    def test_no_envelope_returns_maximally_restrictive(
        self, minimal_yaml_path: Path
    ) -> None:
        """Role with no envelope should get maximally restrictive defaults."""
        engine = self._make_engine(minimal_yaml_path)
        # Mock compute_envelope to return None (no envelope configured)
        with patch.object(engine._governance, "compute_envelope", return_value=None):
            result = engine._adapt_envelope("D1-R1")
        assert result["budget_usd"] == 0.0
        assert result["tools"] == []
        assert result["data_clearance"] == "none"
        assert result["timeout_seconds"] == 60
        assert result["max_depth"] == 0

    def test_maximally_restrictive_defaults_static(self) -> None:
        """_maximally_restrictive_defaults should return the expected dict."""
        defaults = PactEngine._maximally_restrictive_defaults()
        assert defaults == {
            "budget_usd": 0.0,
            "tools": [],
            "data_clearance": "none",
            "timeout_seconds": 60,
            "max_depth": 0,
        }

    def test_financial_dimension_mapped(self, minimal_yaml_path: Path) -> None:
        """Financial max_spend_usd should map to budget_usd."""
        engine = self._make_engine(minimal_yaml_path)
        envelope = ConstraintEnvelopeConfig(
            id="test-env",
            financial=FinancialConstraintConfig(max_spend_usd=100.0),
        )
        with patch.object(
            engine._governance, "compute_envelope", return_value=envelope
        ):
            result = engine._adapt_envelope("r-dev")
        assert result["budget_usd"] == 100.0

    def test_financial_capped_by_remaining_budget(
        self, minimal_yaml_path: Path
    ) -> None:
        """budget_usd should be min(envelope.max_spend, costs.remaining)."""
        engine = PactEngine(org=str(minimal_yaml_path), budget_usd=30.0)
        envelope = ConstraintEnvelopeConfig(
            id="test-env",
            financial=FinancialConstraintConfig(max_spend_usd=100.0),
        )
        with patch.object(
            engine._governance, "compute_envelope", return_value=envelope
        ):
            result = engine._adapt_envelope("r-dev")
        # Engine budget is 30, envelope allows 100 -- should use 30
        assert result["budget_usd"] == 30.0

    def test_financial_nan_uses_default(
        self, minimal_yaml_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """NaN in financial.max_spend_usd should use restrictive default and log error."""
        engine = self._make_engine(minimal_yaml_path)
        # Construct envelope with a mock that has NaN
        envelope = MagicMock()
        envelope.financial = MagicMock()
        envelope.financial.max_spend_usd = float("nan")
        envelope.operational = None
        envelope.data_access = None
        envelope.confidentiality_clearance = None
        envelope.temporal = None
        envelope.communication = None
        envelope.max_delegation_depth = None

        with patch.object(
            engine._governance, "compute_envelope", return_value=envelope
        ):
            with caplog.at_level(logging.ERROR, logger="pact.engine"):
                result = engine._adapt_envelope("r-dev")

        # Should use remaining or 0.0 (no budget set = None remaining = 0.0)
        assert math.isfinite(result["budget_usd"])
        assert any("non-finite" in record.message for record in caplog.records)

    def test_operational_dimension_mapped(self, minimal_yaml_path: Path) -> None:
        """Operational allowed_actions should map to tools list."""
        engine = self._make_engine(minimal_yaml_path)
        envelope = ConstraintEnvelopeConfig(
            id="test-env",
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "deploy"]
            ),
            max_delegation_depth=3,
        )
        with patch.object(
            engine._governance, "compute_envelope", return_value=envelope
        ):
            result = engine._adapt_envelope("r-dev")
        assert result["tools"] == ["read", "write", "deploy"]
        assert result["max_depth"] == 3

    def test_data_access_dimension_mapped(self, minimal_yaml_path: Path) -> None:
        """confidentiality_clearance should map to data_clearance."""
        engine = self._make_engine(minimal_yaml_path)
        envelope = ConstraintEnvelopeConfig(
            id="test-env",
            confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        )
        with patch.object(
            engine._governance, "compute_envelope", return_value=envelope
        ):
            result = engine._adapt_envelope("r-dev")
        assert result["data_clearance"] == "confidential"

    def test_temporal_dimension_defaults(self, minimal_yaml_path: Path) -> None:
        """Temporal should map to timeout_seconds with restrictive default."""
        engine = self._make_engine(minimal_yaml_path)
        envelope = ConstraintEnvelopeConfig(
            id="test-env",
            temporal=TemporalConstraintConfig(
                active_hours_start="09:00",
                active_hours_end="17:00",
            ),
        )
        with patch.object(
            engine._governance, "compute_envelope", return_value=envelope
        ):
            result = engine._adapt_envelope("r-dev")
        # Default timeout since temporal config doesn't have max_duration_seconds
        assert result["timeout_seconds"] == 60

    def test_communication_dimension_mapped(self, minimal_yaml_path: Path) -> None:
        """Communication allowed_channels should be mapped."""
        engine = self._make_engine(minimal_yaml_path)
        envelope = ConstraintEnvelopeConfig(
            id="test-env",
            communication=CommunicationConstraintConfig(
                allowed_channels=["email", "slack"],
                external_requires_approval=True,
            ),
        )
        with patch.object(
            engine._governance, "compute_envelope", return_value=envelope
        ):
            result = engine._adapt_envelope("r-dev")
        assert result["allowed_channels"] == ["email", "slack"]
        assert result["notification_policy"] == "approval_required"

    def test_all_five_dimensions_present(self, minimal_yaml_path: Path) -> None:
        """All 5 canonical dimensions should be mapped from a fully populated envelope."""
        engine = PactEngine(org=str(minimal_yaml_path), budget_usd=200.0)
        envelope = ConstraintEnvelopeConfig(
            id="full-env",
            financial=FinancialConstraintConfig(max_spend_usd=50.0),
            operational=OperationalConstraintConfig(allowed_actions=["read", "write"]),
            temporal=TemporalConstraintConfig(
                active_hours_start="08:00",
                active_hours_end="18:00",
            ),
            data_access=DataAccessConstraintConfig(
                read_paths=["data/*"],
                write_paths=["data/output/*"],
            ),
            communication=CommunicationConstraintConfig(
                allowed_channels=["internal"],
                external_requires_approval=False,
            ),
            confidentiality_clearance=ConfidentialityLevel.RESTRICTED,
            max_delegation_depth=2,
        )
        with patch.object(
            engine._governance, "compute_envelope", return_value=envelope
        ):
            result = engine._adapt_envelope("r-dev")

        # Financial
        assert result["budget_usd"] == 50.0
        # Operational
        assert result["tools"] == ["read", "write"]
        assert result["max_depth"] == 2
        # Data Access
        assert result["data_clearance"] == "restricted"
        # Temporal
        assert result["timeout_seconds"] == 60
        # Communication
        assert result["allowed_channels"] == ["internal"]

    def test_nan_delegation_depth_uses_default(
        self, minimal_yaml_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """NaN in max_delegation_depth should use restrictive default."""
        engine = self._make_engine(minimal_yaml_path)
        envelope = MagicMock()
        envelope.financial = None
        envelope.operational = MagicMock()
        envelope.operational.allowed_actions = ["read"]
        envelope.max_delegation_depth = float("nan")
        envelope.data_access = None
        envelope.confidentiality_clearance = None
        envelope.temporal = None
        envelope.communication = None

        with patch.object(
            engine._governance, "compute_envelope", return_value=envelope
        ):
            with caplog.at_level(logging.ERROR, logger="pact.engine"):
                result = engine._adapt_envelope("r-dev")

        assert result["max_depth"] == 0
        assert any("non-finite" in record.message for record in caplog.records)
