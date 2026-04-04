"""Unit tests for Provenance[T] field-level source tracking (issue #242)."""

import math
from datetime import datetime, UTC, timezone

import pytest

from dataflow.core.provenance import Provenance, ProvenanceMetadata, SourceType


# ---------------------------------------------------------------------------
# SourceType enum
# ---------------------------------------------------------------------------


class TestSourceType:
    def test_all_members_are_strings(self):
        for member in SourceType:
            assert isinstance(member.value, str)

    def test_expected_members(self):
        expected = {
            "excel_cell",
            "api_query",
            "calculated",
            "agent_derived",
            "manual",
            "database",
            "file",
        }
        assert {m.value for m in SourceType} == expected

    def test_construct_from_string(self):
        assert SourceType("api_query") is SourceType.API_QUERY

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            SourceType("not_a_source")


# ---------------------------------------------------------------------------
# ProvenanceMetadata validation
# ---------------------------------------------------------------------------


class TestProvenanceMetadataValidation:
    def test_valid_creation(self):
        meta = ProvenanceMetadata(
            source_type=SourceType.EXCEL_CELL,
            source_detail="Sheet1!B3",
            confidence=0.95,
        )
        assert meta.source_type is SourceType.EXCEL_CELL
        assert meta.source_detail == "Sheet1!B3"
        assert meta.confidence == 0.95
        assert meta.extracted_at is not None

    def test_string_source_type_coerced(self):
        meta = ProvenanceMetadata(source_type="manual")
        assert meta.source_type is SourceType.MANUAL

    def test_invalid_source_type_string_raises(self):
        with pytest.raises(ValueError):
            ProvenanceMetadata(source_type="bogus")

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            ProvenanceMetadata(source_type=SourceType.MANUAL, confidence=-0.1)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            ProvenanceMetadata(source_type=SourceType.MANUAL, confidence=1.01)

    def test_confidence_nan_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            ProvenanceMetadata(source_type=SourceType.MANUAL, confidence=float("nan"))

    def test_confidence_positive_inf_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            ProvenanceMetadata(source_type=SourceType.MANUAL, confidence=float("inf"))

    def test_confidence_negative_inf_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            ProvenanceMetadata(source_type=SourceType.MANUAL, confidence=float("-inf"))

    def test_confidence_zero_is_valid(self):
        meta = ProvenanceMetadata(source_type=SourceType.MANUAL, confidence=0.0)
        assert meta.confidence == 0.0

    def test_confidence_one_is_valid(self):
        meta = ProvenanceMetadata(source_type=SourceType.MANUAL, confidence=1.0)
        assert meta.confidence == 1.0

    def test_extracted_at_defaults_to_utc_now(self):
        before = datetime.now(UTC)
        meta = ProvenanceMetadata(source_type=SourceType.MANUAL)
        after = datetime.now(UTC)
        assert before <= meta.extracted_at <= after

    def test_explicit_extracted_at_preserved(self):
        ts = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        meta = ProvenanceMetadata(source_type=SourceType.API_QUERY, extracted_at=ts)
        assert meta.extracted_at == ts


# ---------------------------------------------------------------------------
# ProvenanceMetadata serialization round-trip
# ---------------------------------------------------------------------------


class TestProvenanceMetadataSerialization:
    def test_to_dict_structure(self):
        meta = ProvenanceMetadata(
            source_type=SourceType.API_QUERY,
            source_detail="GET /api/loans",
            confidence=0.9,
            change_reason="quarterly refresh",
        )
        d = meta.to_dict()
        assert d["source_type"] == "api_query"
        assert d["source_detail"] == "GET /api/loans"
        assert d["confidence"] == 0.9
        assert d["change_reason"] == "quarterly refresh"
        assert d["previous_value"] is None
        assert isinstance(d["extracted_at"], str)

    def test_round_trip(self):
        original = ProvenanceMetadata(
            source_type=SourceType.CALCULATED,
            source_detail="sum(outstanding)",
            confidence=0.85,
            previous_value=100.0,
            change_reason="recalculation",
        )
        d = original.to_dict()
        restored = ProvenanceMetadata.from_dict(d)

        assert restored.source_type is SourceType.CALCULATED
        assert restored.source_detail == original.source_detail
        assert restored.confidence == original.confidence
        assert restored.previous_value == original.previous_value
        assert restored.change_reason == original.change_reason
        assert restored.extracted_at == original.extracted_at

    def test_from_dict_does_not_mutate_input(self):
        d = {
            "source_type": "manual",
            "extracted_at": "2026-01-15T12:00:00+00:00",
        }
        original_d = dict(d)
        ProvenanceMetadata.from_dict(d)
        assert d == original_d


