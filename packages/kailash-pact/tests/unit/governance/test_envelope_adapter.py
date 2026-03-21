# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for GovernanceEnvelopeAdapter -- converts governance envelopes to
trust-layer ConstraintEnvelope for backward compatibility.

Written TDD-first: tests define expected behavior before implementation.

Covers:
- Valid conversion from governance effective envelope to ConstraintEnvelope
- Round-trip evaluation (governance -> adapter -> evaluate -> consistent result)
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

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from pact.examples.university.org import create_university_org
from pact.governance.compilation import CompiledOrg
from pact.governance.engine import GovernanceEngine
from pact.governance.envelope_adapter import (
    EnvelopeAdapterError,
    GovernanceEnvelopeAdapter,
)
from pact.governance.envelopes import RoleEnvelope, TaskEnvelope
from pact.trust.constraint.envelope import ConstraintEnvelope


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

    def test_to_constraint_envelope_valid(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """Adapter should produce a ConstraintEnvelope from a valid governance envelope."""
        result = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")
        assert isinstance(result, ConstraintEnvelope)
        assert result.config.id == "env-cs-chair"
        assert result.config.financial is not None
        assert result.config.financial.max_spend_usd == 1000.0
        assert result.config.operational.allowed_actions == [
            "read",
            "write",
            "grade",
            "teach",
        ]

    def test_round_trip_evaluation(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """Governance -> adapter -> evaluate should produce a consistent evaluation.

        The trust-layer ConstraintEnvelope's evaluate_action() should respect
        the governance envelope's constraints: "read" is allowed, "delete" is blocked.
        """
        trust_envelope = adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")

        # "read" is in allowed_actions -> should be ALLOWED
        eval_read = trust_envelope.evaluate_action(
            action="read",
            agent_id="agent-001",
            spend_amount=10.0,
        )
        assert eval_read.is_allowed is True

        # "delete" is in blocked_actions -> should be DENIED
        eval_delete = trust_envelope.evaluate_action(
            action="delete",
            agent_id="agent-001",
        )
        assert eval_delete.overall_result.value == "denied"

        # Spend exceeding limit -> should be DENIED
        eval_overspend = trust_envelope.evaluate_action(
            action="read",
            agent_id="agent-001",
            spend_amount=2000.0,
        )
        assert eval_overspend.overall_result.value == "denied"


# ---------------------------------------------------------------------------
# Test: No Envelope (Fail-Closed)
# ---------------------------------------------------------------------------


class TestNoEnvelope:
    """When no envelope is found, adapter must fail-closed."""

    def test_no_envelope_raises_adapter_error(self, adapter: GovernanceEnvelopeAdapter) -> None:
        """If the engine returns None for a role, adapter MUST raise EnvelopeAdapterError."""
        # Use a role address with no envelope set
        with pytest.raises(EnvelopeAdapterError, match="No effective envelope"):
            adapter.to_constraint_envelope("D1-R1-D2-R1-T1-R1")


# ---------------------------------------------------------------------------
# Test: Conversion Failure
# ---------------------------------------------------------------------------


class TestConversionFailure:
    """Conversion errors must raise EnvelopeAdapterError, never silent fallback."""

    def test_conversion_failure_raises_adapter_error(self, compiled_org: CompiledOrg) -> None:
        """If the engine throws during compute_envelope, adapter wraps in EnvelopeAdapterError."""
        engine = GovernanceEngine(compiled_org)

        # Monkey-patch compute_envelope to simulate failure
        original = engine.compute_envelope

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
        """If a governance envelope has NaN/Inf in financial fields, adapter
        MUST raise EnvelopeAdapterError (via pydantic validation or explicit guard).

        Note: The schema validators on ConstraintEnvelopeConfig reject NaN/Inf
        at construction time. This test verifies the adapter propagates that
        failure as EnvelopeAdapterError.
        """
        engine = GovernanceEngine(compiled_org)

        # Monkey-patch to return an envelope with NaN in a numeric field.
        # Since ConstraintEnvelopeConfig has validators that reject NaN,
        # we simulate the adapter receiving a broken config from the engine.
        original = engine.compute_envelope

        def nan_compute(*args: Any, **kwargs: Any) -> ConstraintEnvelopeConfig:
            # Bypassing pydantic validation to inject NaN
            raise ValueError("max_spend_usd must be finite, got nan")

        engine.compute_envelope = nan_compute  # type: ignore[assignment]

        adapter = GovernanceEnvelopeAdapter(engine)
        with pytest.raises(EnvelopeAdapterError, match="Envelope conversion failed"):
            adapter.to_constraint_envelope("D1-R1-D1-R1-D1-R1-T1-R1")

    def test_adapter_validates_numeric_fields(self, compiled_org: CompiledOrg) -> None:
        """Adapter's own NaN/Inf guard catches values that somehow bypass schema validation."""
        engine = GovernanceEngine(compiled_org)

        # Create a valid envelope via the engine
        envelope_config = ConstraintEnvelopeConfig(
            id="env-test-nan",
            description="Test NaN guard",
            financial=FinancialConstraintConfig(max_spend_usd=100.0),
            operational=OperationalConstraintConfig(
                allowed_actions=["read"],
            ),
        )
        role_env = RoleEnvelope(
            id="re-test-nan",
            defining_role_address="D1-R1-D1-R1-D1-R1",
            target_role_address="D1-R1-D1-R1-D1-R1-T1-R1",
            envelope=envelope_config,
        )
        engine.set_role_envelope(role_env)

        # Monkey-patch engine to return a config with NaN smuggled in
        def patched_compute(
            role_address: str, task_id: str | None = None
        ) -> ConstraintEnvelopeConfig:
            config = original(role_address, task_id=task_id)
            if config is None:
                return config
            # Use object.__setattr__ to bypass frozen model
            fin = config.financial
            if fin is not None:
                object.__setattr__(fin, "max_spend_usd", float("nan"))
            return config

        original = engine.compute_envelope
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
        """Setting a task envelope should narrow the effective via intersection,
        and the adapter should produce a ConstraintEnvelope reflecting the narrowed constraints.
        """
        # Add a task envelope that narrows the CS Chair's envelope
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
        assert trust_envelope.config.financial is not None
        assert trust_envelope.config.financial.max_spend_usd == 200.0

        # Operational narrowed to intersection: {"read", "grade"}
        assert set(trust_envelope.config.operational.allowed_actions) == {
            "read",
            "grade",
        }

        # "write" is no longer allowed after narrowing
        eval_write = trust_envelope.evaluate_action(
            action="write",
            agent_id="agent-001",
        )
        assert eval_write.overall_result.value == "denied"
