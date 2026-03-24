# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for deprecation warnings on legacy paths.

TODO 7023: Deprecation markers for:
1. GradientEngine constructed without governance_engine -> DeprecationWarning
2. GradientEngine constructed with governance_engine -> no warning
3. ConstraintEnvelope.evaluate_action() called directly -> DeprecationWarning
"""

from __future__ import annotations

import warnings
from datetime import UTC, datetime, timedelta

import pytest

from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    GradientRuleConfig,
    OperationalConstraintConfig,
    VerificationGradientConfig,
    VerificationLevel,
)
from pact.examples.university.org import create_university_org
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.gradient import GradientEngine
from kailash.trust.plane.models import ConstraintEnvelope


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gradient_config() -> VerificationGradientConfig:
    """A simple gradient config for testing."""
    return VerificationGradientConfig(
        rules=[
            GradientRuleConfig(
                pattern="delete*",
                level=VerificationLevel.BLOCKED,
                reason="Delete actions are blocked",
            ),
            GradientRuleConfig(
                pattern="deploy*",
                level=VerificationLevel.HELD,
                reason="Deploy actions require approval",
            ),
        ],
        default_level=VerificationLevel.AUTO_APPROVED,
    )


@pytest.fixture
def compiled_org() -> CompiledOrg:
    """Compiled university org."""
    compiled, _ = create_university_org()
    return compiled


@pytest.fixture
def governance_engine(compiled_org: CompiledOrg) -> GovernanceEngine:
    """A configured GovernanceEngine."""
    engine = GovernanceEngine(compiled_org)
    envelope_config = ConstraintEnvelopeConfig(
        id="env-test",
        description="Test envelope",
        financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write"],
        ),
    )
    role_env = RoleEnvelope(
        id="re-test",
        defining_role_address="D1-R1",
        target_role_address="D1-R1",
        envelope=envelope_config,
    )
    engine.set_role_envelope(role_env)
    return engine


# ---------------------------------------------------------------------------
# Test: GradientEngine Deprecation Warnings
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="GradientEngine API changed in monorepo integration — old deprecation bridge removed"
)
class TestGradientEngineDeprecation:
    """GradientEngine should warn when constructed without governance_engine."""

    def test_gradient_engine_without_governance_warns(
        self, gradient_config: VerificationGradientConfig
    ) -> None:
        """Constructing GradientEngine without governance_engine emits DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            engine = GradientEngine(gradient_config)
            # Filter for our specific deprecation warning
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1
            assert "governance_engine" in str(deprecation_warnings[0].message).lower()

    def test_gradient_engine_with_governance_no_warning(
        self,
        gradient_config: VerificationGradientConfig,
        governance_engine: GovernanceEngine,
    ) -> None:
        """Constructing GradientEngine with governance_engine emits NO DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            engine = GradientEngine(
                gradient_config, governance_engine=governance_engine
            )
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) == 0


# ---------------------------------------------------------------------------
# Test: ConstraintEnvelope.evaluate_action() Deprecation
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="ConstraintEnvelope API changed — kailash.trust.plane.models.ConstraintEnvelope has different constructor"
)
class TestConstraintEnvelopeDeprecation:
    """ConstraintEnvelope.evaluate_action() should emit DeprecationWarning."""

    def test_constraint_envelope_evaluate_warns(self) -> None:
        """Calling ConstraintEnvelope.evaluate_action() directly emits DeprecationWarning."""
        config = ConstraintEnvelopeConfig(
            id="env-legacy-test",
            description="Legacy test envelope",
            financial=FinancialConstraintConfig(max_spend_usd=1000.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write"],
            ),
        )
        envelope = ConstraintEnvelope(config=config)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = envelope.evaluate_action(
                action="read",
                agent_id="agent-001",
            )
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1
            msg = str(deprecation_warnings[0].message).lower()
            assert "governanceengine" in msg or "governance" in msg

        # The evaluation itself should still work correctly
        assert result.is_allowed is True
