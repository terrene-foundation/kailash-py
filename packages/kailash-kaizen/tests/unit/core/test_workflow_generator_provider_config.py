"""
Test WorkflowGenerator structured output and provider_config handling.

Verifies that:
- response_format is placed as a top-level key in node_config for structured output
- provider_config is preserved as nested dict for provider-specific settings
- structured_output_mode controls auto-generation behavior

References:
- Explicit config refactor: response_format separated from provider_config
- Original bug: workflow_generator.py was flattening provider_config
"""

import warnings

import pytest
from kaizen.core.config import BaseAgentConfig
from kaizen.core.workflow_generator import WorkflowGenerator
from kaizen.signatures import InputField, OutputField, Signature


class SimpleSignature(Signature):
    """Simple test signature."""

    question: str = InputField(desc="Question")
    answer: str = OutputField(desc="Answer")


class TestWorkflowGeneratorProviderConfig:
    """Test response_format and provider_config handling in WorkflowGenerator."""

    def test_explicit_response_format_in_node_config(self):
        """Test explicit response_format is placed as top-level key in node_config."""
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "test",
                "strict": True,
                "schema": {"type": "object"},
            },
        }

        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o-2024-08-06",
            response_format=response_format,
            structured_output_mode="explicit",
        )

        generator = WorkflowGenerator(config=config, signature=SimpleSignature())
        workflow = generator.generate_signature_workflow()

        # Verify workflow structure
        assert workflow.nodes
        assert len(workflow.nodes) == 1

        node_id = list(workflow.nodes.keys())[0]
        node = workflow.nodes[node_id]
        assert node["type"] == "LLMAgentNode"

        # response_format is a top-level key in node_config
        assert "response_format" in node["config"]
        assert node["config"]["response_format"] == response_format

        # provider_config should NOT be present (none provided)
        assert "provider_config" not in node["config"]

    def test_provider_config_preserved_separately_from_response_format(self):
        """Test provider_config holds only provider-specific settings."""
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "test",
                "strict": True,
                "schema": {"type": "object"},
            },
        }
        provider_config = {
            "api_version": "2024-02-01",
            "deployment": "my-deployment",
        }

        config = BaseAgentConfig(
            llm_provider="azure",
            model="gpt-4o",
            response_format=response_format,
            provider_config=provider_config,
            structured_output_mode="explicit",
        )

        generator = WorkflowGenerator(config=config, signature=SimpleSignature())
        workflow = generator.generate_signature_workflow()

        node_id = list(workflow.nodes.keys())[0]
        node = workflow.nodes[node_id]

        # Both are present as separate top-level keys
        assert "response_format" in node["config"]
        assert node["config"]["response_format"] == response_format
        assert "provider_config" in node["config"]
        assert node["config"]["provider_config"] == provider_config

    def test_legacy_provider_config_migrated_to_response_format(self):
        """Test legacy provider_config with 'type' key is migrated to response_format."""
        # Old-style: structured output config in provider_config
        legacy_provider_config = {
            "type": "json_schema",
            "json_schema": {
                "name": "test",
                "strict": True,
                "schema": {"type": "object"},
            },
        }

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            config = BaseAgentConfig(
                llm_provider="openai",
                model="gpt-4o-2024-08-06",
                provider_config=legacy_provider_config,
                structured_output_mode="explicit",
            )

        # __post_init__ migration should have moved structured output keys
        assert config.response_format is not None
        assert config.response_format["type"] == "json_schema"
        # provider_config should be cleared (no non-structured keys remained)
        assert config.provider_config is None

        generator = WorkflowGenerator(config=config, signature=SimpleSignature())
        workflow = generator.generate_signature_workflow()

        node_id = list(workflow.nodes.keys())[0]
        node = workflow.nodes[node_id]

        # response_format in node_config from migration
        assert "response_format" in node["config"]
        assert node["config"]["response_format"]["type"] == "json_schema"
        # provider_config should NOT be present (was fully migrated)
        assert "provider_config" not in node["config"]

    def test_fallback_workflow_preserves_provider_config(self):
        """Test provider_config is preserved in fallback workflow."""
        provider_config = {
            "api_version": "2024-02-01",
            "deployment": "my-deployment",
        }

        config = BaseAgentConfig(
            llm_provider="azure",
            model="gpt-4o",
            provider_config=provider_config,
        )

        generator = WorkflowGenerator(config=config)
        workflow = generator.generate_fallback_workflow()

        assert workflow.nodes
        assert len(workflow.nodes) == 1

        node_id = list(workflow.nodes.keys())[0]
        node = workflow.nodes[node_id]
        assert node["type"] == "LLMAgentNode"

        assert "provider_config" in node["config"]
        assert node["config"]["provider_config"] == provider_config

    def test_auto_mode_generates_response_format_with_deprecation_warning(self):
        """Test auto mode auto-generates response_format with FutureWarning.

        When structured_output_mode='auto' and no response_format is set,
        WorkflowGenerator auto-generates structured output config and emits a
        FutureWarning (deprecated since v2.5.0, removal in v3.0).
        """
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4",
            structured_output_mode="auto",  # Must be explicit — default is now "explicit"
        )

        generator = WorkflowGenerator(config=config, signature=SimpleSignature())

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            workflow = generator.generate_signature_workflow()

            # Should emit FutureWarning about auto mode deprecation
            future_warnings = [x for x in w if issubclass(x.category, FutureWarning)]
            assert len(future_warnings) >= 1
            assert "structured_output_mode='auto' is deprecated" in str(
                future_warnings[0].message
            )

        node_id = list(workflow.nodes.keys())[0]
        node = workflow.nodes[node_id]

        # response_format is present with auto-generated JSON schema
        assert "response_format" in node["config"]
        assert node["config"]["response_format"]["type"] == "json_schema"
        assert "json_schema" in node["config"]["response_format"]
        assert (
            node["config"]["response_format"]["json_schema"]["name"]
            == "SimpleSignature"
        )

    def test_off_mode_suppresses_structured_output(self):
        """Test structured_output_mode='off' prevents any structured output."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4",
            response_format={"type": "json_object"},  # Explicitly set but...
            structured_output_mode="off",  # ...off mode overrides
        )

        generator = WorkflowGenerator(config=config, signature=SimpleSignature())
        workflow = generator.generate_signature_workflow()

        node_id = list(workflow.nodes.keys())[0]
        node = workflow.nodes[node_id]

        # response_format should NOT be in node_config when mode is "off"
        assert "response_format" not in node["config"]