# ---------------------------------------------------------------------------
# Provenance[T] generic wrapper
# ---------------------------------------------------------------------------


class TestProvenanceGeneric:
    def test_provenance_float(self):
        p: Provenance[float] = Provenance(
            value=65_000_000.0,
            metadata=ProvenanceMetadata(
                source_type=SourceType.API_QUERY,
                confidence=0.95,
            ),
        )
        assert p.value == 65_000_000.0
        assert p.metadata.source_type is SourceType.API_QUERY

    def test_provenance_str(self):
        p: Provenance[str] = Provenance(
            value="performing",
            metadata=ProvenanceMetadata(source_type=SourceType.AGENT_DERIVED),
        )
        assert p.value == "performing"

    def test_provenance_int(self):
        p: Provenance[int] = Provenance(
            value=42,
            metadata=ProvenanceMetadata(source_type=SourceType.DATABASE),
        )
        assert p.value == 42

    def test_to_dict(self):
        p = Provenance(
            value=99.9,
            metadata=ProvenanceMetadata(
                source_type=SourceType.EXCEL_CELL,
                source_detail="Sheet1!C5",
                confidence=1.0,
            ),
        )
        d = p.to_dict()
        assert d["value"] == 99.9
        assert d["source_type"] == "excel_cell"
        assert d["source_detail"] == "Sheet1!C5"
        assert d["confidence"] == 1.0

    def test_round_trip(self):
        original = Provenance(
            value=3.14,
            metadata=ProvenanceMetadata(
                source_type=SourceType.CALCULATED,
                source_detail="pi approximation",
                confidence=0.999,
            ),
        )
        d = original.to_dict()
        restored = Provenance.from_dict(d)

        assert restored.value == original.value
        assert restored.metadata.source_type == original.metadata.source_type
        assert restored.metadata.source_detail == original.metadata.source_detail
        assert restored.metadata.confidence == original.metadata.confidence


# ---------------------------------------------------------------------------
# Previous-value tracking (manual for now, system-tracked in model integration)
# ---------------------------------------------------------------------------


class TestPreviousValueTracking:
    def test_previous_value_stored(self):
        meta = ProvenanceMetadata(
            source_type=SourceType.API_QUERY,
            previous_value=70_000_000.0,
            change_reason="quarterly refresh",
        )
        assert meta.previous_value == 70_000_000.0

    def test_previous_value_survives_round_trip(self):
        meta = ProvenanceMetadata(
            source_type=SourceType.MANUAL,
            previous_value={"nested": "data"},
        )
        d = meta.to_dict()
        restored = ProvenanceMetadata.from_dict(d)
        assert restored.previous_value == {"nested": "data"}

    def test_previous_value_in_provenance_to_dict(self):
        p = Provenance(
            value=65_000_000.0,
            metadata=ProvenanceMetadata(
                source_type=SourceType.API_QUERY,
                previous_value=70_000_000.0,
            ),
        )
        d = p.to_dict()
        assert d["previous_value"] == 70_000_000.0
        assert d["value"] == 65_000_000.0


# ---------------------------------------------------------------------------
# Package export smoke test
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_importable_from_dataflow(self):
        from dataflow import Provenance, ProvenanceMetadata, SourceType

        assert Provenance is not None
        assert ProvenanceMetadata is not None
        assert SourceType is not None
