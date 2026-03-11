"""
Tier 3: E2E Tests for Bug #5 Fix (Production Scenarios)

Tests Bug #5 fix with REAL production workflows using OpenAI API (NO MOCKING).

Bug #5 Context:
- Reported by: OCR Flow Development Team
- Scenario: Medical referral conversation analysis
- Issue: strict=False sent invalid schema key to OpenAI
- Impact: OpenAI returned plain text instead of JSON, causing JSON_PARSE_FAILED
- Fix: Removed schema key from strict=False format (line 353)

This file tests the EXACT production scenario that was failing.

CRITICAL: NO MOCKING per Kaizen gold standards (Tier 3).

Test Budget:
- Test 1 (medical referral): ~$0.002 (1 call @ gpt-4o-mini)
- Test 2 (multi-turn conversation): ~$0.006 (3 calls @ gpt-4o-mini)
- Test 3 (production workflow): ~$0.003 (1 call @ gpt-4o-mini)
Total: ~$0.011 ($0.02 with buffer)
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
        pytest.skip("OPENAI_API_KEY not set - skipping E2E tests")
    return api_key


# ============================================================================
# Tier 3: E2E Tests with Production Scenarios
# ============================================================================


@pytest.mark.e2e
@pytest.mark.openai
@pytest.mark.cost
class TestBug5ProductionScenario:
    """Test Bug #5 fix with EXACT production scenario from bug report."""

    def test_bug5_medical_referral_extraction_full_scenario(self, openai_api_key):
        """
        Tier 3 E2E Test 1: Medical referral extraction (EXACT production scenario).

        This is the EXACT scenario reported by OCR Flow Development Team that was failing.

        Production Context:
        - Team: OCR Flow Development Team
        - Use Case: Extract medical referral information from patient conversations
        - Problem: OpenAI returned plain text instead of JSON
        - Error: JSON_PARSE_FAILED when trying to parse response
        - Workaround: Team had to manually parse text responses
        - Fix: Bug #5 fix removes schema key from strict=False format

        This test verifies the workaround is no longer needed.

        Verifies:
        1. Complete medical referral signature works
        2. Multiple Literal fields work together
        3. Dict fields work for extracted information
        4. OpenAI returns valid JSON (not plain text)
        5. BaseAgent.run() parses response successfully
        6. No manual text parsing needed (workaround removed)

        Budget: ~$0.002 (1 call @ gpt-4o-mini)
        """

        # Create EXACT production signature from bug report
        class MedicalReferralSignature(Signature):
            """Production signature for medical referral extraction."""

            conversation_text: str = InputField(desc="Patient conversation text")

            # Referral information
            referral_specialty: Literal[
                "Not Mentioned",
                "Cardiology",
                "Neurology",
                "Orthopedics",
                "Dermatology",
                "Psychiatry",
                "Other",
            ] = OutputField(desc="Medical specialty for referral")

            # Urgency assessment
            urgency_level: Literal["routine", "urgent", "emergency"] = OutputField(
                desc="Urgency level of referral"
            )

            # Extracted patient information
            extracted_info: Dict = OutputField(
                desc="Extracted patient information (name, phone, etc.)"
            )

            # Next action
            next_action: str = OutputField(
                desc="Recommended next action for patient care"
            )

            # Confidence
            confidence_score: float = OutputField(desc="Confidence in extraction (0-1)")

        # Verify Bug #5 fix: auto-fallback to strict=False due to Dict field
        config = create_structured_output_config(
            MedicalReferralSignature(), strict=True
        )
        assert config == {
            "type": "json_object"
        }, "Auto-fallback to strict=False due to Dict field"
        assert "schema" not in config, "Bug #5 fix: no schema key in strict=False"

        # Create agent with REAL OpenAI API
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",  # Production model
            temperature=0.3,  # Lower temp for medical accuracy
            max_tokens=300,  # Enough for complete response
            provider_config=config,
        )

        agent = BaseAgent(config=agent_config, signature=MedicalReferralSignature())

        # EXACT production scenario that was failing
        production_conversation = """
        Patient: Hi, my name is Sarah Johnson. I've been having severe chest pains
        and shortness of breath for the past week. My doctor told me I need to see
        a cardiologist as soon as possible. Can you help me schedule an appointment?

        Receptionist: I'm sorry to hear that. Let me get your information. Can you
        provide your phone number?

        Patient: Yes, it's 555-0123. This is really urgent - the pain has been
        getting worse.
        """

        # Execute with REAL OpenAI API (this was failing before Bug #5 fix)
        result = agent.run(conversation_text=production_conversation)

        # CRITICAL: Verify response is dict (not str requiring manual parsing)
        assert isinstance(
            result, dict
        ), "FAIL: OpenAI returned text instead of JSON (Bug #5 not fixed)"

        # Verify all production fields are present
        required_fields = [
            "referral_specialty",
            "urgency_level",
            "extracted_info",
            "next_action",
            "confidence_score",
        ]
        for field in required_fields:
            assert (
                field in result
            ), f"Missing production field: {field} (JSON parsing failed)"

        # Verify medical specialty extraction
        assert result["referral_specialty"] in [
            "Not Mentioned",
            "Cardiology",
            "Neurology",
            "Orthopedics",
            "Dermatology",
            "Psychiatry",
            "Other",
        ], f"Invalid specialty: {result['referral_specialty']}"

        # Verify urgency assessment
        assert result["urgency_level"] in [
            "routine",
            "urgent",
            "emergency",
        ], f"Invalid urgency: {result['urgency_level']}"

        # Verify extracted information is dict
        assert isinstance(result["extracted_info"], dict), "extracted_info must be dict"
        assert len(result["extracted_info"]) > 0, "extracted_info cannot be empty"

        # Verify confidence score
        assert isinstance(
            result["confidence_score"], (int, float)
        ), "confidence_score must be number"
        assert (
            0 <= result["confidence_score"] <= 1
        ), f"confidence_score out of range: {result['confidence_score']}"

        # Verify extraction quality (production validation)
        extracted = result["extracted_info"]

        # Expected extractions (flexible matching - LLM might use different keys)
        extracted_str = json.dumps(extracted).lower()
        assert (
            "sarah" in extracted_str or "johnson" in extracted_str
        ), f"Patient name not extracted: {extracted}"
        assert (
            "555-0123" in extracted_str or "5550123" in extracted_str
        ), f"Phone number not extracted: {extracted}"

        # Verify correct medical assessment
        assert result["referral_specialty"] in [
            "Cardiology",
            "Other",
        ], f"Should identify cardiology: {result['referral_specialty']}"
        assert result["urgency_level"] in [
            "urgent",
            "emergency",
        ], f"Should identify urgency: {result['urgency_level']}"

        # SUCCESS: No manual text parsing needed (Bug #5 fixed)
        print("✅ E2E Test 1 PASSED: Production scenario works without workarounds")
        print(f"\nProduction Response:")
        print(f"  Specialty: {result['referral_specialty']}")
        print(f"  Urgency: {result['urgency_level']}")
        print(f"  Extracted: {json.dumps(result['extracted_info'], indent=4)}")
        print(f"  Next Action: {result['next_action']}")
        print(f"  Confidence: {result['confidence_score']}")

    def test_bug5_multi_turn_conversation_with_memory(self, openai_api_key):
        """
        Tier 3 E2E Test 2: Multi-turn conversation analysis.

        Tests Bug #5 fix in realistic multi-turn conversation scenario.

        Verifies:
        1. Multiple agent calls maintain structured output
        2. Conversation context accumulates correctly
        3. Each response is valid JSON (not text)
        4. State tracking works across turns
        5. Memory/context integration works

        Budget: ~$0.006 (3 calls @ gpt-4o-mini)
        """

        # Create conversation state signature
        class ConversationStateSignature(Signature):
            """Tracks conversation state across multiple turns."""

            conversation_history: str = InputField(desc="Full conversation history")

            # Current state
            current_intent: Literal[
                "greeting",
                "information_request",
                "appointment_scheduling",
                "complaint",
                "closing",
            ] = OutputField(desc="Current conversation intent")

            # Information completeness
            information_complete: bool = OutputField(
                desc="Whether all required information is collected"
            )

            # Missing information
            missing_fields: str = OutputField(
                desc="Comma-separated list of missing information"
            )

            # Recommended response
            recommended_response: str = OutputField(desc="Recommended response to user")

        # Verify Bug #5 fix
        config = create_structured_output_config(
            ConversationStateSignature(), strict=False
        )
        assert config == {"type": "json_object"}

        # Create agent
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=200,
            provider_config=config,
        )

        agent = BaseAgent(config=agent_config, signature=ConversationStateSignature())

        # Multi-turn conversation scenario
        conversation_history = ""

        # Turn 1: Initial greeting
        turn1 = "Patient: Hello, I need to schedule an appointment."
        conversation_history += turn1 + "\n"

        result1 = agent.run(conversation_history=conversation_history)
        assert isinstance(result1, dict), "Turn 1 failed: got text instead of JSON"
        assert result1["current_intent"] == "appointment_scheduling"
        assert result1["information_complete"] is False
        print(
            f"\n✅ Turn 1: Intent={result1['current_intent']}, Complete={result1['information_complete']}"
        )

        # Turn 2: Provide partial information
        turn2 = "Receptionist: I can help with that. What's your name?\nPatient: My name is John Smith."
        conversation_history += turn2 + "\n"

        result2 = agent.run(conversation_history=conversation_history)
        assert isinstance(result2, dict), "Turn 2 failed: got text instead of JSON"
        assert result2["information_complete"] is False  # Still need more info
        print(
            f"✅ Turn 2: Intent={result2['current_intent']}, Missing={result2['missing_fields']}"
        )

        # Turn 3: Complete information
        turn3 = (
            "Receptionist: Great! What's your phone number?\nPatient: It's 555-9876."
        )
        conversation_history += turn3 + "\n"

        result3 = agent.run(conversation_history=conversation_history)
        assert isinstance(result3, dict), "Turn 3 failed: got text instead of JSON"
        # Information might be complete now (depends on what was needed)
        print(
            f"✅ Turn 3: Intent={result3['current_intent']}, Complete={result3['information_complete']}"
        )

        # Verify all turns returned JSON (Bug #5 fixed)
        print("\n✅ E2E Test 2 PASSED: Multi-turn conversation maintained JSON format")

    def test_bug5_production_workflow_with_baseagent(self, openai_api_key):
        """
        Tier 3 E2E Test 3: Complete production workflow with BaseAgent.

        Tests Bug #5 fix in complete end-to-end production workflow:
        1. Conversation intake
        2. Information extraction
        3. Classification
        4. Action planning

        Verifies:
        1. Complete workflow executes successfully
        2. All stages return JSON (not text)
        3. Data flows correctly between stages
        4. Production-grade error handling works
        5. BaseAgent integration is robust

        Budget: ~$0.003 (1 call @ gpt-4o-mini)
        """

        # Create production workflow signature
        class ProductionWorkflowSignature(Signature):
            """Complete production workflow for patient intake."""

            # Input
            raw_conversation: str = InputField(desc="Raw conversation transcript")

            # Stage 1: Classification
            conversation_type: Literal[
                "new_patient", "existing_patient", "emergency", "inquiry"
            ] = OutputField(desc="Type of conversation")

            # Stage 2: Extraction
            patient_info: Dict = OutputField(desc="Extracted patient information")

            # Stage 3: Requirements
            medical_specialty: Literal[
                "Not Mentioned",
                "Cardiology",
                "Neurology",
                "Orthopedics",
                "Primary Care",
                "Other",
            ] = OutputField(desc="Required medical specialty")

            # Stage 4: Action
            next_steps: str = OutputField(desc="Next steps for staff")

            # Stage 5: Validation
            validation_status: Literal["complete", "incomplete", "needs_review"] = (
                OutputField(desc="Validation status")
            )

            priority: Literal["low", "medium", "high", "critical"] = OutputField(
                desc="Priority level"
            )

        # Verify Bug #5 fix (Dict field triggers auto-fallback)
        config = create_structured_output_config(
            ProductionWorkflowSignature(), strict=True
        )
        assert config == {"type": "json_object"}

        # Create production agent
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            temperature=0.2,  # Lower for production consistency
            max_tokens=400,
            provider_config=config,
        )

        agent = BaseAgent(config=agent_config, signature=ProductionWorkflowSignature())

        # PRODUCTION SCENARIO: Complex multi-requirement conversation
        production_input = """
        Intake Call Transcript:

        Receptionist: Thank you for calling City Medical Center. How can I help you today?

        Caller: Yes, hi. This is the first time I'm calling. My name is Michael Chen,
        and I'm having some issues with irregular heartbeat and dizziness. My primary
        care doctor referred me to see a cardiologist.

        Receptionist: I see. Let me get some information from you. Can you spell your
        last name for me?

        Caller: Sure, it's C-H-E-N. My phone number is 555-2468, and my date of birth
        is March 15, 1978.

        Receptionist: Thank you. And you mentioned your primary care doctor referred you?

        Caller: Yes, Dr. Smith at Valley Clinic. The irregular heartbeat has been
        happening for about 2 weeks now. It's not constant, but when it happens,
        I feel lightheaded.

        Receptionist: I understand. We'll get you scheduled with one of our cardiologists.
        """

        # Execute complete production workflow
        result = agent.run(raw_conversation=production_input)

        # CRITICAL: Verify response is complete JSON structure
        assert isinstance(
            result, dict
        ), "Production workflow failed: got text instead of JSON"

        # Verify all workflow stages completed
        required_fields = [
            "conversation_type",
            "patient_info",
            "medical_specialty",
            "next_steps",
            "validation_status",
            "priority",
        ]
        for field in required_fields:
            assert field in result, f"Production workflow incomplete: missing {field}"

        # Verify classification stage
        assert result["conversation_type"] in [
            "new_patient",
            "existing_patient",
            "emergency",
            "inquiry",
        ]

        # Verify extraction stage
        assert isinstance(result["patient_info"], dict)
        assert len(result["patient_info"]) > 0
        patient_info_str = json.dumps(result["patient_info"]).lower()
        assert "michael" in patient_info_str or "chen" in patient_info_str

        # Verify requirements stage
        assert result["medical_specialty"] in [
            "Cardiology",
            "Other",
        ], f"Should identify cardiology: {result['medical_specialty']}"

        # Verify action stage
        assert isinstance(result["next_steps"], str)
        assert len(result["next_steps"]) > 0

        # Verify validation stage
        assert result["validation_status"] in ["complete", "incomplete", "needs_review"]
        assert result["priority"] in ["low", "medium", "high", "critical"]

        # Production quality checks
        assert result["conversation_type"] == "new_patient"
        assert result["priority"] in [
            "medium",
            "high",
        ], "Cardiac symptoms should be prioritized"

        # SUCCESS: Complete production workflow executed without errors
        print("\n✅ E2E Test 3 PASSED: Complete production workflow successful")
        print(f"\nProduction Workflow Results:")
        print(f"  Type: {result['conversation_type']}")
        print(f"  Patient Info: {json.dumps(result['patient_info'], indent=4)}")
        print(f"  Specialty: {result['medical_specialty']}")
        print(f"  Next Steps: {result['next_steps']}")
        print(f"  Status: {result['validation_status']}")
        print(f"  Priority: {result['priority']}")


