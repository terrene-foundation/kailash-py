"""
Unit tests for InputField and OutputField description parameter support.

Tests the fix for GitHub Issue #XXX:
  "Signature input parameters not passed to LLM"

Root Cause:
  - Documentation showed: InputField(description='...')
  - Implementation expected: InputField(desc='...')
  - Using 'description' stored it in metadata, not self.desc

Fix:
  - InputField now accepts both 'description' and 'desc'
  - OutputField now accepts both 'description' and 'desc'
  - 'description' takes precedence to match documentation
"""

import pytest
from kaizen.signatures import InputField, OutputField, Signature


class TestInputFieldDescriptionParameter:
    """Test InputField accepts 'description' parameter."""

    def test_inputfield_with_description_param(self):
        """Test InputField(description='...') sets self.desc correctly."""
        field = InputField(description="Test description")

        assert field.desc == "Test description"
        assert field.metadata == {}  # description not in metadata

    def test_inputfield_with_desc_param(self):
        """Test InputField(desc='...') still works (backward compat)."""
        field = InputField(desc="Test desc")

        assert field.desc == "Test desc"
        assert field.metadata == {}

    def test_inputfield_description_takes_precedence(self):
        """Test 'description' takes precedence over 'desc'."""
        field = InputField(desc="Old", description="New")

        assert field.desc == "New"  # description wins
        assert field.metadata == {}

    def test_inputfield_defaults_to_empty_string(self):
        """Test InputField() defaults to empty description."""
        field = InputField()

        assert field.desc == ""
        assert field.metadata == {}

    def test_inputfield_description_with_other_params(self):
        """Test description works with other parameters."""
        field = InputField(
            description="Test description", default="default_value", required=False
        )

        assert field.desc == "Test description"
        assert field.default == "default_value"
        assert field.required is False
        assert field.metadata == {}

    def test_inputfield_description_with_metadata(self):
        """Test description works with additional metadata."""
        field = InputField(description="Test description", custom_key="custom_value")

        assert field.desc == "Test description"
        assert field.metadata == {"custom_key": "custom_value"}


class TestOutputFieldDescriptionParameter:
    """Test OutputField accepts 'description' parameter."""

    def test_outputfield_with_description_param(self):
        """Test OutputField(description='...') sets self.desc correctly."""
        field = OutputField(description="Output description")

        assert field.desc == "Output description"
        assert field.metadata == {}

    def test_outputfield_with_desc_param(self):
        """Test OutputField(desc='...') still works (backward compat)."""
        field = OutputField(desc="Output desc")

        assert field.desc == "Output desc"
        assert field.metadata == {}

    def test_outputfield_description_takes_precedence(self):
        """Test 'description' takes precedence over 'desc'."""
        field = OutputField(desc="Old", description="New")

        assert field.desc == "New"  # description wins
        assert field.metadata == {}

    def test_outputfield_defaults_to_empty_string(self):
        """Test OutputField() defaults to empty description."""
        field = OutputField()

        assert field.desc == ""
        assert field.metadata == {}

    def test_outputfield_description_with_metadata(self):
        """Test description works with additional metadata."""
        field = OutputField(description="Output description", custom_key="custom_value")

        assert field.desc == "Output description"
        assert field.metadata == {"custom_key": "custom_value"}


class TestSignatureWithDescriptionParameter:
    """Test Signature class with description parameter."""

    def test_signature_input_fields_with_description(self):
        """Test Signature correctly processes InputField with description."""

        class TestSignature(Signature):
            text: str = InputField(description="Text to process")
            context: str = InputField(description="Additional context")

        sig = TestSignature()

        # Check input_fields dict
        assert "text" in sig.input_fields
        assert sig.input_fields["text"]["desc"] == "Text to process"

        assert "context" in sig.input_fields
        assert sig.input_fields["context"]["desc"] == "Additional context"

    def test_signature_output_fields_with_description(self):
        """Test Signature correctly processes OutputField with description."""

        class TestSignature(Signature):
            text: str = InputField(description="Input text")
            result: str = OutputField(description="Processed result")
            confidence: float = OutputField(description="Confidence score")

        sig = TestSignature()

        # Check output_fields dict
        assert "result" in sig.output_fields
        assert sig.output_fields["result"]["desc"] == "Processed result"

        assert "confidence" in sig.output_fields
        assert sig.output_fields["confidence"]["desc"] == "Confidence score"

    def test_signature_mixed_desc_and_description(self):
        """Test Signature with mixed desc= and description= parameters."""

        class TestSignature(Signature):
            input1: str = InputField(desc="Input 1")  # Old style
            input2: str = InputField(description="Input 2")  # New style
            output1: str = OutputField(desc="Output 1")  # Old style
            output2: str = OutputField(description="Output 2")  # New style

        sig = TestSignature()

        # Both styles should work
        assert sig.input_fields["input1"]["desc"] == "Input 1"
        assert sig.input_fields["input2"]["desc"] == "Input 2"
        assert sig.output_fields["output1"]["desc"] == "Output 1"
        assert sig.output_fields["output2"]["desc"] == "Output 2"


class TestMessageFormattingWithDescription:
    """Test that descriptions are used in message formatting."""

    def test_message_formatting_uses_description(self):
        """Test _create_messages_from_inputs uses description correctly."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy

        # Create signature with description parameter
        class QASignature(Signature):
            question: str = InputField(description="User question")
            context: str = InputField(description="Background context")
            answer: str = OutputField(description="Answer to question")

        # Create mock agent
        config = BaseAgentConfig(llm_provider="mock", model="mock")
        agent = BaseAgent(config=config, signature=QASignature())

        # Create strategy and format messages
        strategy = AsyncSingleShotStrategy()
        inputs = {"question": "What is AI?", "context": "Machine learning topic"}

        messages = strategy._create_messages_from_inputs(agent, inputs)

        # Check message content
        assert len(messages) == 1
        content = messages[0]["content"]

        # Descriptions should be in the message
        assert "User question: What is AI?" in content
        assert "Background context: Machine learning topic" in content

        # Should NOT have empty labels like ": What is AI?"
        assert not content.startswith(":")
        assert ": :" not in content  # No empty descriptions


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_existing_code_with_desc_still_works(self):
        """Test that existing code using desc= continues to work."""

        class LegacySignature(Signature):
            """Example from existing codebase using desc="""

            input_text: str = InputField(desc="Input text")
            output_text: str = OutputField(desc="Output text")

        sig = LegacySignature()

        assert sig.input_fields["input_text"]["desc"] == "Input text"
        assert sig.output_fields["output_text"]["desc"] == "Output text"

    def test_documentation_examples_now_work(self):
        """Test that examples from documentation now work."""

        class DocumentationSignature(Signature):
            """Example from official Kaizen documentation"""

            question: str = InputField(description="User question")
            answer: str = OutputField(description="Answer to question")

        sig = DocumentationSignature()

        assert sig.input_fields["question"]["desc"] == "User question"
        assert sig.output_fields["answer"]["desc"] == "Answer to question"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
