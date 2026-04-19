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
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.config import (
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    GradientRuleConfig,
    OperationalConstraintConfig,
    VerificationGradientConfig,
    VerificationLevel,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.gradient import GradientEngine
from kailash.trust.plane.models import ConstraintEnvelope
from pact.examples.university.org import create_university_org

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


# Removed TestGradientEngineDeprecation and
# TestConstraintEnvelopeDeprecation — both test classes were skipped
# with reasons indicating the underlying deprecation bridges they
# tested had been removed in the monorepo integration. A skipped test
# of a removed API is a stub (zero-tolerance.md Rule 2) AND a
# test-orphan (orphan-detection.md Rule 4). The current deprecation
# surface, if any, needs new tests targeting today's actual behavior
# rather than a bridge that no longer exists.
