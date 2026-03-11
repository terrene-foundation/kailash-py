"""
Unit tests for CARE-036: Knowledge Entry Structures.

Tests cover:
- KnowledgeType enum values
- KnowledgeEntry dataclass creation
- Factory method (create)
- Validation methods (validate, is_valid)
- Verification tracking (add_verification)
- Serialization (to_dict, from_dict)
- Edge cases and boundary conditions
"""

from datetime import datetime, timezone

import pytest
from kaizen.trust.knowledge import KnowledgeEntry, KnowledgeType


class TestKnowledgeType:
    """Tests for KnowledgeType enum."""

    def test_knowledge_type_factual_value(self):
        """FACTUAL enum has correct value."""
        assert KnowledgeType.FACTUAL.value == "factual"

    def test_knowledge_type_procedural_value(self):
        """PROCEDURAL enum has correct value."""
        assert KnowledgeType.PROCEDURAL.value == "procedural"

    def test_knowledge_type_tacit_trace_value(self):
        """TACIT_TRACE enum has correct value."""
        assert KnowledgeType.TACIT_TRACE.value == "tacit_trace"

    def test_knowledge_type_insight_value(self):
        """INSIGHT enum has correct value."""
        assert KnowledgeType.INSIGHT.value == "insight"

    def test_knowledge_type_decision_rationale_value(self):
        """DECISION_RATIONALE enum has correct value."""
        assert KnowledgeType.DECISION_RATIONALE.value == "decision_rationale"

    def test_all_knowledge_types_count(self):
        """All 5 knowledge types are defined."""
        assert len(KnowledgeType) == 5


class TestKnowledgeEntryCreation:
    """Tests for KnowledgeEntry creation."""

    def test_knowledge_entry_creation(self):
        """Create via factory, verify entry_id prefix and all fields."""
        entry = KnowledgeEntry.create(
            content="API rate limit is 1000 requests per minute",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-abc123",
        )

        # Verify entry_id format
        assert entry.entry_id.startswith("ke-")
        assert len(entry.entry_id) == 15  # "ke-" + 12 hex chars

        # Verify all fields
        assert entry.content == "API rate limit is 1000 requests per minute"
        assert entry.content_type == KnowledgeType.FACTUAL
        assert entry.source_agent_id == "agent-001"
        assert entry.trust_chain_ref == "chain-abc123"
        assert entry.constraint_envelope_ref is None
        assert isinstance(entry.created_at, datetime)
        assert entry.verified_by == []
        assert entry.confidence_score == 0.8
        assert entry.metadata == {}

    def test_knowledge_entry_creation_with_optional_fields(self):
        """Create with all optional fields populated."""
        entry = KnowledgeEntry.create(
            content="Procedure for data validation",
            content_type=KnowledgeType.PROCEDURAL,
            source_agent_id="agent-002",
            trust_chain_ref="chain-def456",
            constraint_envelope_ref="env-xyz789",
            confidence_score=0.95,
            metadata={"category": "validation", "priority": "high"},
        )

        assert entry.constraint_envelope_ref == "env-xyz789"
        assert entry.confidence_score == 0.95
        assert entry.metadata == {"category": "validation", "priority": "high"}

    def test_knowledge_entry_default_values(self):
        """Verify defaults (confidence=0.8, empty verified_by, etc.)."""
        entry = KnowledgeEntry.create(
            content="Test content",
            content_type=KnowledgeType.INSIGHT,
            source_agent_id="agent-test",
            trust_chain_ref="chain-test",
        )

        assert entry.confidence_score == 0.8
        assert entry.verified_by == []
        assert entry.metadata == {}
        assert entry.constraint_envelope_ref is None

    def test_entry_id_uniqueness(self):
        """Multiple creates produce unique IDs."""
        entries = [
            KnowledgeEntry.create(
                content=f"Content {i}",
                content_type=KnowledgeType.FACTUAL,
                source_agent_id="agent-001",
                trust_chain_ref="chain-001",
            )
            for i in range(100)
        ]

        entry_ids = [e.entry_id for e in entries]
        assert len(entry_ids) == len(set(entry_ids)), "Entry IDs should be unique"


