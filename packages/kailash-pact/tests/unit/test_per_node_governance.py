# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for PR 1B: HELD verdict + per-node governance.

Covers:
- GovernanceVerdict.is_held / is_blocked properties
- GovernanceHeldError is distinct from PactError
- HeldActionCallback with return True -> proceeds
- HeldActionCallback with return False -> blocks
- No on_held -> GovernanceHeldError raised
- _DefaultGovernanceCallback handles all verdict types
- Backward compat: PactEngine without on_held works
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from dataclasses import dataclass

import pytest

from kailash.trust.pact.verdict import GovernanceVerdict
from kailash.trust.pact.exceptions import PactError
from pact.engine import (
    GovernanceHeldError,
    HeldActionCallback,
    GovernanceCallback,
    PactEngine,
    _DefaultGovernanceCallback,
)


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
        "org_id": "test-minimal-001",
        "name": "Minimal Test Org",
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


def _make_verdict(level: str, reason: str = "test reason") -> GovernanceVerdict:
    """Create a GovernanceVerdict with the given level."""
    return GovernanceVerdict(
        level=level,
        reason=reason,
        role_address="D1-T1-R1",
        action="test_action",
    )


class _FakeGovernance:
    """Fake governance engine that returns a configurable verdict."""

    def __init__(self, verdict: GovernanceVerdict) -> None:
        self._verdict = verdict

    def verify_action(
        self,
        role_address: str,
        action: str,
        context: dict[str, Any],
    ) -> GovernanceVerdict:
        return self._verdict


# ---------------------------------------------------------------------------
# GovernanceVerdict.is_held / is_blocked tests
# ---------------------------------------------------------------------------


class TestVerdictProperties:
    """GovernanceVerdict.is_held and is_blocked return correct values."""

    def test_is_held_true_for_held_level(self) -> None:
        verdict = _make_verdict("held")
        assert verdict.is_held is True

    def test_is_held_false_for_auto_approved(self) -> None:
        verdict = _make_verdict("auto_approved")
        assert verdict.is_held is False

    def test_is_held_false_for_blocked(self) -> None:
        verdict = _make_verdict("blocked")
        assert verdict.is_held is False

    def test_is_held_false_for_flagged(self) -> None:
        verdict = _make_verdict("flagged")
        assert verdict.is_held is False

    def test_is_blocked_true_for_blocked_level(self) -> None:
        verdict = _make_verdict("blocked")
        assert verdict.is_blocked is True

    def test_is_blocked_false_for_auto_approved(self) -> None:
        verdict = _make_verdict("auto_approved")
        assert verdict.is_blocked is False

    def test_is_blocked_false_for_held(self) -> None:
        verdict = _make_verdict("held")
        assert verdict.is_blocked is False

    def test_is_blocked_false_for_flagged(self) -> None:
        verdict = _make_verdict("flagged")
        assert verdict.is_blocked is False

    def test_allowed_still_works_for_auto_approved(self) -> None:
        """Backward compat: allowed property unchanged."""
        verdict = _make_verdict("auto_approved")
        assert verdict.allowed is True

    def test_allowed_still_works_for_flagged(self) -> None:
        verdict = _make_verdict("flagged")
        assert verdict.allowed is True

    def test_allowed_false_for_held(self) -> None:
        verdict = _make_verdict("held")
        assert verdict.allowed is False

    def test_allowed_false_for_blocked(self) -> None:
        verdict = _make_verdict("blocked")
        assert verdict.allowed is False


# ---------------------------------------------------------------------------
# GovernanceHeldError tests
# ---------------------------------------------------------------------------


