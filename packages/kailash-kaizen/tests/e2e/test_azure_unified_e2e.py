"""End-to-end tests for UnifiedAzureProvider with full Kaizen agent workflows.

IMPORTANT: NO MOCKING - These tests run against real Azure infrastructure.

Prerequisites:
    export AZURE_ENDPOINT="https://your-resource.openai.azure.com"
    export AZURE_API_KEY="your-api-key"
    export AZURE_DEPLOYMENT="gpt-4o"

Run with:
    pytest tests/e2e/test_azure_unified_e2e.py -v
"""

import json
import os
from dataclasses import dataclass

import pytest

from kaizen.nodes.ai.ai_providers import get_provider
from kaizen.nodes.ai.unified_azure_provider import UnifiedAzureProvider


@pytest.fixture
def azure_available():
    """Check if Azure is configured and skip if not."""
    provider = UnifiedAzureProvider()
    if not provider.is_available():
        pytest.skip("Azure not configured - set AZURE_ENDPOINT and AZURE_API_KEY")
    return True


@pytest.fixture
def azure_model():
    """Get Azure model/deployment from environment."""
    return os.getenv("AZURE_DEPLOYMENT", os.getenv("AZURE_MODEL", "gpt-4o"))


@pytest.mark.e2e
class TestAzureUnifiedE2EBasicAgent:
    """E2E tests with basic agent patterns."""

    def test_simple_qa_with_azure(self, azure_available, azure_model):
        """Simple Q&A agent should work with Azure provider."""
        from kaizen.agents.specialized.simple_qa import QAConfig, SimpleQAAgent

        config = QAConfig(
            llm_provider="azure",
            model=azure_model,
            temperature=0.0,
        )

        agent = SimpleQAAgent(config)
        result = agent.ask("What is the capital of Japan? Answer in one word.")

        assert result is not None
        assert "answer" in result
        assert "tokyo" in result["answer"].lower()

    def test_chain_of_thought_with_azure(self, azure_available, azure_model):
        """Chain-of-thought agent should work with Azure provider."""
        from kaizen.agents.specialized.chain_of_thought import (
            ChainOfThoughtAgent,
            CoTConfig,
        )

        config = CoTConfig(
            llm_provider="azure",
            model=azure_model,
            temperature=0.0,
        )

        agent = ChainOfThoughtAgent(config)
        result = agent.reason(
            "If a train travels 60 miles in 1 hour, how far does it travel in 30 minutes?"
        )

        assert result is not None
        assert "answer" in result or "reasoning" in result
        # Should mention 30 miles somewhere
        full_response = str(result)
        assert "30" in full_response


