"""Integration tests for Google Gemini JSON mode (structured output).

These tests verify the fix for the critical Kaizen v0.7.2 issue where
GoogleGeminiProvider was not properly handling response_format translation.

ISSUE: When using BaseAgent.run() with Google/Gemini provider, the LLM returned
markdown-formatted text instead of valid JSON, causing json.JSONDecodeError.

ROOT CAUSE: GoogleGeminiProvider.chat() did not translate OpenAI-style
response_format to Google's response_mime_type and response_json_schema parameters.

FIX: Added response_format translation in both chat() and chat_async() methods.

Run with:
    PYTHONPATH=src pytest tests/integration/nodes/ai/test_google_json_mode.py -v -s
"""

import json
import os

import pytest

# Skip entire module if no Google API key
pytestmark = pytest.mark.skipif(
    not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")),
    reason="GOOGLE_API_KEY or GEMINI_API_KEY not set",
)


class TestGoogleGeminiJSONMode:
    """Test JSON mode (structured output) for Google Gemini provider."""

    def test_json_object_mode(self):
        """Should return valid JSON with json_object response_format."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()
        assert provider.is_available(), "Provider should be available"

        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that outputs JSON.",
            },
            {
                "role": "user",
                "content": "Extract the name and age from: 'John is 25 years old'. Return as JSON with 'name' and 'age' fields.",
            },
        ]

        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={
                "temperature": 0,
                "max_tokens": 100,
                "response_format": {"type": "json_object"},
            },
        )

        # Verify response is valid JSON
        content = response["content"]
        assert content is not None
        assert len(content) > 0

        # Parse as JSON
        parsed = json.loads(content)
        assert "name" in parsed or "Name" in parsed
        # Value should contain "John"
        name_value = parsed.get("name") or parsed.get("Name")
        assert "John" in str(name_value)

    def test_json_schema_mode(self):
        """Should return valid JSON adhering to schema with json_schema response_format."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [
            {
                "role": "user",
                "content": "Extract info from: 'Alice is a software engineer who loves Python'. Return the person's details.",
            },
        ]

        # Define a JSON schema for the response
        response_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The person's name"},
                "occupation": {
                    "type": "string",
                    "description": "The person's job title",
                },
                "interests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of interests or skills",
                },
            },
            "required": ["name", "occupation"],
        }

        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={
                "temperature": 0,
                "max_tokens": 200,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "person_info",
                        "strict": True,
                        "schema": response_schema,
                    },
                },
            },
        )

        # Verify response is valid JSON
        content = response["content"]
        assert content is not None

        # Parse as JSON
        parsed = json.loads(content)

        # Verify schema compliance
        assert "name" in parsed
        assert "occupation" in parsed
        assert "Alice" in parsed["name"]
        assert "engineer" in parsed["occupation"].lower()

    def test_json_mode_prevents_markdown(self):
        """Should NOT return markdown when JSON mode is enabled."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [
            {
                "role": "user",
                "content": "List 3 programming languages with their main use case. Be concise.",
            },
        ]

        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={
                "temperature": 0,
                "max_tokens": 300,
                "response_format": {"type": "json_object"},
            },
        )

        content = response["content"]

        # Should NOT contain markdown formatting
        assert "**" not in content, "Response should not contain markdown bold"
        assert "```" not in content, "Response should not contain code blocks"
        assert content.strip().startswith("{") or content.strip().startswith(
            "["
        ), "Response should start with JSON object or array"

        # Should be valid JSON (array or object both acceptable)
        parsed = json.loads(content)
        assert isinstance(parsed, (dict, list))


class TestGoogleGeminiJSONModeAsync:
    """Async tests for JSON mode."""

    @pytest.mark.asyncio
    async def test_json_object_mode_async(self):
        """Should return valid JSON with json_object response_format (async)."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [
            {
                "role": "user",
                "content": "Return a JSON object with fields 'status' and 'message'. Status should be 'ok'.",
            },
        ]

        response = await provider.chat_async(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={
                "temperature": 0,
                "max_tokens": 100,
                "response_format": {"type": "json_object"},
            },
        )

        content = response["content"]
        parsed = json.loads(content)

        assert "status" in parsed
        assert parsed["status"].lower() == "ok"

    @pytest.mark.asyncio
    async def test_json_schema_mode_async(self):
        """Should return valid JSON adhering to schema (async)."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [
            {
                "role": "user",
                "content": "Generate a simple todo item about buying groceries.",
            },
        ]

        response_schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "completed": {"type": "boolean"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["title", "completed", "priority"],
        }

        response = await provider.chat_async(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={
                "temperature": 0,
                "max_tokens": 150,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "todo_item",
                        "strict": True,
                        "schema": response_schema,
                    },
                },
            },
        )

        content = response["content"]
        parsed = json.loads(content)

        # Verify all required fields present
        assert "title" in parsed
        assert "completed" in parsed
        assert "priority" in parsed
        assert isinstance(parsed["completed"], bool)
        assert parsed["priority"] in ["low", "medium", "high"]


class TestAdditionalPropertiesFalseRegression:
    """Regression tests for additionalProperties: false bug.

    When create_structured_output_config(strict=True) generates schemas, it adds
    "additionalProperties": false. The old code passed these via response_schema,
    which caused 400 INVALID_ARGUMENT from the Gemini API because response_schema
    doesn't support additionalProperties. The fix uses response_json_schema instead.
    """

    def test_json_schema_with_additional_properties_false(self):
        """Schema with additionalProperties: false must not cause 400 error."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [
            {
                "role": "user",
                "content": "Extract info from: 'Bob is 30 and lives in NYC'.",
            },
        ]

        # This is the exact pattern create_structured_output_config(strict=True) produces
        response_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "city": {"type": "string"},
            },
            "required": ["name", "age", "city"],
            "additionalProperties": False,
        }

        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={
                "temperature": 0,
                "max_tokens": 150,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "person_info",
                        "strict": True,
                        "schema": response_schema,
                    },
                },
            },
        )

        content = response["content"]
        parsed = json.loads(content)

        assert parsed["name"] == "Bob"
        assert parsed["age"] == 30
        assert "NYC" in parsed["city"] or "New York" in parsed["city"]

    @pytest.mark.asyncio
    async def test_json_schema_with_additional_properties_false_async(self):
        """Async: schema with additionalProperties: false must not cause 400 error."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [
            {
                "role": "user",
                "content": "Extract info from: 'Carol is a teacher in London'.",
            },
        ]

        response_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "occupation": {"type": "string"},
                "city": {"type": "string"},
            },
            "required": ["name", "occupation", "city"],
            "additionalProperties": False,
        }

        response = await provider.chat_async(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={
                "temperature": 0,
                "max_tokens": 150,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "person_info",
                        "strict": True,
                        "schema": response_schema,
                    },
                },
            },
        )

        content = response["content"]
        parsed = json.loads(content)

        assert parsed["name"] == "Carol"
        assert "teacher" in parsed["occupation"].lower()
        assert "London" in parsed["city"] or "london" in parsed["city"].lower()


class TestMediScribeScenario:
    """Test scenario from the original MediScribe issue report."""

    def test_medical_soap_extraction(self):
        """Reproduce the MediScribe SOAP note extraction scenario."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        # Simulated patient transcript
        transcript = """
        Patient: I've been having this headache for about 3 days now.
        It's mostly in the front of my head, and it gets worse when I look at screens.
        I've also been feeling really tired and my eyes are sensitive to light.
        """

        messages = [
            {
                "role": "system",
                "content": "You are a medical assistant. Extract subjective findings from patient transcripts.",
            },
            {
                "role": "user",
                "content": f"Extract subjective findings from this transcript:\n{transcript}",
            },
        ]

        # Schema matching SubjectiveAgent output fields
        response_schema = {
            "type": "object",
            "properties": {
                "chief_complaint": {
                    "type": "string",
                    "description": "Main complaint in brief",
                },
                "symptoms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of reported symptoms",
                },
                "duration": {
                    "type": "string",
                    "description": "How long symptoms have been present",
                },
            },
            "required": ["chief_complaint", "symptoms"],
        }

        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={
                "temperature": 0,
                "max_tokens": 300,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "subjective_findings",
                        "strict": True,
                        "schema": response_schema,
                    },
                },
            },
        )

        # This should NOT raise json.JSONDecodeError anymore
        content = response["content"]
        parsed = json.loads(content)

        # Verify structure
        assert "chief_complaint" in parsed
        assert "symptoms" in parsed
        assert isinstance(parsed["symptoms"], list)
        assert len(parsed["symptoms"]) > 0

        # Verify content
        assert "headache" in parsed["chief_complaint"].lower() or any(
            "headache" in s.lower() for s in parsed["symptoms"]
        )

        print(f"\n=== MediScribe Test Result ===")
        print(f"Chief Complaint: {parsed['chief_complaint']}")
        print(f"Symptoms: {parsed['symptoms']}")
        if "duration" in parsed:
            print(f"Duration: {parsed['duration']}")
        print("=== JSON parsing successful! ===\n")