class TestGovernanceHeldError:
    """GovernanceHeldError is distinct from PactError and carries context."""

    def test_governance_held_error_is_distinct_from_pact_error(self) -> None:
        """GovernanceHeldError should NOT be caught by except PactError."""
        verdict = _make_verdict("held")
        err = GovernanceHeldError(
            verdict=verdict,
            role="D1-R1",
            action="send_email",
        )
        assert not isinstance(err, PactError)

    def test_governance_held_error_carries_verdict(self) -> None:
        verdict = _make_verdict("held")
        err = GovernanceHeldError(
            verdict=verdict,
            role="D1-R1",
            action="send_email",
        )
        assert err.verdict is verdict

    def test_governance_held_error_carries_role(self) -> None:
        verdict = _make_verdict("held")
        err = GovernanceHeldError(
            verdict=verdict,
            role="D1-R1",
            action="send_email",
        )
        assert err.role == "D1-R1"

    def test_governance_held_error_carries_action(self) -> None:
        verdict = _make_verdict("held")
        err = GovernanceHeldError(
            verdict=verdict,
            role="D1-R1",
            action="send_email",
        )
        assert err.action == "send_email"

    def test_governance_held_error_carries_context(self) -> None:
        verdict = _make_verdict("held")
        ctx = {"recipient": "user@example.com"}
        err = GovernanceHeldError(
            verdict=verdict,
            role="D1-R1",
            action="send_email",
            context=ctx,
        )
        assert err.context == ctx

    def test_governance_held_error_default_context(self) -> None:
        verdict = _make_verdict("held")
        err = GovernanceHeldError(
            verdict=verdict,
            role="D1-R1",
            action="send_email",
        )
        assert err.context == {}

    def test_governance_held_error_message(self) -> None:
        verdict = _make_verdict("held")
        err = GovernanceHeldError(
            verdict=verdict,
            role="D1-R1",
            action="send_email",
        )
        assert "D1-R1" in str(err)
        assert "send_email" in str(err)
        assert "held for human review" in str(err).lower()


# ---------------------------------------------------------------------------
# _DefaultGovernanceCallback tests
# ---------------------------------------------------------------------------


class TestDefaultGovernanceCallback:
    """_DefaultGovernanceCallback handles all verdict types correctly."""

    def test_auto_approved_verdict_returns_verdict(self) -> None:
        """auto_approved verdict should return the verdict directly."""
        verdict = _make_verdict("auto_approved")
        governance = _FakeGovernance(verdict)
        callback = _DefaultGovernanceCallback(governance)
        result = asyncio.run(callback("D1-R1", "submit", {}))
        assert result is verdict

    def test_flagged_verdict_returns_verdict(self) -> None:
        """flagged verdict should return the verdict directly."""
        verdict = _make_verdict("flagged")
        governance = _FakeGovernance(verdict)
        callback = _DefaultGovernanceCallback(governance)
        result = asyncio.run(callback("D1-R1", "submit", {}))
        assert result is verdict

    def test_held_verdict_no_callback_raises_held_error(self) -> None:
        """held verdict with no on_held callback should raise GovernanceHeldError."""
        verdict = _make_verdict("held")
        governance = _FakeGovernance(verdict)
        callback = _DefaultGovernanceCallback(governance, on_held=None)
        with pytest.raises(GovernanceHeldError) as exc_info:
            asyncio.run(callback("D1-R1", "submit", {"key": "val"}))
        assert exc_info.value.role == "D1-R1"
        assert exc_info.value.action == "submit"
        assert exc_info.value.verdict is verdict
        assert exc_info.value.context == {"key": "val"}

    def test_held_verdict_callback_returns_true_proceeds(self) -> None:
        """held verdict with on_held returning True should return the verdict."""

        async def approve_held(
            verdict: Any, role: str, action: str, context: dict[str, Any]
        ) -> bool:
            return True

        verdict = _make_verdict("held")
        governance = _FakeGovernance(verdict)
        callback = _DefaultGovernanceCallback(governance, on_held=approve_held)
        result = asyncio.run(callback("D1-R1", "submit", {}))
        assert result is verdict

    def test_held_verdict_callback_returns_false_raises_held_error(self) -> None:
        """held verdict with on_held returning False should raise GovernanceHeldError."""

        async def reject_held(
            verdict: Any, role: str, action: str, context: dict[str, Any]
        ) -> bool:
            return False

        verdict = _make_verdict("held")
        governance = _FakeGovernance(verdict)
        callback = _DefaultGovernanceCallback(governance, on_held=reject_held)
        with pytest.raises(GovernanceHeldError) as exc_info:
            asyncio.run(callback("D1-R1", "submit", {}))
        assert exc_info.value.verdict is verdict

    def test_blocked_verdict_raises_pact_error(self) -> None:
        """blocked verdict should raise PactError."""
        verdict = _make_verdict("blocked", reason="Budget exceeded")
        governance = _FakeGovernance(verdict)
        callback = _DefaultGovernanceCallback(governance)
        with pytest.raises(PactError, match="Budget exceeded"):
            asyncio.run(callback("D1-R1", "submit", {}))

    def test_callback_passes_context_to_on_held(self) -> None:
        """The on_held callback should receive the correct arguments."""
        received_args: list[tuple] = []

        async def capture_held(
            verdict: Any, role: str, action: str, context: dict[str, Any]
        ) -> bool:
            received_args.append((verdict, role, action, context))
            return True

        verdict = _make_verdict("held")
        governance = _FakeGovernance(verdict)
        ctx = {"cost": 42.0}
        callback = _DefaultGovernanceCallback(governance, on_held=capture_held)
        asyncio.run(callback("D1-T1-R1", "send_email", ctx))
        assert len(received_args) == 1
        assert received_args[0][0] is verdict
        assert received_args[0][1] == "D1-T1-R1"
        assert received_args[0][2] == "send_email"
        assert received_args[0][3] == ctx


