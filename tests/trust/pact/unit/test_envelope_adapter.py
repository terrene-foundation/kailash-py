# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for GovernanceEnvelopeAdapter -- converts governance envelopes to
trust-layer ConstraintEnvelope for backward compatibility.

Covers:
- Valid conversion from governance effective envelope to ConstraintEnvelope
- Field mapping correctness (governance config -> trust-layer dimensions)
- No envelope raises EnvelopeAdapterError (fail-closed)
- Conversion failure raises EnvelopeAdapterError (not silent fallback)
- NaN/Inf guard during conversion
- Task envelope narrows effective envelope through adapter
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from pact.examples.university.org import create_university_org
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelope_adapter import (
    EnvelopeAdapterError,
    GovernanceEnvelopeAdapter,
)
from kailash.trust.pact.envelopes import RoleEnvelope, TaskEnvelope
from kailash.trust.plane.models import ConstraintEnvelope


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def compiled_org() -> CompiledOrg:
    """Compiled university org for adapter tests."""
    compiled, _ = create_university_org()
    return compiled


@pytest.fixture
def engine(compiled_org: CompiledOrg) -> GovernanceEngine:
    """GovernanceEngine with a role envelope set for CS Chair."""
    eng = GovernanceEngine(compiled_org)

    envelope_config = ConstraintEnvelopeConfig(
        id="env-cs-chair",
        description="CS Chair envelope",
        financial=FinancialConstraintConfig(
            max_spend_usd=1000.0,
            requires_approval_above_usd=500.0,
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=["read", "write", "grade", "teach"],
            blocked_actions=["delete"],
        ),
    )
    role_env = RoleEnvelope(
        id="re-cs-chair",
        defining_role_address="D1-R1-D1-R1-D1-R1",
        target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
        envelope=envelope_config,
    )
    eng.set_role_envelope(role_env)
    return eng


@pytest.fixture
def adapter(engine: GovernanceEngine) -> GovernanceEnvelopeAdapter:
    """Adapter wrapping the engine."""
    return GovernanceEnvelopeAdapter(engine)


# ---------------------------------------------------------------------------
# Test: Valid Conversion
# ---------------------------------------------------------------------------


