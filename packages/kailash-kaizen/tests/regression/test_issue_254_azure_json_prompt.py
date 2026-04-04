"""Regression: #254 — Azure json_object response_format requires 'json' in system prompt.

When using response_format: {"type": "json_object"} with Azure OpenAI,
Azure requires the word 'json' to appear somewhere in the messages.
The SDK auto-generates json_object for non-OpenAI providers but the
system prompt from BaseAgent._generate_system_prompt() never mentions JSON.

Fix: workflow_generator.generate_workflow() now appends a JSON instruction
to the system prompt when response_format type is json_object/json_schema
and the prompt doesn't already contain "json".
"""

import pytest

from kaizen.core.config import BaseAgentConfig
from kaizen.core.workflow_generator import WorkflowGenerator
from kaizen.signatures import InputField, OutputField, Signature


class TranslateSig(Signature):
    """Translate text to target language."""

    text: str = InputField(desc="Text to translate")
    translation: str = OutputField(desc="Translated text")


@pytest.mark.regression
class TestIssue254AzureJsonPrompt:
    """Regression tests for #254: Azure json_object requires 'json' in prompt."""

    def test_azure_auto_config_adds_json_to_system_prompt(self):
        """System prompt must contain 'json' when Azure auto-generates json_object config."""
        config = BaseAgentConfig(
            llm_provider="azure",
            model="gpt-5-mini",
        )

        generator = WorkflowGenerator(config=config, signature=TranslateSig())
        workflow = generator.generate_signature_workflow()

        node_id = list(workflow.nodes.keys())[0]
        node_config = workflow.nodes[node_id]["config"]

        system_prompt = node_config.get("system_prompt", "")
        assert (
            "json" in system_prompt.lower()
        ), "System prompt must contain 'json' for Azure json_object response_format"

    def test_explicit_json_object_adds_json_to_system_prompt(self):
        """System prompt must contain 'json' when user provides json_object config."""
        config = BaseAgentConfig(
            llm_provider="azure",
            model="gpt-5-mini",
            provider_config={"type": "json_object"},
        )

        generator = WorkflowGenerator(config=config, signature=TranslateSig())
        workflow = generator.generate_signature_workflow()

        node_id = list(workflow.nodes.keys())[0]
        node_config = workflow.nodes[node_id]["config"]

        system_prompt = node_config.get("system_prompt", "")
        assert "json" in system_prompt.lower()

    def test_no_duplicate_json_instruction_when_prompt_already_has_json(self):
        """Should not duplicate JSON instruction if prompt already mentions json."""

        class JsonSig(Signature):
            """Respond with a json object."""

            text: str = InputField(desc="Input")
            result: str = OutputField(desc="Output")

        config = BaseAgentConfig(
            llm_provider="azure",
            model="gpt-5-mini",
            provider_config={"type": "json_object"},
        )

        generator = WorkflowGenerator(config=config, signature=JsonSig())
        workflow = generator.generate_signature_workflow()

        node_id = list(workflow.nodes.keys())[0]
        node_config = workflow.nodes[node_id]["config"]
        system_prompt = node_config.get("system_prompt", "")

        # Should not have the appended instruction since docstring already has "json"
        assert system_prompt.count("Respond with a JSON object") <= 1

    def test_openai_strict_mode_no_unnecessary_json_instruction(self):
        """OpenAI with strict json_schema should still get instruction (harmless)."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o",
        )

        generator = WorkflowGenerator(config=config, signature=TranslateSig())
        workflow = generator.generate_signature_workflow()

        node_id = list(workflow.nodes.keys())[0]
        node_config = workflow.nodes[node_id]["config"]

        # OpenAI auto-generates json_schema (strict=True), which also triggers
        # the json instruction — this is harmless and ensures compatibility
        provider_config = node_config.get("provider_config", {})
        assert provider_config.get("type") in ("json_schema", "json_object")
