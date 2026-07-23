"""Base classes for Nexus-aware Kaizen agents."""

from typing import Dict, Optional

from .connection import NexusConnection


class NexusDeploymentMixin:
    """
    Mixin providing Nexus deployment capabilities to Kaizen agents.

    Add multi-channel deployment to any Kaizen agent:
    - Deploy as REST API
    - Deploy as CLI command
    - Deploy as MCP tool
    """

    nexus_connection: Optional[NexusConnection] = None

    def connect_nexus(self, nexus_app: "Nexus"):
        """Connect this agent to a Nexus instance."""
        try:
            from nexus import Nexus
        except ImportError:
            raise ImportError(
                "Nexus not available. Install with: pip install kailash-nexus"
            )

        # Allow MockNexus and Mock for testing
        type_name = type(nexus_app).__name__
        if not isinstance(nexus_app, Nexus) and type_name not in [
            "MockNexus",
            "Mock",
            "MagicMock",
        ]:
            raise TypeError(f"Expected Nexus instance, got {type(nexus_app)}")

        self.nexus_connection = NexusConnection(nexus_app=nexus_app)

    def to_workflow(self) -> "WorkflowBuilder":
        """
        Convert agent to Core SDK WorkflowBuilder.

        This enables deployment via Nexus platform.
        """
        from kailash.workflow.builder import WorkflowBuilder

        # FIX 5: LLMAgentNode's NodeParameter is named "provider" — it never
        # reads "llm_provider". Passing "llm_provider" silently dropped the
        # configured provider and every deployment defaulted to LLMAgentNode's
        # own "mock" parameter default (`kaizen/nodes/ai/llm_agent.py::
        # get_parameters`), regardless of a real provider being explicitly
        # configured. `detect_provider_from_env()` mirrors
        # `Agent._get_provider_for_config()`'s exact env-first fallback
        # (openai -> anthropic -> mock) so an unset `llm_provider` never
        # re-defaults to mock when a real API key is present.
        from kaizen.core._provider_env import detect_provider_from_env

        provider = self.config.llm_provider or detect_provider_from_env()

        # Create workflow from agent's signature
        workflow = WorkflowBuilder()

        # Add LLMAgentNode with agent's configuration
        workflow.add_node(
            "LLMAgentNode",
            "agent_node",
            {
                "provider": provider,
                "model": self.config.model,
                "temperature": getattr(self.config, "temperature", 0.7),
                "system_prompt": self._build_system_prompt(),
            },
        )

        return workflow

    def _build_system_prompt(self) -> str:
        """Build system prompt from agent signature."""
        if hasattr(self, "signature") and self.signature:
            # Build prompt from signature fields
            prompt_parts = []

            # Add signature description if available
            if hasattr(self.signature, "description") and self.signature.description:
                prompt_parts.append(self.signature.description)
            else:
                prompt_parts.append("You are a helpful AI assistant.")

            # Add input/output field descriptions
            if hasattr(self.signature, "input_fields"):
                input_fields = [
                    f"- {name}: {field.description}"
                    for name, field in self.signature.input_fields.items()
                    if hasattr(field, "description")
                ]
                if input_fields:
                    prompt_parts.append("\nInputs:\n" + "\n".join(input_fields))

            if hasattr(self.signature, "output_fields"):
                output_fields = [
                    f"- {name}: {field.description}"
                    for name, field in self.signature.output_fields.items()
                    if hasattr(field, "description")
                ]
                if output_fields:
                    prompt_parts.append("\nOutputs:\n" + "\n".join(output_fields))

            return "\n".join(prompt_parts)

        return "You are a helpful AI assistant."

    def deploy_as_api(self, nexus_app: "Nexus", name: str) -> str:
        """Deploy this agent as API endpoint."""
        from .deployment import deploy_as_api

        return deploy_as_api(self, nexus_app, name)

    def deploy_as_cli(self, nexus_app: "Nexus", name: str) -> str:
        """Deploy this agent as CLI command."""
        from .deployment import deploy_as_cli

        return deploy_as_cli(self, nexus_app, name)

    def deploy_as_mcp(self, nexus_app: "Nexus", name: str) -> str:
        """Deploy this agent as MCP tool."""
        from .deployment import deploy_as_mcp

        return deploy_as_mcp(self, nexus_app, name)

    def deploy_multi_channel(self, nexus_app: "Nexus", name: str) -> Dict[str, str]:
        """Deploy this agent across all channels."""
        from .deployment import deploy_multi_channel

        return deploy_multi_channel(self, nexus_app, name)
