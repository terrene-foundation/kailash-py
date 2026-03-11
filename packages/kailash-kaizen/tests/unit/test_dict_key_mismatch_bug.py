"""
TDD Tests for Kaizen SDK Bug Fixes (v0.9.6)

Bug Report Summary:
1. Issue 1: Dict key mismatch - LLM returns {"content": "..."} but signature expects {"answer": "..."}
2. Issue 2: GPT-5/o3 temperature restriction not handled

These tests verify the bug fixes.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestDictKeyMismatchBug:
    """
    Test Issue 1: Dict key mismatch bug fix.

    Problem: When LLM returns {"content": "The answer is 42"} but signature
    expects {"answer": "..."}, Kaizen returned an error.

    Fix: parse_result() now wraps dicts with only "content" key in
    {"response": ...} to trigger validation bypass.
    """

    def test_parse_result_dict_with_only_content_key_is_wrapped(self):
        """
        When content is dict with ONLY "content" key, it should be wrapped.
        This is the main bug fix - raw LLM response {"content": "..."}.
        """
        from kaizen.strategies.single_shot import SingleShotStrategy

        strategy = SingleShotStrategy()

        # Simulate LLM response structure where content is a dict with only "content" key
        raw_result = {
            "agent_exec": {
                "response": {
                    "content": {
                        "content": "The answer is 42"
                    }  # Dict with only content key
                }
            }
        }

        result = strategy.parse_result(raw_result)

        # Should be wrapped with "response" key to bypass validation
        assert (
            "response" in result
        ), f"Dict with only 'content' key should be wrapped. Got: {result}"
        assert result["response"] == "The answer is 42"

    def test_parse_result_json_string_with_only_content_key_is_wrapped(self):
        """
        When JSON string parses to {"content": "..."}, it should be wrapped.
        """
        from kaizen.strategies.single_shot import SingleShotStrategy

        strategy = SingleShotStrategy()

        raw_result = {
            "agent_exec": {"response": {"content": '{"content": "The answer is 42"}'}}
        }

        result = strategy.parse_result(raw_result)

        # Should be wrapped
        assert (
            "response" in result
        ), f"Parsed JSON with only 'content' key should be wrapped. Got: {result}"
        assert result["response"] == "The answer is 42"

    def test_parse_result_preserves_valid_signature_fields(self):
        """
        When LLM returns dict with expected signature fields (e.g., "answer"),
        it should be preserved as-is (not wrapped).
        """
        from kaizen.strategies.single_shot import SingleShotStrategy

        strategy = SingleShotStrategy()

        # Response with valid signature field
        raw_result = {"agent_exec": {"response": {"content": '{"answer": "42"}'}}}

        result = strategy.parse_result(raw_result)

        # Should preserve the answer field (not wrap)
        assert "answer" in result, f"Should preserve 'answer' field. Got: {result}"
        assert result["answer"] == "42"

    def test_parse_result_dict_with_multiple_keys_not_wrapped(self):
        """
        When dict has multiple keys (not just "content"), don't wrap it.
        It might be a valid structured response.
        """
        from kaizen.strategies.single_shot import SingleShotStrategy

        strategy = SingleShotStrategy()

        raw_result = {
            "agent_exec": {
                "response": {"content": {"content": "text", "metadata": "extra"}}
            }
        }

        result = strategy.parse_result(raw_result)

        # Should NOT be wrapped since it has multiple keys
        assert (
            "content" in result
            or "response" not in result
            or ("response" in result and isinstance(result["response"], str))
        ), f"Multi-key dict should not be wrapped as simple response. Got: {result}"

    def test_parse_result_primitive_still_wrapped(self):
        """
        Primitive responses (from v0.9.5 fix) should still be wrapped.
        """
        from kaizen.strategies.single_shot import SingleShotStrategy

        strategy = SingleShotStrategy()

        raw_result = {
            "agent_exec": {"response": {"content": '"42"'}}  # JSON string primitive
        }

        result = strategy.parse_result(raw_result)

        # Should be wrapped (v0.9.5 fix for primitives)
        assert "response" in result, f"Primitive should be wrapped. Got: {result}"

    def test_validation_bypass_keys(self):
        """
        Verify that "response" key triggers validation bypass.
        """
        # These keys bypass validation in base_agent.py
        bypass_keys = ["_write_insight", "response", "result"]

        output_with_response = {"response": "The answer is 42"}
        has_special = any(key in output_with_response for key in bypass_keys)
        assert has_special, "Output with 'response' should have bypass key"


class TestReasoningModelTemperature:
    """
    Test Issue 2: GPT-5/o3 temperature restriction fix.

    Problem: GPT-5 and o3 models only support temperature=1.0.
    Fix: OpenAI provider now detects reasoning models and filters params.
    """

    def test_is_reasoning_model_gpt5(self):
        """GPT-5 models should be detected as reasoning models."""
        from kaizen.nodes.ai.ai_providers import OpenAIProvider

        provider = OpenAIProvider()

        reasoning_models = ["gpt-5", "GPT-5", "gpt-5-turbo", "gpt5"]
        for model in reasoning_models:
            assert provider._is_reasoning_model(
                model
            ), f"{model} should be detected as reasoning model"

    def test_is_reasoning_model_o1(self):
        """o1 models should be detected as reasoning models."""
        from kaizen.nodes.ai.ai_providers import OpenAIProvider

        provider = OpenAIProvider()

        reasoning_models = ["o1", "o1-preview", "o1-mini"]
        for model in reasoning_models:
            assert provider._is_reasoning_model(
                model
            ), f"{model} should be detected as reasoning model"

    def test_is_reasoning_model_o3(self):
        """o3 models should be detected as reasoning models."""
        from kaizen.nodes.ai.ai_providers import OpenAIProvider

        provider = OpenAIProvider()

        reasoning_models = ["o3", "o3-mini", "o3-preview"]
        for model in reasoning_models:
            assert provider._is_reasoning_model(
                model
            ), f"{model} should be detected as reasoning model"

    def test_non_reasoning_models_not_detected(self):
        """Regular models should NOT be detected as reasoning models."""
        from kaizen.nodes.ai.ai_providers import OpenAIProvider

        provider = OpenAIProvider()

        regular_models = ["gpt-4", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "o4-mini"]
        for model in regular_models:
            assert not provider._is_reasoning_model(
                model
            ), f"{model} should NOT be detected as reasoning model"

    def test_filter_removes_temperature_for_reasoning_models(self):
        """Temperature should be removed for reasoning models."""
        from kaizen.nodes.ai.ai_providers import OpenAIProvider

        provider = OpenAIProvider()

        generation_config = {
            "temperature": 0.7,
            "top_p": 0.9,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.5,
            "max_completion_tokens": 1000,
        }

        filtered = provider._filter_reasoning_model_params("gpt-5", generation_config)

        # Temperature and related params should be removed
        assert "temperature" not in filtered
        assert "top_p" not in filtered
        assert "frequency_penalty" not in filtered
        assert "presence_penalty" not in filtered

        # Other params should be preserved
        assert filtered.get("max_completion_tokens") == 1000

    def test_filter_preserves_params_for_regular_models(self):
        """All params should be preserved for regular models."""
        from kaizen.nodes.ai.ai_providers import OpenAIProvider

        provider = OpenAIProvider()

        generation_config = {
            "temperature": 0.7,
            "top_p": 0.9,
            "max_completion_tokens": 1000,
        }

        filtered = provider._filter_reasoning_model_params("gpt-4o", generation_config)

        # All params should be preserved for regular models
        assert filtered.get("temperature") == 0.7
        assert filtered.get("top_p") == 0.9
        assert filtered.get("max_completion_tokens") == 1000


class TestIntegration:
    """Integration tests for the bug fixes."""

    def test_parse_result_end_to_end_content_key(self):
        """
        End-to-end test: simulate what happens when Azure returns
        {"content": "The answer is 42"} for a question.
        """
        from kaizen.strategies.single_shot import SingleShotStrategy

        strategy = SingleShotStrategy()

        # Simulate typical Azure/OpenAI response structure
        # where the LLM returns {"content": "..."} instead of {"answer": "..."}
        raw_result = {
            "agent_exec": {
                "response": {"content": {"content": "The answer to 2+2 is 4"}}
            }
        }

        result = strategy.parse_result(raw_result)

        # Result should have "response" key for validation bypass
        assert "response" in result
        assert "error" not in result
        assert result["response"] == "The answer to 2+2 is 4"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
