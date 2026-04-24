# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 tests for the public :func:`apply_read_classification` helper.

Cross-SDK parity: these tests mirror the masking matrix that
kailash-rs PR #580 exercises for its PyO3-exposed
``apply_read_classification`` entry.
"""

from __future__ import annotations

import pytest

from dataflow.classification import (
    ClassificationPolicy,
    DataClassification,
    FieldClassification,
    MaskingStrategy,
    RetentionPolicy,
    apply_read_classification,
    format_record_id_for_event,
)


def _fields(**kwargs: FieldClassification) -> dict[str, FieldClassification]:
    return kwargs


class TestApplyReadClassificationPublicExport:
    def test_importable_from_classification_module(self) -> None:
        """apply_read_classification is the documented public entry."""
        from dataflow.classification import apply_read_classification as exported

        assert exported is apply_read_classification

    def test_format_record_id_also_exported(self) -> None:
        """format_record_id_for_event is exported from the same surface."""
        from dataflow.classification import format_record_id_for_event as exported

        assert exported is format_record_id_for_event

    def test_listed_in_all(self) -> None:
        """Both helpers appear in __all__ per orphan-detection.md §6."""
        import dataflow.classification as mod

        assert "apply_read_classification" in mod.__all__
        assert "format_record_id_for_event" in mod.__all__


class TestMaskingMatrix:
    def test_public_caller_cannot_see_pii(self) -> None:
        fields = _fields(
            ssn=FieldClassification(
                DataClassification.PII,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.REDACT,
            )
        )
        record = {"name": "Alice", "ssn": "123-45-6789"}
        result = apply_read_classification(fields, record, DataClassification.PUBLIC)
        assert result["ssn"] == "[REDACTED]"
        assert result["name"] == "Alice"

    def test_pii_caller_sees_pii(self) -> None:
        fields = _fields(
            ssn=FieldClassification(
                DataClassification.PII,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.REDACT,
            )
        )
        record = {"ssn": "123-45-6789"}
        result = apply_read_classification(fields, record, DataClassification.PII)
        assert result["ssn"] == "123-45-6789"

    def test_gdpr_caller_cannot_see_highly_confidential(self) -> None:
        fields = _fields(
            secret=FieldClassification(
                DataClassification.HIGHLY_CONFIDENTIAL,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.REDACT,
            )
        )
        result = apply_read_classification(
            _fields(**fields),
            {"secret": "topsecret"},
            DataClassification.GDPR,
        )
        assert result["secret"] == "[REDACTED]"

    def test_highly_confidential_caller_sees_all(self) -> None:
        fields = _fields(
            secret=FieldClassification(
                DataClassification.HIGHLY_CONFIDENTIAL,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.REDACT,
            )
        )
        result = apply_read_classification(
            fields,
            {"secret": "topsecret"},
            DataClassification.HIGHLY_CONFIDENTIAL,
        )
        assert result["secret"] == "topsecret"

    def test_none_masking_defaults_to_redact_when_below_clearance(
        self,
    ) -> None:
        """MaskingStrategy.NONE should still mask when caller lacks clearance."""
        fields = _fields(
            email=FieldClassification(
                DataClassification.PII,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.NONE,  # will default to REDACT
            )
        )
        result = apply_read_classification(
            fields,
            {"email": "a@b.com"},
            DataClassification.PUBLIC,
        )
        assert result["email"] == "[REDACTED]"

    def test_hash_strategy(self) -> None:
        fields = _fields(
            token=FieldClassification(
                DataClassification.SENSITIVE,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.HASH,
            )
        )
        result = apply_read_classification(
            fields,
            {"token": "abc123"},
            DataClassification.PUBLIC,
        )
        assert result["token"] != "abc123"
        assert len(result["token"]) == 64  # sha256 hex

    def test_last_four_strategy(self) -> None:
        fields = _fields(
            card=FieldClassification(
                DataClassification.PII,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.LAST_FOUR,
            )
        )
        result = apply_read_classification(
            fields,
            {"card": "4111111111111234"},
            DataClassification.PUBLIC,
        )
        assert result["card"] == "************1234"

    def test_encrypt_sentinel(self) -> None:
        fields = _fields(
            body=FieldClassification(
                DataClassification.HIGHLY_CONFIDENTIAL,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.ENCRYPT,
            )
        )
        result = apply_read_classification(
            fields,
            {"body": "secret content"},
            DataClassification.PUBLIC,
        )
        assert result["body"] == "[ENCRYPTED]"

    def test_none_clearance_treated_as_public(self) -> None:
        fields = _fields(
            ssn=FieldClassification(
                DataClassification.PII,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.REDACT,
            )
        )
        result = apply_read_classification(
            fields, {"ssn": "123"}, caller_clearance=None
        )
        assert result["ssn"] == "[REDACTED]"


class TestNonDictPassthrough:
    def test_non_dict_record_returned_unchanged(self) -> None:
        fields = _fields(
            x=FieldClassification(
                DataClassification.PII,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.REDACT,
            )
        )
        assert (
            apply_read_classification(fields, None, DataClassification.PUBLIC) is None
        )
        assert (
            apply_read_classification(fields, "not a dict", DataClassification.PUBLIC)
            == "not a dict"
        )
        assert apply_read_classification(fields, 42, DataClassification.PUBLIC) == 42

    def test_empty_fields_returned_unchanged(self) -> None:
        record = {"a": 1, "b": 2}
        result = apply_read_classification({}, record, DataClassification.PUBLIC)
        assert result == {"a": 1, "b": 2}
        # Same reference when fields empty — mutation-in-place contract
        assert result is record

    def test_field_absent_from_record_is_skipped(self) -> None:
        fields = _fields(
            missing=FieldClassification(
                DataClassification.PII,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.REDACT,
            )
        )
        record = {"present": "value"}
        result = apply_read_classification(fields, record, DataClassification.PUBLIC)
        assert result == {"present": "value"}


class TestMutationContract:
    def test_mutates_record_in_place(self) -> None:
        """Record is mutated in place AND returned (for chaining)."""
        fields = _fields(
            ssn=FieldClassification(
                DataClassification.PII,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.REDACT,
            )
        )
        record = {"ssn": "123-45-6789"}
        result = apply_read_classification(fields, record, DataClassification.PUBLIC)
        assert result is record
        assert record["ssn"] == "[REDACTED]"


class TestAmbientClearance:
    def test_ambient_clearance_picked_up_when_caller_clearance_is_none(
        self,
    ) -> None:
        """When caller_clearance=None, get_current_clearance() is consulted."""
        from dataflow.core.agent_context import clearance_context

        fields = _fields(
            ssn=FieldClassification(
                DataClassification.PII,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.REDACT,
            )
        )
        with clearance_context(DataClassification.PII):
            result = apply_read_classification(fields, {"ssn": "123"})
            assert result["ssn"] == "123"  # PII caller sees PII

        with clearance_context(DataClassification.PUBLIC):
            result = apply_read_classification(fields, {"ssn": "456"})
            assert result["ssn"] == "[REDACTED]"


class TestCrossSDKParity:
    def test_apply_read_classification_and_format_record_id_share_module(
        self,
    ) -> None:
        """
        Structural invariant: both helpers MUST be importable from the
        same `dataflow.classification` module — matches kailash-rs PR #580
        which exposes both from `kailash.dataflow` on the Rust binding side.
        """
        import dataflow.classification as mod

        assert hasattr(mod, "apply_read_classification")
        assert hasattr(mod, "format_record_id_for_event")

    def test_parity_with_classification_policy_apply_masking_to_record(
        self,
    ) -> None:
        """
        The public helper MUST produce the same output as
        `ClassificationPolicy.apply_masking_to_record` — the private path
        already wired into DataFlowExpress mutation returns.
        """
        policy = ClassificationPolicy()
        policy.set_field(
            "User",
            "ssn",
            DataClassification.PII,
            RetentionPolicy.INDEFINITE,
            MaskingStrategy.REDACT,
        )
        fields = policy.get_model_fields("User")
        record_via_helper = apply_read_classification(
            fields, {"ssn": "123-45-6789"}, DataClassification.PUBLIC
        )
        record_via_policy = policy.apply_masking_to_record(
            "User", {"ssn": "123-45-6789"}, DataClassification.PUBLIC
        )
        assert record_via_helper == record_via_policy
