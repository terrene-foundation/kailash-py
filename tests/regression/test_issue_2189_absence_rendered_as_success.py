"""Regression tests for issue #2189 — an absence rendered as a success.

The class: *a mechanism that learned NOTHING reports the same value as a
mechanism that checked and passed.* Two instances found by the sweep, each
with the property that the vacuous value is produced exactly when the
machinery is misconfigured or the input is hostile:

1. ``MultiDimensionEvaluator.evaluate`` dropped unregistered constraint
   dimensions from the result set entirely. With every dimension unknown,
   ``satisfied`` came back ``True`` — byte-identical, on the field callers
   gate on, to an evaluation that ran and passed.

2. ``_StripeVerifier.verify`` / ``_SlackVerifier.verify`` guarded the
   timestamp parse with ``math.isfinite`` but performed the
   ``datetime.fromtimestamp`` conversion *outside* the guarded block. A
   finite-but-out-of-range value in an attacker-controlled header
   (``t=1e300``) raised ``OverflowError`` past ``handle_webhook``'s
   documented return contract, skipping the rejection metric.

Every test here pairs the probe with a control that must keep its original
answer, so a test cannot pass by making the mechanism uniformly negative.
"""

from datetime import datetime, timezone

import pytest

from kailash.trust.constraints import (
    ConstraintDimensionRegistry,
    InteractionMode,
    MultiDimensionEvaluator,
)
from kailash.trust.constraints.builtin import CostLimitDimension


@pytest.fixture
def evaluator() -> MultiDimensionEvaluator:
    registry = ConstraintDimensionRegistry()
    registry.register(CostLimitDimension())
    return MultiDimensionEvaluator(registry, enable_anti_gaming=False)


class TestUnknownConstraintDimensionFailsClosed:
    """An unevaluated constraint MUST NOT read as a satisfied one."""

    def test_control_registered_dimension_violated_is_unsatisfied(
        self, evaluator: MultiDimensionEvaluator
    ) -> None:
        """Control: the evaluator still says False when a real check fails."""
        result = evaluator.evaluate(
            constraints={"cost_limit": 100},
            context={"cost_used": 999},
            mode=InteractionMode.CONJUNCTIVE,
        )
        assert result.satisfied is False
        assert result.failed_dimensions == ["cost_limit"]

    def test_control_registered_dimension_met_is_satisfied(
        self, evaluator: MultiDimensionEvaluator
    ) -> None:
        """Control: the evaluator still says True when a real check passes.

        Without this the fix could be "return False always" and every other
        test here would pass.
        """
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000},
            context={"cost_used": 10},
            mode=InteractionMode.CONJUNCTIVE,
        )
        assert result.satisfied is True
        assert result.failed_dimensions == []

    def test_all_dimensions_unknown_is_not_satisfied(
        self, evaluator: MultiDimensionEvaluator
    ) -> None:
        """Nothing was evaluated, so nothing may be reported as satisfied."""
        result = evaluator.evaluate(
            constraints={"cost_limitt": 100, "rate_limit": 1},
            context={"cost_used": 10**9},
            mode=InteractionMode.CONJUNCTIVE,
        )
        assert result.satisfied is False
        assert sorted(result.failed_dimensions) == ["cost_limitt", "rate_limit"]

    def test_unknown_dimension_appears_in_results_not_only_warnings(
        self, evaluator: MultiDimensionEvaluator
    ) -> None:
        """The truth must reach the field callers read, not just ``warnings``.

        A warning that no gate consults is a deletion with provenance.
        """
        result = evaluator.evaluate(
            constraints={"nonexistent_dim": 42},
            context={},
            mode=InteractionMode.CONJUNCTIVE,
        )
        assert any("Unknown dimension" in w for w in result.warnings)
        assert "nonexistent_dim" in result.dimension_results
        assert result.dimension_results["nonexistent_dim"].satisfied is False
        assert "not" in result.dimension_results["nonexistent_dim"].reason.lower()

    def test_conjunctive_all_must_pass_counts_the_unknown_dimension(
        self, evaluator: MultiDimensionEvaluator
    ) -> None:
        """ "ALL must pass" may not be computed over a silently shrunk set."""
        result = evaluator.evaluate(
            constraints={"cost_limit": 1000, "data_residency": "EU"},
            context={"cost_used": 10},
            mode=InteractionMode.CONJUNCTIVE,
        )
        assert result.satisfied is False
        assert result.failed_dimensions == ["data_residency"]

    def test_control_empty_constraint_set_is_still_satisfied(
        self, evaluator: MultiDimensionEvaluator
    ) -> None:
        """Control: asking for nothing is unchanged — that is not the defect."""
        assert evaluator.evaluate(constraints={}, context={}).satisfied is True


class TestWebhookTimestampGuardCoversTheConversion:
    """A hostile timestamp header must be REJECTED, never raise."""

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def test_stripe_out_of_range_timestamp_is_rejected_not_raised(self) -> None:
        webhooks = pytest.importorskip("dataflow.fabric.webhooks")
        result = webhooks._StripeVerifier().verify(
            headers={"stripe-signature": "t=1e300,v1=deadbeef"},
            body=b"{}",
            secret="s",
            now=self._now(),
        )
        assert result.accepted is False

    def test_slack_out_of_range_timestamp_is_rejected_not_raised(self) -> None:
        webhooks = pytest.importorskip("dataflow.fabric.webhooks")
        result = webhooks._SlackVerifier().verify(
            headers={
                "x-slack-signature": "v0=deadbeef",
                "x-slack-request-timestamp": "1e300",
            },
            body=b"{}",
            secret="s",
            now=self._now(),
        )
        assert result.accepted is False

    def test_control_ordinary_stale_timestamp_keeps_its_own_reason(self) -> None:
        """Control: the tolerance window still reports staleness as staleness.

        Without this the fix could be "reject every timestamp" and the two
        probes above would pass.
        """
        webhooks = pytest.importorskip("dataflow.fabric.webhooks")
        result = webhooks._StripeVerifier().verify(
            headers={"stripe-signature": "t=1,v1=deadbeef"},
            body=b"{}",
            secret="s",
            now=self._now(),
        )
        assert result.accepted is False
        assert "too old" in result.reason
