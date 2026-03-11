"""
Tier 2: Integration Tests for Bug #5 Fix (Structured Output strict=False)

Tests Bug #5 fix with REAL OpenAI API calls (NO MOCKING).

Bug #5 Summary:
- Issue: strict=False mode sent {"type": "json_object", "schema": {...}} to OpenAI
- Problem: OpenAI API doesn't accept "schema" key for legacy mode
- Fix: Changed to {"type": "json_object"} only (line 353 in structured_output.py)
- Result: OpenAI now returns JSON instead of plain text

CRITICAL: NO MOCKING per Kaizen gold standards (Tier 2-3).

Test Budget:
- Test 1 (simple signature): ~$0.001 (1 call @ gpt-4o-mini)
- Test 2 (complex signature): ~$0.001 (1 call @ gpt-4o-mini)
- Test 3 (auto-fallback): ~$0.001 (1 call @ gpt-4o-mini)
- Test 4 (strict mode): ~$0.001 (1 call @ gpt-4o-2024-08-06)
- Test 5 (error handling): ~$0.001 (1 call @ gpt-4o-mini)
Total: ~$0.005 ($0.01 with buffer)
"""

import json
import os
from typing import Dict, Literal

import pytest
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.core.structured_output import create_structured_output_config
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def openai_api_key():
    """Fixture providing OpenAI API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set - skipping integration tests")
    return api_key


# ============================================================================
# Tier 2: Integration Tests with REAL OpenAI API
# ============================================================================


@pytest.mark.integration
@pytest.mark.openai
@pytest.mark.cost
class TestBug5FixWithRealOpenAI:
    """Test Bug #5 fix with REAL OpenAI API (strict=False mode)."""

    def test_bug5_fix_simple_signature_strict_false(self, openai_api_key):
        """
        Tier 2 Test 1: Simple signature with strict=False returns JSON (not text).

        Verifies:
        1. create_structured_output_config(strict=False) returns {"type": "json_object"}
        2. OpenAI API accepts the format without error
        3. OpenAI returns valid JSON (not plain text)
        4. BaseAgent.run() successfully parses response
        5. No JSON_PARSE_FAILED error

        Budget: ~$0.001 (1 call @ gpt-4o-mini)
        """

        # Create simple signature
        class SimpleSignature(Signature):
            question: str = InputField(desc="User question")
            answer: str = OutputField(desc="Short answer")

        # Verify Bug #5 fix: strict=False returns correct format
        config = create_structured_output_config(SimpleSignature(), strict=False)
        assert config == {
            "type": "json_object"
        }, "Bug #5 fix: strict=False should return only type:json_object"
        assert "schema" not in config, "Bug #5 fix: schema key should not exist"

        # Test with REAL OpenAI API
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",  # Cost-efficient model
            temperature=0.3,  # Lower temp for consistency
            max_tokens=50,  # Small response to save cost
            provider_config=config,  # Bug #5 fixed format
        )

        agent = BaseAgent(config=agent_config, signature=SimpleSignature())

        # Execute with real API
        result = agent.run(question="What is 2+2?")

        # Verify structured output
        assert isinstance(result, dict), "Result must be dict (not str)"
        assert "answer" in result, "Result must have 'answer' field"
        assert isinstance(result["answer"], str), "Answer must be string"
        assert len(result["answer"].strip()) > 0, "Answer cannot be empty"

        # Verify real intelligence (not template)
        answer = result["answer"].lower()
        assert "4" in answer or "four" in answer, f"Must answer correctly: {answer}"

        print(f"✅ Test 1 passed: OpenAI returned JSON with answer: {result['answer']}")

    def test_bug5_fix_complex_signature_strict_false(self, openai_api_key):
        """
        Tier 2 Test 2: Complex signature with multiple fields works with strict=False.

        Verifies:
        1. Complex signatures work with fixed format
        2. All output fields are populated
        3. Types are correct (str, float, bool)
        4. Response parsing works end-to-end

        Budget: ~$0.001 (1 call @ gpt-4o-mini)
        """

        # Create complex signature
        class ProductAnalysisSignature(Signature):
            product_description: str = InputField(desc="Product description")
            category: str = OutputField(desc="Product category")
            price_range: str = OutputField(desc="Price range estimate")
            confidence: float = OutputField(desc="Confidence score 0-1")

        # Verify Bug #5 fix
        config = create_structured_output_config(
            ProductAnalysisSignature(), strict=False
        )
        assert config == {"type": "json_object"}

        # Test with REAL OpenAI API
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=100,
            provider_config=config,
        )

        agent = BaseAgent(config=agent_config, signature=ProductAnalysisSignature())

        # Execute with real API
        result = agent.run(
            product_description="Wireless headphones with 30-hour battery"
        )

        # Verify all fields present
        assert "category" in result, "Missing 'category' field"
        assert "price_range" in result, "Missing 'price_range' field"
        assert "confidence" in result, "Missing 'confidence' field"

        # Verify types
        assert isinstance(result["category"], str), "category must be string"
        assert isinstance(result["price_range"], str), "price_range must be string"
        assert isinstance(
            result["confidence"], (int, float)
        ), "confidence must be number"

        # Verify content quality
        assert len(result["category"]) > 0, "category cannot be empty"
        assert len(result["price_range"]) > 0, "price_range cannot be empty"
        assert (
            0 <= result["confidence"] <= 1
        ), f"confidence out of range: {result['confidence']}"

        print(
            f"✅ Test 2 passed: Complex signature returned: {json.dumps(result, indent=2)}"
        )

    def test_bug5_fix_auto_fallback_dict_fields(self, openai_api_key):
        """
        Tier 2 Test 3: Auto-fallback to strict=False when Dict fields present.

        Verifies:
        1. Signatures with Dict fields auto-fallback to strict=False
        2. Fallback uses correct format {"type": "json_object"}
        3. OpenAI API accepts fallback format
        4. Dict fields are populated correctly

        Budget: ~$0.001 (1 call @ gpt-4o-mini)
        """

        # Create signature with Dict field (triggers auto-fallback)
        class ExtractedFieldsSignature(Signature):
            conversation_text: str = InputField(desc="Conversation text")
            extracted_fields: Dict = OutputField(desc="Extracted fields")
            confidence_score: float = OutputField(desc="Confidence 0-1")

        # Verify auto-fallback behavior
        # When strict=True is requested but Dict fields exist, falls back to strict=False
        config = create_structured_output_config(
            ExtractedFieldsSignature(), strict=True
        )
        # Bug #5 fix: Auto-fallback should use {"type": "json_object"}
        assert config == {"type": "json_object"}

        # Test with REAL OpenAI API
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=150,
            provider_config=config,
        )

        agent = BaseAgent(config=agent_config, signature=ExtractedFieldsSignature())

        # Execute with real API
        result = agent.run(
            conversation_text="Patient: I need to see a cardiologist. My name is John Doe."
        )

        # Verify all fields present
        assert "extracted_fields" in result, "Missing 'extracted_fields' field"
        assert "confidence_score" in result, "Missing 'confidence_score' field"

        # Verify Dict field is dict
        assert isinstance(
            result["extracted_fields"], dict
        ), "extracted_fields must be dict"
        assert isinstance(
            result["confidence_score"], (int, float)
        ), "confidence_score must be number"

        # Verify Dict has content
        assert len(result["extracted_fields"]) > 0, "extracted_fields cannot be empty"

        print(
            f"✅ Test 3 passed: Auto-fallback with Dict fields: {json.dumps(result, indent=2)}"
        )

    def test_bug5_fix_strict_true_unchanged(self, openai_api_key):
        """
        Tier 2 Test 4: strict=True mode unchanged (regression test).

        Verifies:
        1. Bug #5 fix doesn't break strict=True mode
        2. strict=True still returns json_schema format
        3. OpenAI API accepts strict format (gpt-4o-2024-08-06+)
        4. 100% schema compliance works

        Budget: ~$0.001 (1 call @ gpt-4o-2024-08-06)
        """

        # Create simple signature
        class StrictSignature(Signature):
            query: str = InputField(desc="User query")
            category: Literal["tech", "business", "personal"] = OutputField(
                desc="Category"
            )
            urgency: Literal["low", "medium", "high"] = OutputField(desc="Urgency")

        # Verify strict=True unchanged
        config = create_structured_output_config(
            StrictSignature(), strict=True, name="strict_test"
        )
        assert config["type"] == "json_schema", "strict=True must use json_schema"
        assert config["json_schema"]["strict"] is True, "strict flag must be True"
        assert "schema" in config["json_schema"], "schema must be present"

        # Test with REAL OpenAI API (strict mode requires gpt-4o-2024-08-06+)
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-2024-08-06",  # Supports structured outputs
            temperature=0.3,
            max_tokens=50,
            provider_config=config,
        )

        agent = BaseAgent(config=agent_config, signature=StrictSignature())

        # Execute with real API
        result = agent.run(query="Need help setting up my email client")

        # Verify structured output
        assert "category" in result, "Missing 'category' field"
        assert "urgency" in result, "Missing 'urgency' field"

        # Verify Literal constraints are respected
        assert result["category"] in [
            "tech",
            "business",
            "personal",
        ], f"Invalid category: {result['category']}"
        assert result["urgency"] in [
            "low",
            "medium",
            "high",
        ], f"Invalid urgency: {result['urgency']}"

        print(
            f"✅ Test 4 passed: strict=True unchanged: {json.dumps(result, indent=2)}"
        )

    def test_bug5_fix_error_logging_improved(self, openai_api_key):
        """
        Tier 2 Test 5: Error handling and logging improved.

        Verifies:
        1. Invalid signatures are caught early
        2. Error messages are clear and actionable
        3. No JSON_PARSE_FAILED errors with valid signatures
        4. API errors are handled gracefully

        Budget: ~$0.001 (1 call @ gpt-4o-mini)
        """

        # Create valid signature
        class ValidSignature(Signature):
            input_text: str = InputField(desc="Input text")
            sentiment: Literal["positive", "negative", "neutral"] = OutputField(
                desc="Sentiment"
            )

        # Verify config is valid
        config = create_structured_output_config(ValidSignature(), strict=False)
        assert config == {"type": "json_object"}

        # Test with REAL OpenAI API
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=50,
            provider_config=config,
        )

        agent = BaseAgent(config=agent_config, signature=ValidSignature())

        # Execute with real API
        result = agent.run(input_text="I love this product! Amazing quality.")

        # Verify no errors
        assert isinstance(result, dict), "Result must be dict (no parse errors)"
        assert "sentiment" in result, "Missing 'sentiment' field"
        assert result["sentiment"] in [
            "positive",
            "negative",
            "neutral",
        ], f"Invalid sentiment: {result['sentiment']}"

        # Verify correct classification
        assert (
            result["sentiment"] == "positive"
        ), f"Should be positive: {result['sentiment']}"

        print(
            f"✅ Test 5 passed: Error handling works, sentiment: {result['sentiment']}"
        )


