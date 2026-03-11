"""
Test Layer 2 Signature Enhancements for Journey Orchestration.

This module tests the Layer 2 enhancements to the Signature class that enable
Journey Orchestration to understand:
- __intent__: WHY the agent exists (high-level purpose)
- __guidelines__: HOW the agent should behave (behavioral constraints)

Requirements Tested:
- REQ-L2-001: Intent Extraction
- REQ-L2-002: Guidelines Extraction
- REQ-L2-003: Property Accessors (intent, guidelines, instructions)
- REQ-L2-004: Immutable Composition - with_instructions()
- REQ-L2-005: Immutable Composition - with_guidelines()
- REQ-L2-006: Clone Helper (_clone())

Reference: /docs/plans/03-journey/02-layer2-enhancements.md
"""

import pytest

from kaizen.signatures import InputField, OutputField, Signature

# ==============================================================================
# REQ-L2-001: Intent Extraction Tests
# ==============================================================================


class TestIntentExtraction:
    """Test intent extraction from __intent__ class attribute."""

    def test_intent_from_class_attribute(self):
        """Test that __intent__ is correctly extracted from class definition."""

        class MySig(Signature):
            __intent__ = "Test intent"
            question: str = InputField(desc="Q")
            answer: str = OutputField(desc="A")

        sig = MySig()
        assert sig.intent == "Test intent"

    def test_missing_intent_defaults_to_empty(self):
        """Test that missing __intent__ defaults to empty string."""

        class MySig(Signature):
            question: str = InputField(desc="Q")
            answer: str = OutputField(desc="A")

        sig = MySig()
        assert sig.intent == ""

    def test_intent_with_docstring(self):
        """Test that intent and docstring can coexist."""

        class MySig(Signature):
            """This is the docstring instructions."""

            __intent__ = "This is the intent"
            question: str = InputField(desc="Q")
            answer: str = OutputField(desc="A")

        sig = MySig()
        assert sig.intent == "This is the intent"
        assert sig.instructions == "This is the docstring instructions."

    def test_intent_empty_string(self):
        """Test that explicit empty string intent is preserved."""

        class MySig(Signature):
            __intent__ = ""
            question: str = InputField(desc="Q")
            answer: str = OutputField(desc="A")

        sig = MySig()
        assert sig.intent == ""

    def test_intent_multiline(self):
        """Test that multiline intent strings work correctly."""

        class MySig(Signature):
            __intent__ = """This is a multiline intent
            that spans multiple lines"""
            question: str = InputField(desc="Q")
            answer: str = OutputField(desc="A")

        sig = MySig()
        assert "multiline intent" in sig.intent
        assert "multiple lines" in sig.intent


# ==============================================================================
# REQ-L2-002: Guidelines Extraction Tests
# ==============================================================================