class TestKnowledgeEntryValidation:
    """Tests for KnowledgeEntry validation."""

    @pytest.fixture
    def valid_entry(self):
        """Create a valid entry for testing."""
        return KnowledgeEntry.create(
            content="Valid content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
        )

    def test_knowledge_entry_validation_valid(self, valid_entry):
        """Valid entry passes validation."""
        assert valid_entry.validate() is True
        assert valid_entry.is_valid() is True

    def test_knowledge_entry_validation_invalid_id(self):
        """Wrong prefix fails validation."""
        entry = KnowledgeEntry(
            entry_id="invalid-id",  # Wrong prefix
            content="Content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
        )

        with pytest.raises(ValueError) as exc_info:
            entry.validate()
        assert "must start with 'ke-'" in str(exc_info.value)
        assert entry.is_valid() is False

    def test_knowledge_entry_validation_invalid_confidence_low(self):
        """Below 0.0 fails validation."""
        entry = KnowledgeEntry(
            entry_id="ke-abc123def456",
            content="Content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
            confidence_score=-0.1,
        )

        with pytest.raises(ValueError) as exc_info:
            entry.validate()
        assert "must be >= 0.0" in str(exc_info.value)
        assert entry.is_valid() is False

    def test_knowledge_entry_validation_invalid_confidence_high(self):
        """Above 1.0 fails validation."""
        entry = KnowledgeEntry(
            entry_id="ke-abc123def456",
            content="Content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
            confidence_score=1.1,
        )

        with pytest.raises(ValueError) as exc_info:
            entry.validate()
        assert "must be <= 1.0" in str(exc_info.value)
        assert entry.is_valid() is False

    def test_knowledge_entry_validation_empty_content(self):
        """Empty string fails validation."""
        entry = KnowledgeEntry(
            entry_id="ke-abc123def456",
            content="",  # Empty content
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
        )

        with pytest.raises(ValueError) as exc_info:
            entry.validate()
        assert "content must be non-empty" in str(exc_info.value)
        assert entry.is_valid() is False

    def test_knowledge_entry_validation_empty_source(self):
        """Empty source fails validation."""
        entry = KnowledgeEntry(
            entry_id="ke-abc123def456",
            content="Content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="",  # Empty source
            trust_chain_ref="chain-001",
        )

        with pytest.raises(ValueError) as exc_info:
            entry.validate()
        assert "source_agent_id must be non-empty" in str(exc_info.value)
        assert entry.is_valid() is False

    def test_knowledge_entry_validation_empty_trust_chain(self):
        """Empty trust chain ref fails validation."""
        entry = KnowledgeEntry(
            entry_id="ke-abc123def456",
            content="Content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="",  # Empty trust chain
        )

        with pytest.raises(ValueError) as exc_info:
            entry.validate()
        assert "trust_chain_ref must be non-empty" in str(exc_info.value)
        assert entry.is_valid() is False

    def test_confidence_score_boundary_zero(self):
        """0.0 is valid confidence score."""
        entry = KnowledgeEntry(
            entry_id="ke-abc123def456",
            content="Content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
            confidence_score=0.0,
        )

        assert entry.validate() is True
        assert entry.is_valid() is True

    def test_confidence_score_boundary_one(self):
        """1.0 is valid confidence score."""
        entry = KnowledgeEntry(
            entry_id="ke-abc123def456",
            content="Content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
            confidence_score=1.0,
        )

        assert entry.validate() is True
        assert entry.is_valid() is True


class TestKnowledgeEntryVerification:
    """Tests for verification tracking."""

    def test_add_verification(self):
        """Add verifiers, no duplicates."""
        entry = KnowledgeEntry.create(
            content="Content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
        )

        # Add first verifier
        entry.add_verification("verifier-001")
        assert entry.verified_by == ["verifier-001"]

        # Add second verifier
        entry.add_verification("verifier-002")
        assert entry.verified_by == ["verifier-001", "verifier-002"]

        # Try to add duplicate - should not be added
        entry.add_verification("verifier-001")
        assert entry.verified_by == ["verifier-001", "verifier-002"]
        assert len(entry.verified_by) == 2