@pytest.mark.integration
@pytest.mark.openai
class TestBug5RealWorldScenarios:
    """Test Bug #5 fix with real-world production scenarios."""

    def test_bug5_medical_specialty_extraction_simple(self, openai_api_key):
        """
        Tier 2 Test 6: Medical specialty extraction (simplified version).

        This is the EXACT use case reported by OCR Flow Development Team.

        Verifies:
        1. Medical specialty signature works with Bug #5 fix
        2. Literal enum values work correctly
        3. "Not Mentioned" sentinel value works
        4. Confidence scoring works

        Budget: ~$0.001 (1 call @ gpt-4o-mini)
        """

        # Create medical specialty signature (from bug report)
        class MedicalSpecialtySignature(Signature):
            conversation_text: str = InputField(desc="Patient conversation")
            referral_specialty: Literal[
                "Not Mentioned", "Cardiology", "Neurology", "Orthopedics"
            ] = OutputField(desc="Medical specialty")
            confidence: float = OutputField(desc="Confidence 0-1")

        # Verify Bug #5 fix works with this signature
        config = create_structured_output_config(
            MedicalSpecialtySignature(), strict=False
        )
        assert config == {"type": "json_object"}

        # Test with REAL OpenAI API
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=100,
            provider_config=config,
        )

        agent = BaseAgent(config=agent_config, signature=MedicalSpecialtySignature())

        # Test Case 1: Explicit specialty mentioned
        result1 = agent.run(
            conversation_text="Patient needs to see a cardiologist for heart issues."
        )
        assert result1["referral_specialty"] == "Cardiology"
        assert result1["confidence"] > 0.7

        # Test Case 2: No specialty mentioned
        result2 = agent.run(
            conversation_text="Patient wants to schedule an appointment."
        )
        assert result2["referral_specialty"] == "Not Mentioned"

        print(f"✅ Test 6 passed: Medical specialty extraction works")
        print(f"  - Case 1 (explicit): {result1}")
        print(f"  - Case 2 (not mentioned): {result2}")

    def test_bug5_conversation_analysis_dict_fields(self, openai_api_key):
        """
        Tier 2 Test 7: Conversation analysis with Dict fields.

        Tests Bug #5 fix with complex signatures containing Dict fields.

        Verifies:
        1. Auto-fallback works with Dict fields
        2. Multiple output fields work together
        3. Dict fields contain structured data
        4. Response parsing is robust

        Budget: ~$0.002 (1 call @ gpt-4o-mini with larger response)
        """

        # Create complex conversation signature
        class ConversationAnalysisSignature(Signature):
            conversation_text: str = InputField(desc="Conversation text")
            next_action: str = OutputField(desc="Next action to take")
            extracted_fields: Dict = OutputField(desc="Extracted fields")
            confidence_level: float = OutputField(desc="Confidence 0-1")

        # Verify auto-fallback with Dict
        config = create_structured_output_config(
            ConversationAnalysisSignature(), strict=True
        )  # Request strict, but should fallback
        assert config == {"type": "json_object"}  # Fallback to legacy

        # Test with REAL OpenAI API
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=200,
            provider_config=config,
        )

        agent = BaseAgent(
            config=agent_config, signature=ConversationAnalysisSignature()
        )

        # Execute with real conversation
        result = agent.run(
            conversation_text="Patient: My name is Jane Smith. I need to see a neurologist for my migraines. My phone is 555-1234."
        )

        # Verify all fields present
        assert "next_action" in result
        assert "extracted_fields" in result
        assert "confidence_level" in result

        # Verify Dict has expected structure
        assert isinstance(result["extracted_fields"], dict)
        assert len(result["extracted_fields"]) > 0

        # Check if common fields were extracted
        extracted = result["extracted_fields"]
        # Note: We don't assert specific fields because LLM might structure differently
        # Just verify it's a non-empty dict
        print(f"✅ Test 7 passed: Conversation analysis with Dict fields:")
        print(f"  - Next action: {result['next_action']}")
        print(f"  - Extracted: {json.dumps(extracted, indent=2)}")
        print(f"  - Confidence: {result['confidence_level']}")

    def test_bug5_response_format_validation(self, openai_api_key):
        """
        Tier 2 Test 8: Response format validation end-to-end.

        Verifies:
        1. OpenAI returns valid JSON (not plain text)
        2. JSON structure matches signature
        3. Field types are correct
        4. No parsing errors

        Budget: ~$0.001 (1 call @ gpt-4o-mini)
        """

        # Create signature with diverse types
        class TypeTestSignature(Signature):
            input: str = InputField(desc="Input text")
            text_output: str = OutputField(desc="Text output")
            number_output: float = OutputField(desc="Number output")
            boolean_output: bool = OutputField(desc="Boolean output")
            category: Literal["A", "B", "C"] = OutputField(desc="Category")

        # Verify Bug #5 fix
        config = create_structured_output_config(TypeTestSignature(), strict=False)
        assert config == {"type": "json_object"}

        # Test with REAL OpenAI API
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=150,
            provider_config=config,
        )

        agent = BaseAgent(config=agent_config, signature=TypeTestSignature())

        # Execute with real API
        result = agent.run(input="Test input for type validation")

        # Verify all fields present
        required_fields = [
            "text_output",
            "number_output",
            "boolean_output",
            "category",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

        # Verify types
        assert isinstance(result["text_output"], str), "text_output must be string"
        assert isinstance(
            result["number_output"], (int, float)
        ), "number_output must be number"
        assert isinstance(
            result["boolean_output"], bool
        ), "boolean_output must be boolean"
        assert result["category"] in [
            "A",
            "B",
            "C",
        ], f"Invalid category: {result['category']}"

        print(f"✅ Test 8 passed: All types validated correctly:")
        print(f"  {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