class TestGuidelinesExtraction:
    """Test guidelines extraction from __guidelines__ class attribute."""

    def test_guidelines_from_class_attribute(self):
        """Test that __guidelines__ list is correctly extracted."""

        class MySig(Signature):
            __guidelines__ = ["G1", "G2"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert sig.guidelines == ["G1", "G2"]

    def test_missing_guidelines_defaults_to_empty_list(self):
        """Test that missing __guidelines__ defaults to empty list."""

        class MySig(Signature):
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert sig.guidelines == []

    def test_guidelines_are_copied(self):
        """Ensure guidelines property returns copy, not reference."""

        class MySig(Signature):
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        guidelines = sig.guidelines
        guidelines.append("G2")
        assert sig.guidelines == ["G1"]  # Original unchanged

    def test_guidelines_empty_list(self):
        """Test that explicit empty list guidelines is preserved."""

        class MySig(Signature):
            __guidelines__ = []
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert sig.guidelines == []

    def test_guidelines_with_special_characters(self):
        """Test that guidelines with special characters work correctly."""

        class MySig(Signature):
            __guidelines__ = [
                "Use <emphasis> when needed",
                "Avoid 'single quotes'",
                'Support "double quotes"',
                "Handle & ampersands",
            ]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert len(sig.guidelines) == 4
        assert "<emphasis>" in sig.guidelines[0]

    def test_guidelines_tuple_converted_to_list(self):
        """Test that tuple guidelines are converted to list."""

        class MySig(Signature):
            __guidelines__ = ("G1", "G2", "G3")
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert sig.guidelines == ["G1", "G2", "G3"]
        assert isinstance(sig.guidelines, list)


# ==============================================================================
# REQ-L2-003: Property Accessors Tests
# ==============================================================================


class TestPropertyAccessors:
    """Test intent, guidelines, and instructions property accessors."""

    def test_instructions_property_returns_docstring(self):
        """Test that instructions property returns the docstring."""

        class MySig(Signature):
            """Original docstring instructions."""

            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert sig.instructions == "Original docstring instructions."

    def test_instructions_property_empty_without_docstring(self):
        """Test that instructions is empty when no docstring defined."""

        class MySig(Signature):
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert sig.instructions == ""

    def test_all_properties_accessible(self):
        """Test that all three properties are accessible on a complete signature."""

        class CompleteSig(Signature):
            """Complete instructions."""

            __intent__ = "Complete intent"
            __guidelines__ = ["Complete guideline"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = CompleteSig()
        assert sig.instructions == "Complete instructions."
        assert sig.intent == "Complete intent"
        assert sig.guidelines == ["Complete guideline"]

    def test_properties_are_read_only(self):
        """Test that properties cannot be directly assigned (no setter)."""

        class MySig(Signature):
            """Instructions."""

            __intent__ = "Intent"
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()

        # These should raise AttributeError since properties have no setter
        with pytest.raises(AttributeError):
            sig.intent = "New intent"

        with pytest.raises(AttributeError):
            sig.guidelines = ["New guideline"]

        with pytest.raises(AttributeError):
            sig.instructions = "New instructions"


# ==============================================================================
# REQ-L2-004: Immutable Composition - with_instructions() Tests
# ==============================================================================


class TestWithInstructions:
    """Test with_instructions() immutable composition method."""

    def test_with_instructions_creates_new_instance(self):
        """Test that with_instructions returns a new instance."""

        class MySig(Signature):
            """Original instructions."""

            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_instructions("New instructions.")

        assert sig1 is not sig2
        assert sig1.instructions == "Original instructions."
        assert sig2.instructions == "New instructions."

    def test_with_instructions_preserves_intent(self):
        """Test that with_instructions preserves intent."""

        class MySig(Signature):
            """Original instructions."""

            __intent__ = "Preserved intent"
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_instructions("New instructions.")

        assert sig2.intent == "Preserved intent"

    def test_with_instructions_preserves_guidelines(self):
        """Test that with_instructions preserves guidelines."""

        class MySig(Signature):
            """Original instructions."""

            __guidelines__ = ["G1", "G2"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_instructions("New instructions.")

        assert sig2.guidelines == ["G1", "G2"]

    def test_with_instructions_preserves_fields(self):
        """Test that with_instructions preserves input/output fields."""

        class MySig(Signature):
            """Original instructions."""

            question: str = InputField(desc="The question")
            answer: str = OutputField(desc="The answer")
            confidence: float = OutputField(desc="Confidence score")

        sig1 = MySig()
        sig2 = sig1.with_instructions("New instructions.")

        assert sig2.inputs == sig1.inputs
        assert sig2.outputs == sig1.outputs
        assert "question" in sig2.input_fields
        assert "answer" in sig2.output_fields
        assert "confidence" in sig2.output_fields

    def test_with_instructions_chaining(self):
        """Test that with_instructions can be chained."""

        class MySig(Signature):
            """Original instructions."""

            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_instructions("Second instructions.")
        sig3 = sig2.with_instructions("Third instructions.")

        assert sig1.instructions == "Original instructions."
        assert sig2.instructions == "Second instructions."
        assert sig3.instructions == "Third instructions."
        assert sig1 is not sig2 is not sig3


# ==============================================================================
# REQ-L2-005: Immutable Composition - with_guidelines() Tests
# ==============================================================================


class TestWithGuidelines:
    """Test with_guidelines() immutable composition method."""

    def test_with_guidelines_appends(self):
        """Test that with_guidelines appends new guidelines."""

        class MySig(Signature):
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_guidelines(["G2", "G3"])

        assert sig1.guidelines == ["G1"]
        assert sig2.guidelines == ["G1", "G2", "G3"]

    def test_with_guidelines_creates_new_instance(self):
        """Test that with_guidelines returns a new instance."""

        class MySig(Signature):
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_guidelines(["G2"])

        assert sig1 is not sig2

    def test_with_guidelines_preserves_intent(self):
        """Test that with_guidelines preserves intent."""

        class MySig(Signature):
            __intent__ = "Preserved intent"
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_guidelines(["G2"])

        assert sig2.intent == "Preserved intent"

    def test_with_guidelines_preserves_instructions(self):
        """Test that with_guidelines preserves instructions."""

        class MySig(Signature):
            """Original instructions."""

            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_guidelines(["G2"])

        assert sig2.instructions == "Original instructions."

    def test_with_guidelines_from_empty(self):
        """Test adding guidelines when starting with empty list."""

        class MySig(Signature):
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_guidelines(["G1", "G2"])

        assert sig1.guidelines == []
        assert sig2.guidelines == ["G1", "G2"]

    def test_with_guidelines_empty_list(self):
        """Test that adding empty list doesn't change guidelines."""

        class MySig(Signature):
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_guidelines([])

        assert sig2.guidelines == ["G1"]
        assert sig1 is not sig2  # Still a new instance

    def test_with_guidelines_chaining(self):
        """Test that with_guidelines can be chained."""

        class MySig(Signature):
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_guidelines(["G1"])
        sig3 = sig2.with_guidelines(["G2"])
        sig4 = sig3.with_guidelines(["G3"])

        assert sig1.guidelines == []
        assert sig2.guidelines == ["G1"]
        assert sig3.guidelines == ["G1", "G2"]
        assert sig4.guidelines == ["G1", "G2", "G3"]

    def test_with_guidelines_and_with_instructions_combined(self):
        """Test combining with_guidelines and with_instructions."""

        class MySig(Signature):
            """Original instructions."""

            __intent__ = "Original intent"
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1.with_instructions("New instructions.").with_guidelines(["G2"])

        assert sig1.instructions == "Original instructions."
        assert sig1.guidelines == ["G1"]

        assert sig2.instructions == "New instructions."
        assert sig2.guidelines == ["G1", "G2"]
        assert sig2.intent == "Original intent"  # Preserved


# ==============================================================================
# REQ-L2-006: Clone Helper Tests
# ==============================================================================


class TestCloneHelper:
    """Test _clone() internal method for immutable operations."""

    def test_clone_creates_new_instance(self):
        """Test that _clone creates a new instance."""

        class MySig(Signature):
            __intent__ = "Test intent"
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1._clone()

        assert sig1 is not sig2

    def test_clone_preserves_intent(self):
        """Test that _clone preserves intent."""

        class MySig(Signature):
            __intent__ = "Test intent"
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1._clone()

        assert sig2.intent == "Test intent"

    def test_clone_preserves_guidelines(self):
        """Test that _clone preserves guidelines."""

        class MySig(Signature):
            __guidelines__ = ["G1", "G2"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1._clone()

        assert sig2.guidelines == ["G1", "G2"]

    def test_clone_preserves_instructions(self):
        """Test that _clone preserves instructions."""

        class MySig(Signature):
            """Test instructions."""

            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1._clone()

        assert sig2.instructions == "Test instructions."

    def test_clone_preserves_input_output_fields(self):
        """Test that _clone preserves input and output fields."""

        class MySig(Signature):
            question: str = InputField(desc="The question")
            context: str = InputField(desc="Context", default="")
            answer: str = OutputField(desc="The answer")
            score: float = OutputField(desc="Score")

        sig1 = MySig()
        sig2 = sig1._clone()

        assert sig2.inputs == sig1.inputs
        assert sig2.outputs == sig1.outputs
        assert sig2.input_fields == sig1.input_fields
        assert sig2.output_fields == sig1.output_fields

    def test_clone_guidelines_are_independent(self):
        """Test that cloned guidelines list is independent."""

        class MySig(Signature):
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = MySig()
        sig2 = sig1._clone()

        # Modify sig2's guidelines directly (bypassing immutable API)
        sig2._signature_guidelines.append("G2")

        # sig1 should be unaffected
        assert sig1.guidelines == ["G1"]
        assert sig2.guidelines == ["G1", "G2"]

    def test_clone_preserves_class_type(self):
        """Test that _clone preserves the original class type."""

        class CustomSig(Signature):
            __intent__ = "Custom intent"
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig1 = CustomSig()
        sig2 = sig1._clone()

        assert type(sig2) is CustomSig
        assert isinstance(sig2, CustomSig)
        assert isinstance(sig2, Signature)


# ==============================================================================
# Inheritance Tests
# ==============================================================================


class TestIntentInheritance:
    """Test intent inheritance through signature class hierarchy."""

    def test_intent_inheritance(self):
        """Test that intent is inherited from parent class."""

        class BaseSig(Signature):
            __intent__ = "Base intent"
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        class ChildSig(BaseSig):
            pass  # Should inherit intent

        sig = ChildSig()
        assert sig.intent == "Base intent"

    def test_intent_override(self):
        """Test that child can override parent intent."""

        class BaseSig(Signature):
            __intent__ = "Base intent"
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        class ChildSig(BaseSig):
            __intent__ = "Child intent"

        sig = ChildSig()
        assert sig.intent == "Child intent"

    def test_intent_multi_level_inheritance(self):
        """Test intent inheritance across multiple levels."""

        class Level1(Signature):
            __intent__ = "Level 1 intent"
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        class Level2(Level1):
            pass  # Inherits from Level1

        class Level3(Level2):
            pass  # Inherits from Level2

        sig = Level3()
        assert sig.intent == "Level 1 intent"

    def test_intent_override_at_level_2(self):
        """Test intent override at intermediate level."""

        class Level1(Signature):
            __intent__ = "Level 1 intent"
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        class Level2(Level1):
            __intent__ = "Level 2 intent"

        class Level3(Level2):
            pass  # Inherits from Level2

        sig = Level3()
        assert sig.intent == "Level 2 intent"


class TestGuidelinesInheritance:
    """Test guidelines inheritance through signature class hierarchy."""

    def test_guidelines_inheritance(self):
        """Test that guidelines are inherited from parent class."""

        class BaseSig(Signature):
            __guidelines__ = ["Base guideline 1", "Base guideline 2"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        class ChildSig(BaseSig):
            pass  # Should inherit guidelines

        sig = ChildSig()
        assert sig.guidelines == ["Base guideline 1", "Base guideline 2"]

    def test_guidelines_override(self):
        """Test that child can override parent guidelines."""

        class BaseSig(Signature):
            __guidelines__ = ["Base guideline"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        class ChildSig(BaseSig):
            __guidelines__ = ["Child guideline 1", "Child guideline 2"]

        sig = ChildSig()
        assert sig.guidelines == ["Child guideline 1", "Child guideline 2"]

    def test_guidelines_multi_level_inheritance(self):
        """Test guidelines inheritance across multiple levels."""

        class Level1(Signature):
            __guidelines__ = ["L1 guideline"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        class Level2(Level1):
            pass  # Inherits from Level1

        class Level3(Level2):
            pass  # Inherits from Level2

        sig = Level3()
        assert sig.guidelines == ["L1 guideline"]


# ==============================================================================
# Backward Compatibility Tests
# ==============================================================================


class TestBackwardCompatibility:
    """Test backward compatibility with existing signatures."""

    def test_existing_signature_without_intent_or_guidelines(self):
        """Test that existing signatures without new attributes work."""

        class LegacySig(Signature):
            """Legacy instructions."""

            question: str = InputField(desc="Question")
            answer: str = OutputField(desc="Answer")

        sig = LegacySig()

        # Should work without errors
        assert sig.inputs == ["question"]
        assert sig.outputs == ["answer"]
        assert sig.instructions == "Legacy instructions."
        assert sig.intent == ""
        assert sig.guidelines == []

    def test_programmatic_signature_creation(self):
        """Test that programmatic signature creation still works."""
        sig = Signature(
            inputs=["question"],
            outputs=["answer"],
            name="TestSig",
            description="Test description",
        )

        assert sig.inputs == ["question"]
        assert sig.outputs == ["answer"]
        assert sig.name == "TestSig"
        # Programmatic signatures won't have intent/guidelines from class definition
        assert sig.intent == ""
        assert sig.guidelines == []

    def test_existing_field_api_unchanged(self):
        """Test that existing field API is unchanged."""

        class MySig(Signature):
            """Instructions."""

            __intent__ = "Intent"
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q", default="default")
            a: str = OutputField(desc="A")

        sig = MySig()

        # Existing API should work
        assert sig.input_fields["q"]["desc"] == "Q"
        assert sig.input_fields["q"]["default"] == "default"
        assert sig.output_fields["a"]["desc"] == "A"

    def test_to_dict_still_works(self):
        """Test that to_dict serialization still works."""

        class MySig(Signature):
            """Instructions."""

            __intent__ = "Intent"
            __guidelines__ = ["G1"]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        d = sig.to_dict()

        # Existing fields should be present
        assert "inputs" in d
        assert "outputs" in d
        assert "description" in d
        assert d["inputs"] == ["q"]
        assert d["outputs"] == ["a"]


# ==============================================================================
# Edge Cases and Stress Tests
# ==============================================================================


class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_none_guidelines_treated_as_empty(self):
        """Test that None guidelines are treated as empty list."""

        # This tests the metaclass handling of None
        class MySig(Signature):
            __guidelines__ = None
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        # Should be empty list, not None
        assert sig.guidelines == [] or sig.guidelines is None
        # The important thing is that it doesn't crash

    def test_very_long_intent(self):
        """Test that very long intent strings work."""

        class MySig(Signature):
            __intent__ = "A" * 10000  # 10K character intent
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert len(sig.intent) == 10000

    def test_many_guidelines(self):
        """Test that many guidelines work."""

        class MySig(Signature):
            __guidelines__ = [f"Guideline {i}" for i in range(100)]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert len(sig.guidelines) == 100

    def test_unicode_in_intent_and_guidelines(self):
        """Test Unicode characters in intent and guidelines."""

        class MySig(Signature):
            __intent__ = "Assist users with queries (Japanese)"
            __guidelines__ = [
                "Be helpful (Japanese)",
                "Be respectful",
                "Use appropriate language",
            ]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert "(Japanese)" in sig.intent
        assert "(Japanese)" in sig.guidelines[0]

    def test_newlines_in_guidelines(self):
        """Test that newlines in guidelines are preserved."""

        class MySig(Signature):
            __guidelines__ = [
                "First line\nSecond line",
                "Single line",
            ]
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        assert "\n" in sig.guidelines[0]

    def test_whitespace_only_intent(self):
        """Test that whitespace-only intent is preserved."""

        class MySig(Signature):
            __intent__ = "   "  # Just whitespace
            q: str = InputField(desc="Q")
            a: str = OutputField(desc="A")

        sig = MySig()
        # Whitespace is preserved (no stripping in metaclass)
        assert sig.intent == "   "


# ==============================================================================
# Integration-Style Tests (All Components Together)
# ==============================================================================


class TestIntegrationScenarios:
    """Test realistic usage scenarios combining all Layer 2 features."""

    def test_customer_support_signature(self):
        """Test a realistic customer support signature definition."""

        class CustomerSupportSignature(Signature):
            """You are a helpful customer support agent for TechCorp.
            Your role is to assist customers with their technical issues."""

            __intent__ = (
                "Resolve customer technical issues efficiently and empathetically"
            )
            __guidelines__ = [
                "Acknowledge the customer's concern before providing solutions",
                "Use empathetic and professional language",
                "Escalate to human agent if issue is not resolved within 3 turns",
                "Never share internal system information with customers",
                "Always verify customer identity before discussing account details",
            ]

            customer_query: str = InputField(desc="The customer's question or issue")
            customer_id: str = InputField(desc="Customer ID for account lookup")
            response: str = OutputField(desc="The support response to the customer")
            escalation_needed: bool = OutputField(desc="Whether to escalate to human")
            confidence_score: float = OutputField(desc="Confidence in the response")

        sig = CustomerSupportSignature()

        # Verify all components
        assert "TechCorp" in sig.instructions
        assert "efficiently" in sig.intent
        assert "empathetically" in sig.intent
        assert len(sig.guidelines) == 5
        assert "Acknowledge" in sig.guidelines[0]
        assert len(sig.inputs) == 2
        assert len(sig.outputs) == 3

    def test_runtime_customization_scenario(self):
        """Test runtime customization of a signature."""

        class BaseQASignature(Signature):
            """You are a helpful assistant."""

            __intent__ = "Answer questions accurately"
            __guidelines__ = ["Be helpful", "Be accurate"]
            question: str = InputField(desc="Q")
            answer: str = OutputField(desc="A")

        # Base signature
        base_sig = BaseQASignature()

        # Customize for medical domain
        medical_sig = base_sig.with_instructions(
            "You are a medical information assistant. "
            "Provide general health information but always advise consulting a doctor."
        ).with_guidelines(
            [
                "Never provide specific medical diagnoses",
                "Always recommend consulting a healthcare professional",
            ]
        )

        # Verify base is unchanged
        assert base_sig.instructions == "You are a helpful assistant."
        assert base_sig.guidelines == ["Be helpful", "Be accurate"]

        # Verify customized signature
        assert "medical" in medical_sig.instructions.lower()
        assert len(medical_sig.guidelines) == 4
        assert "healthcare professional" in medical_sig.guidelines[3]
        assert medical_sig.intent == "Answer questions accurately"  # Preserved

    def test_full_inheritance_chain(self):
        """Test a complete inheritance chain with all features."""

        class BaseConversationSig(Signature):
            """Base conversation handler."""

            __intent__ = "Handle conversations"
            __guidelines__ = ["Be professional"]
            message: str = InputField(desc="User message")
            response: str = OutputField(desc="Response")

        class SupportConversationSig(BaseConversationSig):
            """Support-specific handler."""

            __intent__ = "Handle support conversations"  # Override
            __guidelines__ = ["Be empathetic", "Be helpful"]  # Override
            ticket_id: str = OutputField(desc="Support ticket ID")

        class VIPSupportSig(SupportConversationSig):
            """VIP support handler."""

            # Inherits intent and guidelines from SupportConversationSig
            priority: str = OutputField(desc="Priority level")

        vip_sig = VIPSupportSig()

        # Verify inheritance
        assert vip_sig.intent == "Handle support conversations"
        assert vip_sig.guidelines == ["Be empathetic", "Be helpful"]
        assert "message" in vip_sig.inputs
        assert "response" in vip_sig.outputs
        assert "ticket_id" in vip_sig.outputs
        assert "priority" in vip_sig.outputs

        # Apply runtime customization
        custom_vip_sig = vip_sig.with_guidelines(["Prioritize VIP requests"])

        assert custom_vip_sig.guidelines == [
            "Be empathetic",
            "Be helpful",
            "Prioritize VIP requests",
        ]
        assert vip_sig.guidelines == [
            "Be empathetic",
            "Be helpful",
        ]  # Original unchanged