class TestKnowledgeEntrySerialization:
    """Tests for serialization/deserialization."""

    def test_knowledge_entry_serialization_roundtrip(self):
        """to_dict() then from_dict() preserves all fields."""
        original = KnowledgeEntry.create(
            content="API rate limit is 1000 requests per minute",
            content_type=KnowledgeType.PROCEDURAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-abc123",
            constraint_envelope_ref="env-xyz789",
            confidence_score=0.92,
            metadata={"category": "api", "version": "2.0"},
        )
        original.add_verification("verifier-001")
        original.add_verification("verifier-002")

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = KnowledgeEntry.from_dict(data)

        # Verify all fields match
        assert restored.entry_id == original.entry_id
        assert restored.content == original.content
        assert restored.content_type == original.content_type
        assert restored.source_agent_id == original.source_agent_id
        assert restored.trust_chain_ref == original.trust_chain_ref
        assert restored.constraint_envelope_ref == original.constraint_envelope_ref
        assert restored.created_at == original.created_at
        assert restored.verified_by == original.verified_by
        assert restored.confidence_score == original.confidence_score
        assert restored.metadata == original.metadata

    def test_all_knowledge_types(self):
        """Create entry for each KnowledgeType, verify serialization."""
        for knowledge_type in KnowledgeType:
            entry = KnowledgeEntry.create(
                content=f"Content for {knowledge_type.value}",
                content_type=knowledge_type,
                source_agent_id="agent-001",
                trust_chain_ref="chain-001",
            )

            # Serialize
            data = entry.to_dict()
            assert data["content_type"] == knowledge_type.value

            # Deserialize
            restored = KnowledgeEntry.from_dict(data)
            assert restored.content_type == knowledge_type

    def test_metadata_field(self):
        """Custom metadata preserved in serialization."""
        complex_metadata = {
            "tags": ["important", "validated"],
            "source": {"system": "CRM", "version": "3.1"},
            "priority": 1,
            "active": True,
            "ratio": 0.75,
        }

        entry = KnowledgeEntry.create(
            content="Content with complex metadata",
            content_type=KnowledgeType.INSIGHT,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
            metadata=complex_metadata,
        )

        # Serialize and deserialize
        data = entry.to_dict()
        restored = KnowledgeEntry.from_dict(data)

        assert restored.metadata == complex_metadata

    def test_from_dict_missing_optional_fields(self):
        """from_dict handles missing optional fields."""
        minimal_data = {
            "entry_id": "ke-abc123def456",
            "content": "Minimal content",
            "content_type": "factual",
            "source_agent_id": "agent-001",
            "trust_chain_ref": "chain-001",
        }

        entry = KnowledgeEntry.from_dict(minimal_data)

        # Verify defaults are applied for missing optional fields
        assert entry.constraint_envelope_ref is None
        assert entry.verified_by == []
        assert entry.confidence_score == 0.8
        assert entry.metadata == {}
        # created_at should be generated
        assert isinstance(entry.created_at, datetime)

    def test_to_dict_datetime_format(self):
        """Datetime is serialized to ISO format."""
        entry = KnowledgeEntry.create(
            content="Content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
        )

        data = entry.to_dict()

        # Verify datetime is a string in ISO format
        assert isinstance(data["created_at"], str)
        # Should be parseable
        parsed = datetime.fromisoformat(data["created_at"])
        assert isinstance(parsed, datetime)

    def test_to_dict_enum_format(self):
        """Enum is serialized to its value."""
        entry = KnowledgeEntry.create(
            content="Content",
            content_type=KnowledgeType.DECISION_RATIONALE,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
        )

        data = entry.to_dict()

        assert data["content_type"] == "decision_rationale"
        assert isinstance(data["content_type"], str)

    def test_from_dict_with_datetime_object(self):
        """from_dict handles datetime object (not just string)."""
        now = datetime.now(timezone.utc)
        data = {
            "entry_id": "ke-abc123def456",
            "content": "Content",
            "content_type": "factual",
            "source_agent_id": "agent-001",
            "trust_chain_ref": "chain-001",
            "created_at": now,  # datetime object, not string
        }

        entry = KnowledgeEntry.from_dict(data)
        assert entry.created_at == now