@pytest.mark.e2e
class TestAzureUnifiedE2EStructuredOutput:
    """E2E tests for structured output with agents."""

    def test_structured_extraction_with_azure(self, azure_available, azure_model):
        """Structured extraction should work with Azure provider."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.core.structured_output import create_structured_output_config
        from kaizen.signatures import InputField, OutputField, Signature

        # Define signature for structured output
        class ExtractUserSignature(Signature):
            """Extract user information from text."""

            text: str = InputField(desc="Text containing user information")
            name: str = OutputField(desc="Extracted user name")
            age: int = OutputField(desc="Extracted user age")

        # Create structured output config
        response_format = create_structured_output_config(
            ExtractUserSignature(), strict=True, name="user_extraction"
        )

        config = BaseAgentConfig(
            llm_provider="azure",
            model=azure_model,
            temperature=0.0,
            provider_config={"response_format": response_format},
        )

        agent = BaseAgent(config=config, signature=ExtractUserSignature())
        result = agent.run(text="My name is Bob and I am 25 years old.")

        assert result is not None
        # Response should be parseable JSON with name and age
        assert "Bob" in str(result) or "bob" in str(result).lower()


@pytest.mark.e2e
class TestAzureUnifiedE2EProviderSwitching:
    """E2E tests for provider auto-detection and switching."""

    def test_provider_auto_detection(self, azure_available):
        """Provider should auto-detect correct backend."""
        provider = get_provider("azure")

        backend = provider.get_detected_backend()
        source = provider.get_detection_source()

        # Should have a valid backend and source
        assert backend in ("azure_openai", "azure_ai_foundry")
        assert source in ("pattern", "default", "explicit", "error_fallback")

    def test_capabilities_reflect_backend(self, azure_available):
        """Capabilities should correctly reflect detected backend."""
        provider = get_provider("azure")
        backend = provider.get_detected_backend()
        caps = provider.get_capabilities()

        # Common capabilities
        assert caps.get("chat") is True
        assert caps.get("embeddings") is True
        assert caps.get("streaming") is True
        assert caps.get("tool_calling") is True

        # Backend-specific capabilities
        if backend == "azure_openai":
            assert caps.get("audio_input") is True
            assert caps.get("reasoning_models") is True
        elif backend == "azure_ai_foundry":
            assert caps.get("llama_models") is True
            assert caps.get("mistral_models") is True


@pytest.mark.e2e
class TestAzureUnifiedE2EWorkflowIntegration:
    """E2E tests for workflow integration with Azure provider."""

    def test_workflow_with_azure_llm_node(self, azure_available, azure_model):
        """Workflow with LLMAgentNode should use Azure provider."""
        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Add LLM node with Azure provider
        workflow.add_node(
            "LLMAgentNode",
            "llm",
            {
                "provider": "azure",
                "model": azure_model,
                "messages": [
                    {
                        "role": "user",
                        "content": "What is 2+2? Answer with just the number.",
                    }
                ],
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert "llm" in results
        assert results["llm"] is not None
        # Result should contain "4"
        response = results["llm"]
        if isinstance(response, dict):
            assert "4" in str(response.get("content", ""))
        else:
            assert "4" in str(response)


@pytest.mark.e2e
class TestAzureUnifiedE2EErrorHandling:
    """E2E tests for error handling."""

    def test_graceful_error_for_invalid_model(self, azure_available):
        """Should handle invalid model gracefully."""
        provider = get_provider("azure")

        # This should fail gracefully with a clear error
        with pytest.raises(Exception) as exc_info:
            provider.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model="nonexistent-deployment-12345",
            )

        # Error should be informative
        error_msg = str(exc_info.value).lower()
        assert (
            "not found" in error_msg
            or "does not exist" in error_msg
            or "error" in error_msg
        )

    def test_feature_check_prevents_invalid_usage(self, azure_available):
        """Feature check should prevent using unsupported features."""
        from kaizen.nodes.ai.azure_capabilities import FeatureNotSupportedError

        provider = get_provider("azure")
        backend = provider.get_detected_backend()

        if backend == "azure_ai_foundry":
            # Audio not supported on AI Foundry
            with pytest.raises(FeatureNotSupportedError) as exc_info:
                provider.check_feature("audio_input")

            assert "audio_input" in str(exc_info.value)
            assert "Azure OpenAI" in str(exc_info.value)

        elif backend == "azure_openai":
            # Llama models not supported on Azure OpenAI
            with pytest.raises(FeatureNotSupportedError) as exc_info:
                provider.check_model_requirements("llama-3.1-8b")

            assert "AI Foundry" in str(exc_info.value)


@pytest.mark.e2e
class TestAzureUnifiedE2EMultiModal:
    """E2E tests for multi-modal capabilities (if supported)."""

    def test_vision_capability_check(self, azure_available):
        """Vision capability should be correctly reported."""
        provider = get_provider("azure")
        caps = provider.get_capabilities()

        # Vision should be supported on both backends (with warnings on AI Foundry)
        assert "vision" in caps
        # Vision is marked as True for both (degraded on AI Foundry)
        assert caps.get("vision") is True
