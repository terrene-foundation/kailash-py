"""
Test Signature Inheritance - Child signatures should MERGE parent fields.

This test verifies that when a child signature extends a parent signature,
it inherits ALL parent fields and adds its own fields (total = parent + child).

Bug Report:
- Before fix: ReferralConversationSignature only had 4 fields (lost 6 parent fields)
- After fix: ReferralConversationSignature has 10 fields (6 from parent + 4 from child)
"""

import pytest
from kaizen.core.structured_output import (
    StructuredOutputGenerator,
    create_structured_output_config,
)
from kaizen.signatures import InputField, OutputField, Signature


class ConversationSignature(Signature):
    """Parent signature with 6 output fields."""

    conversation_text: str = InputField(desc="The conversation text")

    # Parent fields (6 fields)
    next_action: str = OutputField(desc="Next action to take")
    extracted_fields: dict = OutputField(desc="Extracted fields from conversation")
    conversation_context: str = OutputField(desc="Context of conversation")
    user_intent: str = OutputField(desc="User intent")
    system_response: str = OutputField(desc="System response")
    confidence_level: float = OutputField(desc="Confidence level 0-1")


class ReferralConversationSignature(ConversationSignature):
    """Child signature that extends parent with 4 additional fields."""

    # Child fields (4 new fields)
    confidence_score: float = OutputField(desc="Confidence score for referral")
    user_identity_detected: bool = OutputField(desc="Whether user identity detected")
    referral_needed: bool = OutputField(desc="Whether referral is needed")
    referral_reason: str = OutputField(desc="Reason for referral")


class TestSignatureInheritance:
    """Test signature field inheritance."""

    def test_parent_signature_has_correct_fields(self):
        """Test parent signature has all its fields."""
        sig = ConversationSignature()

        # Parent should have 1 input field
        assert len(sig.input_fields) == 1
        assert "conversation_text" in sig.input_fields

        # Parent should have 6 output fields
        assert len(sig.output_fields) == 6
        assert "next_action" in sig.output_fields
        assert "extracted_fields" in sig.output_fields
        assert "conversation_context" in sig.output_fields
        assert "user_intent" in sig.output_fields
        assert "system_response" in sig.output_fields
        assert "confidence_level" in sig.output_fields

    def test_child_signature_merges_parent_fields(self):
        """Test child signature MERGES parent fields instead of replacing them."""
        sig = ReferralConversationSignature()

        # Child should have 1 input field (from parent)
        assert len(sig.input_fields) == 1
        assert "conversation_text" in sig.input_fields

        # CRITICAL: Child should have ALL 10 output fields (6 from parent + 4 from child)
        assert (
            len(sig.output_fields) == 10
        ), f"Expected 10 fields, got {len(sig.output_fields)}: {list(sig.output_fields.keys())}"

        # Verify parent fields are present
        assert "next_action" in sig.output_fields
        assert "extracted_fields" in sig.output_fields
        assert "conversation_context" in sig.output_fields
        assert "user_intent" in sig.output_fields
        assert "system_response" in sig.output_fields
        assert "confidence_level" in sig.output_fields

        # Verify child fields are present
        assert "confidence_score" in sig.output_fields
        assert "user_identity_detected" in sig.output_fields
        assert "referral_needed" in sig.output_fields
        assert "referral_reason" in sig.output_fields

    def test_child_signature_field_types_preserved(self):
        """Test that field types are preserved through inheritance."""
        sig = ReferralConversationSignature()

        # Check parent field types
        assert sig.output_fields["next_action"]["type"] == str
        assert sig.output_fields["extracted_fields"]["type"] == dict
        assert sig.output_fields["confidence_level"]["type"] == float

        # Check child field types
        assert sig.output_fields["confidence_score"]["type"] == float
        assert sig.output_fields["user_identity_detected"]["type"] == bool
        assert sig.output_fields["referral_needed"]["type"] == bool

    def test_child_signature_field_descriptions_preserved(self):
        """Test that field descriptions are preserved through inheritance."""
        sig = ReferralConversationSignature()

        # Check parent field descriptions
        assert sig.output_fields["next_action"]["desc"] == "Next action to take"
        assert sig.output_fields["user_intent"]["desc"] == "User intent"

        # Check child field descriptions
        assert (
            sig.output_fields["confidence_score"]["desc"]
            == "Confidence score for referral"
        )
        assert (
            sig.output_fields["user_identity_detected"]["desc"]
            == "Whether user identity detected"
        )

    def test_structured_output_schema_includes_all_fields(self):
        """Test that OpenAI Structured Outputs schema includes ALL fields from inheritance chain."""
        sig = ReferralConversationSignature()

        # Generate JSON schema
        schema = StructuredOutputGenerator.signature_to_json_schema(sig)

        # Verify all 10 output fields are in the schema
        assert len(schema["properties"]) == 10
        assert len(schema["required"]) == 10

        # Verify parent fields in schema
        assert "next_action" in schema["properties"]
        assert "extracted_fields" in schema["properties"]
        assert "conversation_context" in schema["properties"]
        assert "user_intent" in schema["properties"]
        assert "system_response" in schema["properties"]
        assert "confidence_level" in schema["properties"]

        # Verify child fields in schema
        assert "confidence_score" in schema["properties"]
        assert "user_identity_detected" in schema["properties"]
        assert "referral_needed" in schema["properties"]
        assert "referral_reason" in schema["properties"]

    def test_structured_output_config_enforces_all_fields(self):
        """Test that OpenAI Structured Outputs config will enforce all 10 fields."""
        sig = ReferralConversationSignature()

        # Create structured output config
        config = create_structured_output_config(sig, strict=True)

        # Verify config structure
        assert config["type"] == "json_schema"
        assert config["json_schema"]["strict"] is True

        # Verify schema has all fields
        schema = config["json_schema"]["schema"]
        assert len(schema["properties"]) == 10
        assert len(schema["required"]) == 10

    def test_child_can_override_parent_field(self):
        """Test that child can override parent field with new definition."""

        class ParentSig(Signature):
            input_text: str = InputField(desc="Input text")
            result: str = OutputField(desc="Parent result")

        class ChildSig(ParentSig):
            # Override parent field with new description
            result: str = OutputField(desc="Child result (overridden)")
            extra: str = OutputField(desc="Extra field")

        sig = ChildSig()

        # Should have 2 output fields (parent overridden + child extra)
        assert len(sig.output_fields) == 2

        # Child override should take precedence
        assert sig.output_fields["result"]["desc"] == "Child result (overridden)"
        assert "extra" in sig.output_fields

    def test_multi_level_inheritance(self):
        """Test that inheritance works across multiple levels."""

        class Level1(Signature):
            input1: str = InputField(desc="Level 1 input")
            output1: str = OutputField(desc="Level 1 output")

        class Level2(Level1):
            output2: str = OutputField(desc="Level 2 output")

        class Level3(Level2):
            output3: str = OutputField(desc="Level 3 output")

        sig = Level3()

        # Should have 1 input field
        assert len(sig.input_fields) == 1
        assert "input1" in sig.input_fields

        # Should have 3 output fields (1 from each level)
        assert len(sig.output_fields) == 3
        assert "output1" in sig.output_fields
        assert "output2" in sig.output_fields
        assert "output3" in sig.output_fields