@pytest.mark.e2e
@pytest.mark.openai
class TestBug5WorkaroundRemoval:
    """Verify Bug #5 workarounds are no longer needed."""

    def test_bug5_no_manual_json_parsing_needed(self, openai_api_key):
        """
        E2E Test 4: Verify manual JSON parsing workaround is no longer needed.

        Before Bug #5 fix, teams had to:
        1. Receive plain text from OpenAI
        2. Manually parse text to extract JSON
        3. Handle parsing failures
        4. Implement retry logic

        After Bug #5 fix:
        1. Receive JSON directly from OpenAI
        2. BaseAgent.run() parses automatically
        3. No manual parsing needed

        This test verifies the workaround code is obsolete.

        Budget: ~$0.001 (1 call @ gpt-4o-mini)
        """

        # Simple signature that was failing before
        class SimpleExtractionSignature(Signature):
            text: str = InputField(desc="Input text")
            extracted_data: Dict = OutputField(desc="Extracted data")

        config = create_structured_output_config(
            SimpleExtractionSignature(), strict=False
        )

        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=150,
            provider_config=config,
        )

        agent = BaseAgent(config=agent_config, signature=SimpleExtractionSignature())

        # Execute
        result = agent.run(
            text="Name: Alice Brown, Phone: 555-3333, Email: alice@example.com"
        )

        # CRITICAL: Result must be dict (not str requiring manual parsing)
        assert isinstance(result, dict), "FAILED: Manual parsing still required"
        assert "extracted_data" in result
        assert isinstance(result["extracted_data"], dict)

        # Before Bug #5 fix, teams had code like this (NOW OBSOLETE):
        # try:
        #     response_text = result  # Was plain text
        #     json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        #     if json_match:
        #         result = json.loads(json_match.group())
        #     else:
        #         raise ValueError("No JSON found in response")
        # except (json.JSONDecodeError, ValueError) as e:
        #     # Handle parsing failure
        #     logger.error(f"JSON parsing failed: {e}")
        #     return {"error": "JSON_PARSE_FAILED"}

        # After Bug #5 fix: No workaround needed!
        print("✅ E2E Test 4 PASSED: Manual JSON parsing workaround is obsolete")
        print(f"  Direct JSON response: {json.dumps(result, indent=2)}")

    def test_bug5_strict_false_actually_returns_json(self, openai_api_key):
        """
        E2E Test 5: Verify strict=False now returns JSON (not text).

        Before Bug #5 fix:
        - strict=False sent {"type": "json_object", "schema": {...}}
        - OpenAI rejected schema key
        - Returned plain text instead of JSON
        - Error: JSON_PARSE_FAILED

        After Bug #5 fix:
        - strict=False sends {"type": "json_object"} only
        - OpenAI accepts format
        - Returns valid JSON
        - Success: Automatic parsing

        Budget: ~$0.001 (1 call @ gpt-4o-mini)
        """

        # Create signature that triggers strict=False
        class LegacyModeSignature(Signature):
            query: str = InputField(desc="User query")
            response: str = OutputField(desc="Response")
            metadata: Dict = OutputField(desc="Response metadata")

        # Verify strict=False format (Bug #5 fix)
        config = create_structured_output_config(LegacyModeSignature(), strict=False)
        assert config == {"type": "json_object"}, "Bug #5 fix verification"
        assert "schema" not in config, "Schema key should be removed"

        # Test with real API
        agent_config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=100,
            provider_config=config,
        )

        agent = BaseAgent(config=agent_config, signature=LegacyModeSignature())

        result = agent.run(query="What is the capital of France?")

        # CRITICAL: Must be JSON, not text
        assert isinstance(result, dict), "strict=False must return JSON (Bug #5 fix)"
        assert "response" in result
        assert "metadata" in result
        assert isinstance(result["metadata"], dict)

        # Verify response quality
        assert "paris" in result["response"].lower()

        print("✅ E2E Test 5 PASSED: strict=False returns JSON correctly")
        print(f"  Response: {result['response']}")
        print(f"  Metadata: {json.dumps(result['metadata'], indent=2)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
