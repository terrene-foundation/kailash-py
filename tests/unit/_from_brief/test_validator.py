# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for the plan validator.

The validator composes three independent gates (structural, confidence,
allowlist). Each test below exercises ONE gate's failure mode with the
others' inputs held clean, so a failure cleanly identifies which gate
fired.

Per ``rules/testing.md`` § "Behavioral Regression Tests Over
Source-Grep", every assertion calls the function and inspects the
typed exception's discriminators — no string-matching on messages.
"""

from __future__ import annotations

from typing import List, Optional

import pytest
from pydantic import Field

from kailash._from_brief import (
    BriefInterpretationError,
    BriefPlan,
    coerce_plan,
    validate_plan,
)


class WorkflowLikePlan(BriefPlan):
    """A test-only plan subclass mimicking a workflow shape."""

    node_types: List[str] = Field(default_factory=list)
    field_types: List[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)
    node_type: Optional[str] = None


class TestConfidenceGate:
    def test_below_threshold_raises_low_confidence(self):
        plan = WorkflowLikePlan(interpretation_confidence=0.3)
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_plan(plan)
        assert excinfo.value.low_confidence is True
        assert excinfo.value.unknown_value is None
        assert excinfo.value.malformed is False

    def test_at_threshold_passes(self):
        plan = WorkflowLikePlan(interpretation_confidence=0.6)
        # No exception — gate passes.
        validate_plan(plan)

    def test_above_threshold_passes(self):
        plan = WorkflowLikePlan(interpretation_confidence=0.95)
        validate_plan(plan)

    def test_custom_threshold_respected(self):
        plan = WorkflowLikePlan(interpretation_confidence=0.7)
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_plan(plan, confidence_threshold=0.8)
        assert excinfo.value.low_confidence is True

    def test_negative_confidence_raises_malformed(self):
        plan = WorkflowLikePlan(interpretation_confidence=-0.1)
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_plan(plan)
        assert excinfo.value.malformed is True

    def test_above_one_confidence_raises_malformed(self):
        plan = WorkflowLikePlan(interpretation_confidence=1.5)
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_plan(plan)
        assert excinfo.value.malformed is True


class TestAllowlistGate:
    def test_unknown_node_type_raises_with_name(self):
        plan = WorkflowLikePlan(
            interpretation_confidence=0.9,
            node_types=["CSVReaderNode", "MystryNode"],
        )
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_plan(
                plan,
                allowed_node_types={"CSVReaderNode", "WriterNode"},
            )
        assert excinfo.value.unknown_value == "MystryNode"
        assert excinfo.value.low_confidence is False
        assert excinfo.value.malformed is False

    def test_known_node_type_passes(self):
        plan = WorkflowLikePlan(
            interpretation_confidence=0.9,
            node_types=["CSVReaderNode", "WriterNode"],
        )
        validate_plan(
            plan,
            allowed_node_types={"CSVReaderNode", "WriterNode"},
        )

    def test_single_node_type_attribute_validated(self):
        plan = WorkflowLikePlan(
            interpretation_confidence=0.9,
            node_type="UnknownAgent",
        )
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_plan(plan, allowed_node_types={"KnownAgent"})
        assert excinfo.value.unknown_value == "UnknownAgent"

    def test_unknown_field_type_raises_with_name(self):
        plan = WorkflowLikePlan(
            interpretation_confidence=0.9,
            field_types=["str", "exotic_pointer"],
        )
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_plan(
                plan,
                allowed_field_types={"str", "int", "float"},
            )
        assert excinfo.value.unknown_value == "exotic_pointer"

    def test_config_value_unknown_raises(self):
        plan = WorkflowLikePlan(
            interpretation_confidence=0.9,
            config={"mode": "json", "format": "exotic"},
        )
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_plan(
                plan,
                allowed_config_values={
                    "mode": {"json", "yaml"},
                    "format": {"csv", "parquet"},
                },
            )
        assert excinfo.value.unknown_value == "exotic"

    def test_config_field_unknown_raises(self):
        plan = WorkflowLikePlan(
            interpretation_confidence=0.9,
            config={"unknown_field": "anything"},
        )
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_plan(
                plan,
                allowed_config_values={"mode": {"json", "yaml"}},
            )
        assert excinfo.value.unknown_value == "unknown_field"


class TestMalformedGate:
    def test_extra_field_rejected_by_pydantic(self):
        # extra="forbid" on the base model means an LLM hallucinating a
        # stray field raises ValidationError at construction.
        with pytest.raises(Exception):
            WorkflowLikePlan(
                interpretation_confidence=0.9,
                hallucinated_field="oops",
            )

    def test_coerce_plan_wraps_validation_error(self):
        raw = {
            "interpretation_confidence": "not_a_float",
            "node_types": [],
        }
        with pytest.raises(BriefInterpretationError) as excinfo:
            coerce_plan(raw, WorkflowLikePlan)
        assert excinfo.value.malformed is True
        # The cause is preserved for forensic traceback.
        assert excinfo.value.__cause__ is not None

    def test_coerce_plan_success_returns_model_instance(self):
        raw = {
            "interpretation_confidence": 0.9,
            "node_types": ["a", "b"],
        }
        plan = coerce_plan(raw, WorkflowLikePlan)
        assert isinstance(plan, WorkflowLikePlan)
        assert plan.node_types == ["a", "b"]


class TestNoGatesProvided:
    """When no allowlist is provided, only the confidence gate runs."""

    def test_clean_plan_passes_with_no_allowlists(self):
        plan = WorkflowLikePlan(
            interpretation_confidence=0.9,
            node_types=["LiterallyAnything"],
            field_types=["arbitrary_type"],
            config={"unknown_field": "unknown_value"},
        )
        # No allowlists → allowlist gate is opt-in → no raise.
        validate_plan(plan)