class TestToConstraintEnvelope:
    """Converting governance envelope to trust-layer ConstraintEnvelope."""

    def test_to_constraint_envelope_valid(
        self, adapter: GovernanceEnvelopeAdapter
    ) -> None:
        """Adapter should produce a trust-layer ConstraintEnvelope from a valid governance envelope."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        assert isinstance(result, ConstraintEnvelope)
        # Trust-layer envelope has direct dimension fields
        assert result.signed_by == "governance:env-cs-chair"

    def test_financial_mapping(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """Financial constraints should be mapped from governance config."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        # max_spend_usd maps to max_cost_per_session
        assert result.financial.max_cost_per_session == 1000.0
        # requires_approval_above_usd maps to max_cost_per_action
        assert result.financial.max_cost_per_action == 500.0
        assert result.financial.budget_tracking is True

    def test_operational_mapping(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """Operational constraints should be mapped from governance config."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        assert "read" in result.operational.allowed_actions
        assert "write" in result.operational.allowed_actions
        assert "delete" in result.operational.blocked_actions


# ---------------------------------------------------------------------------
# Test: No Envelope (Fail-Closed)
# ---------------------------------------------------------------------------


class TestNoEnvelope:
    """When no envelope is found, adapter must fail-closed."""

    def test_no_envelope_raises_adapter_error(
        self, adapter: GovernanceEnvelopeAdapter
    ) -> None:
        """If the engine returns None for a role, adapter MUST raise EnvelopeAdapterError."""
        with pytest.raises(EnvelopeAdapterError, match="No effective envelope"):
            adapter.to_constraint_envelope("D1-R1-D2-R1-T1-R1")


# ---------------------------------------------------------------------------
# Test: Conversion Failure
# ---------------------------------------------------------------------------


class TestConversionFailure:
    """Conversion errors must raise EnvelopeAdapterError, never silent fallback."""

    def test_conversion_failure_raises_adapter_error(
        self, compiled_org: CompiledOrg
    ) -> None:
        """If the engine throws during compute_envelope, adapter wraps in EnvelopeAdapterError."""
        engine = GovernanceEngine(compiled_org)

        def broken_compute(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Simulated engine failure")

        engine.compute_envelope = broken_compute  # type: ignore[assignment]

        adapter = GovernanceEnvelopeAdapter(engine)
        with pytest.raises(EnvelopeAdapterError, match="Envelope conversion failed"):
            adapter.to_constraint_envelope("D1-R1")


# ---------------------------------------------------------------------------
# Test: NaN/Inf Guard
# ---------------------------------------------------------------------------


class TestNanInfGuard:
    """NaN and Inf values must be rejected during conversion."""

    def test_nan_inf_guard_during_conversion(self, compiled_org: CompiledOrg) -> None:
        """If a governance envelope has NaN/Inf, adapter MUST raise EnvelopeAdapterError."""
        engine = GovernanceEngine(compiled_org)

        def nan_compute(*args: Any, **kwargs: Any) -> ConstraintEnvelopeConfig:
            raise ValueError("max_spend_usd must be finite, got nan")

        engine.compute_envelope = nan_compute  # type: ignore[assignment]

        adapter = GovernanceEnvelopeAdapter(engine)
        with pytest.raises(EnvelopeAdapterError, match="Envelope conversion failed"):
            adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")

    def test_adapter_validates_numeric_fields(self, compiled_org: CompiledOrg) -> None:
        """Adapter's own NaN/Inf guard catches values that bypass schema validation."""
        engine = GovernanceEngine(compiled_org)

        envelope_config = ConstraintEnvelopeConfig(
            id="env-test-nan",
            description="Test NaN guard",
            financial=FinancialConstraintConfig(max_spend_usd=100.0),
            operational=OperationalConstraintConfig(allowed_actions=["read"]),
        )
        role_env = RoleEnvelope(
            id="re-test-nan",
            defining_role_address="D1-R1-D1-R1-D1-R1",
            target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            envelope=envelope_config,
        )
        engine.set_role_envelope(role_env)

        original = engine.compute_envelope

        def patched_compute(
            role_address: str, task_id: str | None = None
        ) -> ConstraintEnvelopeConfig:
            config = original(role_address, task_id=task_id)
            if config is None:
                return config
            fin = config.financial
            if fin is not None:
                object.__setattr__(fin, "max_spend_usd", float("nan"))
            return config

        engine.compute_envelope = patched_compute  # type: ignore[assignment]

        adapter = GovernanceEnvelopeAdapter(engine)
        with pytest.raises(EnvelopeAdapterError, match="non-finite"):
            adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")


# ---------------------------------------------------------------------------
# Test: Task Envelope Narrows Through Adapter
# ---------------------------------------------------------------------------


class TestWithTaskEnvelope:
    """Task envelope should narrow the effective envelope through the adapter."""

    def test_with_task_envelope(self, engine: GovernanceEngine) -> None:
        """Setting a task envelope narrows the effective, and the adapter reflects this."""
        task_config = ConstraintEnvelopeConfig(
            id="env-task-grading",
            description="Grading task envelope",
            financial=FinancialConstraintConfig(max_spend_usd=200.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "grade"],
            ),
        )
        task_env = TaskEnvelope(
            id="te-grading",
            task_id="task-grading-2026",
            parent_envelope_id="re-cs-chair",
            envelope=task_config,
            expires_at=datetime.now(UTC) + timedelta(hours=4),
        )
        engine.set_task_envelope(task_env)

        adapter = GovernanceEnvelopeAdapter(engine)
        trust_envelope = adapter.to_constraint_envelope(
            "D1-R1-D1-R1-D1-R1-T1-R1", task_id="task-grading-2026"
        )
        assert isinstance(trust_envelope, ConstraintEnvelope)

        # Financial narrowed to 200.0 (min of 1000, 200)
        assert trust_envelope.financial.max_cost_per_session == 200.0

        # Operational narrowed to intersection
        assert "read" in trust_envelope.operational.allowed_actions
        assert "grade" in trust_envelope.operational.allowed_actions