# ---------------------------------------------------------------------------
# PactEngine backward compatibility tests
# ---------------------------------------------------------------------------


class TestPactEngineBackwardCompat:
    """PactEngine without on_held still works (backward compatible)."""

    def test_engine_without_on_held_constructs(
        self, minimal_org_dict: dict[str, Any]
    ) -> None:
        """PactEngine without on_held should construct normally."""
        engine = PactEngine(org=minimal_org_dict)
        assert engine.governance is not None

    def test_engine_with_on_held_constructs(
        self, minimal_org_dict: dict[str, Any]
    ) -> None:
        """PactEngine with on_held callback should construct normally."""

        async def my_held_handler(
            verdict: Any, role: str, action: str, context: dict[str, Any]
        ) -> bool:
            return True

        engine = PactEngine(org=minimal_org_dict, on_held=my_held_handler)
        assert engine.governance is not None

    def test_engine_governance_callback_property(
        self, minimal_org_dict: dict[str, Any]
    ) -> None:
        """PactEngine should expose the governance_callback property."""
        engine = PactEngine(org=minimal_org_dict)
        cb = engine.governance_callback
        assert isinstance(cb, _DefaultGovernanceCallback)

    def test_engine_governance_callback_with_on_held(
        self, minimal_org_dict: dict[str, Any]
    ) -> None:
        """PactEngine governance_callback should use the provided on_held."""

        async def my_handler(
            verdict: Any, role: str, action: str, context: dict[str, Any]
        ) -> bool:
            return True

        engine = PactEngine(org=minimal_org_dict, on_held=my_handler)
        cb = engine.governance_callback
        assert isinstance(cb, _DefaultGovernanceCallback)
        assert cb._on_held is my_handler

    def test_existing_submit_still_works(
        self, minimal_org_dict: dict[str, Any]
    ) -> None:
        """PactEngine.submit_sync should still work without on_held."""
        from pact.work import WorkResult

        engine = PactEngine(org=minimal_org_dict)
        # submit_sync should complete without raising -- the result depends
        # on whether kaizen-agents is installed in this environment
        result = engine.submit_sync("Test task", role="D1-R1")
        assert isinstance(result, WorkResult)

    def test_existing_properties_unchanged(
        self, minimal_org_dict: dict[str, Any]
    ) -> None:
        """All existing properties should still be accessible."""
        engine = PactEngine(
            org=minimal_org_dict,
            model="test-model",
            budget_usd=100.0,
            clearance="confidential",
        )
        assert engine.model == "test-model"
        assert engine.clearance == "confidential"
        assert engine.costs is not None
        assert engine.events is not None
        assert engine.governance is not None
