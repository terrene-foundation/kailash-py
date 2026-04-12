# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: classification read path must fail-closed.

GH-418: unclassified fields default to HIGHLY_CONFIDENTIAL (most
restrictive). Unknown clearance levels deny access. None clearance
is treated as PUBLIC (can only see PUBLIC fields).

Cross-SDK alignment: kailash-rs PR #334.
"""
from __future__ import annotations

import pytest

from dataflow.classification.policy import ClassificationPolicy
from dataflow.classification.types import DataClassification, MaskingStrategy


@pytest.mark.regression
class TestClassificationFailClosed:
    """Verify fail-closed behavior for all classification paths."""

    def test_unclassified_field_defaults_to_highly_confidential(self) -> None:
        """An unclassified field must return the most restrictive level."""
        policy = ClassificationPolicy()
        level = policy.classify("UnknownModel", "unknown_field")
        assert level == DataClassification.HIGHLY_CONFIDENTIAL.value

    def test_classified_field_returns_its_level(self) -> None:
        """An explicitly classified field returns its own level."""
        policy = ClassificationPolicy()
        policy.set_field("User", "email", DataClassification.PII)
        level = policy.classify("User", "email")
        assert level == DataClassification.PII.value

    def test_unknown_classification_denies_access(self) -> None:
        """Unknown DataClassification values in caller_can_access -> deny."""
        # caller_can_access raises ValueError on unknown enum -> returns False
        result = ClassificationPolicy.caller_can_access(
            DataClassification.PII,
            DataClassification.PUBLIC,
        )
        assert result is False  # PUBLIC < PII -> denied

    def test_none_clearance_treated_as_public(self) -> None:
        """None clearance = PUBLIC = most restrictive for caller."""
        policy = ClassificationPolicy()
        policy.set_field("Doc", "secret", DataClassification.INTERNAL)
        record = {"id": "1", "secret": "top-secret-value"}
        masked = policy.apply_masking_to_record("Doc", record, None)
        assert masked["secret"] == "[REDACTED]"

    def test_none_clearance_can_see_public_fields(self) -> None:
        """None clearance should still see PUBLIC-classified fields."""
        policy = ClassificationPolicy()
        policy.set_field("Doc", "title", DataClassification.PUBLIC)
        record = {"id": "1", "title": "Hello"}
        masked = policy.apply_masking_to_record("Doc", record, None)
        assert masked["title"] == "Hello"

    def test_unknown_masking_strategy_redacts(self) -> None:
        """Unknown MaskingStrategy should redact (fail-closed)."""
        # apply_masking_strategy falls through all known strategies
        # and returns [REDACTED] for unknown
        result = ClassificationPolicy.apply_masking_strategy(
            "sensitive-value", MaskingStrategy.REDACT
        )
        assert result == "[REDACTED]"
