"""
WorkflowGenerator - Convert signatures to Core SDK workflows.

This module provides the WorkflowGenerator class that translates
signature-based agent definitions into executable Core SDK workflows.

Key Responsibilities:
- Generate workflows from Signature definitions
- Create LLMAgentNode instances with proper configuration
- Map input/output fields to workflow parameters
- Handle both signature-based and fallback workflows

References:
- ADR-006: Agent Base Architecture design
- TODO-157: Task 1.3, 1.16a, 1.16b, 1.16c
- Core SDK: WorkflowBuilder, LLMAgentNode

Author: Kaizen Framework Team
Created: 2025-10-01
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.credentials import get_credential_store

from kaizen.core.config import BaseAgentConfig
from kaizen.signatures import Signature

# from .config import BaseAgentConfig

logger = logging.getLogger(__name__)


class WorkflowGenerator:
    """
    Generate Core SDK workflows from Kaizen signatures.

    The WorkflowGenerator is responsible for translating the high-level
    signature-based agent definitions into executable Core SDK workflows
    using WorkflowBuilder and LLMAgentNode.

    Example Usage:
        >>> from kaizen.core.workflow_generator import WorkflowGenerator
        >>> from kaizen.signatures import Signature, InputField, OutputField
        >>> from kaizen.core.config import BaseAgentConfig
        >>>
        >>> # Create signature
        >>> class QASignature(Signature):
        ...     question: str = InputField(desc="Question")
        ...     answer: str = OutputField(desc="Answer")
        >>>
        >>> # Create config
        >>> config = BaseAgentConfig(
        ...     llm_provider="openai",
        ...     model="gpt-4",
        ...     temperature=0.1
        ... )
        >>>
        >>> # Generate workflow
        >>> generator = WorkflowGenerator(config=config, signature=QASignature())
        >>> workflow = generator.generate_signature_workflow()
        >>>
        >>> # Execute workflow
        >>> from kailash.runtime.local import LocalRuntime
        >>> runtime = LocalRuntime()
        >>> results, run_id = runtime.execute(workflow.build())

    Notes:
    - This is a SKELETON implementation for TDD Phase 1
    - Implementation driven by tests in test_base_agent_workflow.py
    - Core pattern: workflow.add_node('LLMAgentNode', 'agent', {...})
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        signature: Optional[Signature] = None,
        prompt_generator: Optional[Callable[[], str]] = None,
        agent: Optional[Any] = None,
    ):
        """
        Initialize WorkflowGenerator.

        Args:
            config: Agent configuration
            signature: Optional signature (for signature-based workflow)
            prompt_generator: Optional callback for custom system prompt generation.
                            If provided, will be used instead of default _generate_system_prompt().
                            This enables BaseAgent subclasses to provide custom prompts.
            agent: Optional agent instance for MCP tool discovery.
                  If provided and agent has MCP configured, tools will be auto-discovered
                  and passed to LLMAgentNode for tool calling.
        """
        self.config = config
        self.signature = signature
        self.prompt_generator = prompt_generator
        self.agent = agent

    def generate_signature_workflow(self) -> WorkflowBuilder:
        """
        Generate workflow from signature definition.

        Creates a Core SDK workflow that:
        1. Uses LLMAgentNode from src/kailash/nodes/ai/llm_agent.py
        2. Maps signature input fields to workflow inputs
        3. Maps signature output fields to workflow outputs
        4. Includes proper system prompt from signature

        Returns:
            WorkflowBuilder: Workflow ready for execution

        Core SDK Pattern:
            workflow.add_node('LLMAgentNode', 'agent', {
                'model': self.config.model,
                'provider': self.config.llm_provider,
                'temperature': self.config.temperature,
                'system_prompt': self._generate_system_prompt(),
            })

        Example:
            >>> workflow = generator.generate_signature_workflow()
            >>> built = workflow.build()
            >>> runtime.execute(built)
        """
        # CRITICAL: Import Kaizen's LLMAgentNode to ensure it's registered
        # Core SDK uses lazy loading, so if we don't import it explicitly,
        # the Core SDK version will be used instead of Kaizen's enhanced version
        from kaizen.nodes.ai.llm_agent import LLMAgentNode as _  # noqa: F401

        if not self.signature:
            raise ValueError(
                "Signature required for signature-based workflow generation"
            )

        # Create workflow builder
        workflow = WorkflowBuilder()

        # Build generation config (handle both dict and BaseAgentConfig)
        generation_config = {}

        # Get config values safely (handle both dict and object)
        temperature = (
            getattr(self.config, "temperature", None)
            if hasattr(self.config, "temperature")
            else self.config.get("temperature")
        )
        max_tokens = (
            getattr(self.config, "max_tokens", None)
            if hasattr(self.config, "max_tokens")
            else self.config.get("max_tokens")
        )
        llm_provider = (
            getattr(self.config, "llm_provider", None)
            if hasattr(self.config, "llm_provider")
            else self.config.get("llm_provider")
        )
        model = (
            getattr(self.config, "model", None)
            if hasattr(self.config, "model")
            else self.config.get("model")
        )
        provider_config = (
            getattr(self.config, "provider_config", None)
            if hasattr(self.config, "provider_config")
            else (
                self.config.get("provider_config")
                if isinstance(self.config, dict)
                else None
            )
        )
        response_format = (
            getattr(self.config, "response_format", None)
            if hasattr(self.config, "response_format")
            else (
                self.config.get("response_format")
                if isinstance(self.config, dict)
                else None
            )
        )
        structured_output_mode = (
            getattr(self.config, "structured_output_mode", "auto")
            if hasattr(self.config, "structured_output_mode")
            else (
                self.config.get("structured_output_mode", "auto")
                if isinstance(self.config, dict)
                else "auto"
            )
        )

        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_tokens is not None:
            generation_config["max_tokens"] = max_tokens

        # Structured output configuration
        #
        # response_format holds structured output config (json_object, json_schema).
        # structured_output_mode controls behavior:
        #   "off"      — no structured output, even if response_format is set
        #   "explicit"  — use only what the user provided in response_format
        #   "auto"      — auto-generate if not provided (deprecated behavior)
        #
        # NOTE: Use strict=False when prompt_generator is provided, as this indicates
        # the agent has custom system prompt (e.g., BaseAutonomousAgent with tool calling).
        # Tool calling requires flexible JSON responses that can't use strict schemas.
        #
        # Structured output auto-configuration is now supported for:
        # - OpenAI: Uses response_format with json_schema or json_object
        # - Google/Gemini: Translates to response_mime_type + response_json_schema
        # - Azure: Translates to JsonSchemaFormat
        providers_with_structured_output = ["openai", "google", "gemini", "azure"]
        effective_provider = llm_provider or "openai"

        if structured_output_mode == "off":
            response_format = None
        elif structured_output_mode == "explicit":
            pass  # Only use what the user provided in response_format
        elif structured_output_mode == "auto":
            # Auto-generate if not provided (deprecated behavior)
            if (
                not response_format
                and effective_provider in providers_with_structured_output
                and self.signature
            ):
                import warnings

                from kaizen.core.structured_output import (
                    create_structured_output_config,
                )

                # Detect tool calling mode: custom prompt generator indicates autonomous agents
                # with tool-aware system prompts (BaseAutonomousAgent._generate_system_prompt)
                # Also, strict mode only works for OpenAI - other providers use it for schema guidance
                use_strict_mode = (
                    self.prompt_generator is None and effective_provider == "openai"
                )

                response_format = create_structured_output_config(
                    signature=self.signature,
                    strict=use_strict_mode,  # True for OpenAI without tools, False otherwise
                    name=f"{self.signature.__class__.__name__}",
                )
                warnings.warn(
                    "Auto-generated structured output is deprecated. "
                    "Set response_format explicitly on BaseAgentConfig. "
                    "Example: BaseAgentConfig(response_format={'type': 'json_object'}, "
                    "structured_output_mode='explicit')",
                    DeprecationWarning,
                    stacklevel=2,
                )

        # Get optional per-request overrides
        api_key = (
            getattr(self.config, "api_key", None)
            if hasattr(self.config, "api_key")
            else self.config.get("api_key")
        )
        base_url = (
            getattr(self.config, "base_url", None)
            if hasattr(self.config, "base_url")
            else self.config.get("base_url")
        )

        # Create LLMAgentNode with signature-based configuration
        node_config = {
            "provider": llm_provider or "openai",
            "model": model or "gpt-4",
            "system_prompt": self._get_system_prompt(),
            "generation_config": generation_config,
        }

        # Register per-request credentials in CredentialStore (never in node_config)
        if api_key or base_url:
            credential_ref = get_credential_store().register(
                api_key=api_key, base_url=base_url
            )
            node_config["credential_ref"] = credential_ref

        # Add structured output config
        if response_format:
            node_config["response_format"] = response_format

        # Add provider-specific config separately (api_version, deployment, etc.)
        if provider_config:
            node_config["provider_config"] = provider_config

        # Azure requires the word "json" in messages when using
        # response_format.type == "json_object" or "json_schema".
        # Append instruction if system prompt doesn't already mention it.
        # Removal deferred to Phase 4 (StructuredOutput.prompt_hint())
        if (
            response_format
            and isinstance(response_format, dict)
            and response_format.get("type") in ("json_object", "json_schema")
        ):
            system_prompt = node_config.get("system_prompt", "")
            if "json" not in system_prompt.lower():
                node_config["system_prompt"] = (
                    system_prompt
                    + "\n\nRespond with a JSON object containing the output fields."
                )

        # Discover and add MCP tools if agent is provided
        # This enables autonomous agents to use tools via MCP client integration
        if self.agent and hasattr(self.agent, "discover_mcp_tools"):
            try:
                mcp_tools = None

                # Try to get cached tools from BaseAgent's _discovered_mcp_tools first
                # This cache contains tools with proper naming convention (mcp__<server>__<tool>)
                if hasattr(self.agent, "_discovered_mcp_tools"):
                    # Check if any tools are cached from previous discovery
                    if self.agent._discovered_mcp_tools:
                        # Flatten cached tools from all servers
                        mcp_tools = []
                        for server_tools in self.agent._discovered_mcp_tools.values():
                            mcp_tools.extend(server_tools)
                        logger.debug(
                            f"Using {len(mcp_tools)} cached MCP tools from BaseAgent cache"
                        )

                # If no cached tools, try async discovery
                if not mcp_tools:
                    # Check if we're already in an async context
                    try:
                        loop = asyncio.get_running_loop()
                        # Already in async context - skip discovery for now
                        # Tools should be discovered before workflow generation
                        logger.info(
                            "In async context: Tools should be discovered via "
                            "await agent.discover_mcp_tools() before workflow generation"
                        )
                    except RuntimeError:
                        # Not in async context - safe to create new event loop
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            mcp_tools = loop.run_until_complete(
                                self.agent.discover_mcp_tools()
                            )
                            logger.debug(
                                f"Discovered {len(mcp_tools) if mcp_tools else 0} MCP tools via new event loop"
                            )
                        finally:
                            loop.close()

                # Convert and add tools to node config
                if mcp_tools:
                    from kaizen.core.tool_formatters import get_tools_for_provider

                    # Convert to provider-specific format
                    provider_tools = get_tools_for_provider(
                        mcp_tools, llm_provider or "openai"
                    )

                    # Add to node config
                    node_config["tools"] = provider_tools

                    logger.info(
                        f"Added {len(provider_tools)} MCP tools to LLMAgentNode config"
                    )
            except Exception as e:
                logger.warning(f"Failed to discover MCP tools: {e}")

        # Add the LLMAgentNode to workflow
        workflow.add_node("LLMAgentNode", "agent_exec", node_config)

        return workflow

    def generate_fallback_workflow(self) -> WorkflowBuilder:
        """
        Generate fallback workflow without signature compilation.

        Creates a simple workflow with direct LLM call for cases where
        signature programming is disabled or unavailable.

        Returns:
            WorkflowBuilder: Simple workflow with direct LLM call

        Example:
            >>> workflow = generator.generate_fallback_workflow()
            >>> built = workflow.build()
            >>> runtime.execute(built, parameters={'prompt': 'What is 2+2?'})
        """
        # Create workflow builder
        workflow = WorkflowBuilder()

        # Build generation config
        generation_config = {
            "temperature": self.config.temperature,
        }
        if self.config.max_tokens:
            generation_config["max_tokens"] = self.config.max_tokens

        # Create simple LLMAgentNode configuration (no signature)
        node_config = {
            "provider": self.config.llm_provider or "openai",
            "model": self.config.model or "gpt-4",
            "generation_config": generation_config,
        }

        # Register per-request credentials in CredentialStore (never in node_config)
        fallback_api_key = (
            getattr(self.config, "api_key", None)
            if hasattr(self.config, "api_key")
            else None
        )
        fallback_base_url = (
            getattr(self.config, "base_url", None)
            if hasattr(self.config, "base_url")
            else None
        )
        if fallback_api_key or fallback_base_url:
            credential_ref = get_credential_store().register(
                api_key=fallback_api_key, base_url=fallback_base_url
            )
            node_config["credential_ref"] = credential_ref

        # Add provider-specific config (preserve as nested dict for LLMAgentNode)
        if self.config.provider_config:
            node_config["provider_config"] = self.config.provider_config

        # Add the LLMAgentNode to workflow (without system prompt for fallback)
        workflow.add_node("LLMAgentNode", "agent_fallback", node_config)

        return workflow

    def _get_system_prompt(self) -> str:
        """
        Get system prompt, using callback if provided, otherwise default generation.

        This method enables extension point pattern: if BaseAgent provides a
        custom prompt_generator callback, use it. Otherwise, fall back to
        signature-based generation.

        Returns:
            str: System prompt for LLM

        Example (with callback):
            >>> def custom_prompt():
            ...     return "You are a medical assistant. Always advise consulting a doctor."
            >>>
            >>> generator = WorkflowGenerator(config, signature, prompt_generator=custom_prompt)
            >>> prompt = generator._get_system_prompt()
            >>> assert "medical assistant" in prompt

        Example (without callback):
            >>> generator = WorkflowGenerator(config, signature)
            >>> prompt = generator._get_system_prompt()
            >>> # Uses default _generate_system_prompt() method
        """
        if self.prompt_generator is not None:
            # Use custom prompt generator callback (from BaseAgent or elsewhere)
            return self.prompt_generator()
        else:
            # Fall back to default signature-based prompt generation
            return self._generate_system_prompt()

    def _generate_system_prompt(self) -> str:
        """
        Generate system prompt from signature (default implementation).

        This is the fallback implementation when no custom prompt_generator
        callback is provided. It generates a prompt from signature fields.

        Analyzes signature input/output fields to create an appropriate
        system prompt for the LLM.

        Returns:
            str: System prompt

        Example:
            >>> prompt = generator._generate_system_prompt()
            >>> print(prompt)
            Task: Given question, produce answer.
        """
        if not self.signature:
            return "You are a helpful AI assistant."

        # Start with signature description if available
        parts = []

        if hasattr(self.signature, "description") and self.signature.description:
            parts.append(self.signature.description)
        elif hasattr(self.signature, "name") and self.signature.name:
            parts.append(f"Task: {self.signature.name}")

        # Describe inputs
        if hasattr(self.signature, "inputs") and self.signature.inputs:
            input_list = ", ".join(self.signature.inputs)
            parts.append(f"\nInputs: {input_list}")

        # Describe outputs
        if hasattr(self.signature, "outputs") and self.signature.outputs:
            output_list = ", ".join(
                self.signature.outputs
                if isinstance(self.signature.outputs, list)
                else [str(self.signature.outputs)]
            )
            parts.append(f"Outputs: {output_list}")

        # Add field descriptions if available
        if hasattr(self.signature, "input_fields") and self.signature.input_fields:
            field_descs = []
            for field_name, field_def in self.signature.input_fields.items():
                if isinstance(field_def, dict) and "desc" in field_def:
                    field_descs.append(f"  - {field_name}: {field_def['desc']}")
            if field_descs:
                parts.append("\nInput Field Descriptions:")
                parts.extend(field_descs)

        if hasattr(self.signature, "output_fields") and self.signature.output_fields:
            field_descs = []
            for field_name, field_def in self.signature.output_fields.items():
                if isinstance(field_def, dict) and "desc" in field_def:
                    field_type = field_def.get("type", str).__name__
                    field_descs.append(
                        f"  - {field_name} ({field_type}): {field_def['desc']}"
                    )
            if field_descs:
                parts.append("\nOutput Field Descriptions:")
                parts.extend(field_descs)

        # Add JSON formatting instructions ONLY if not using structured outputs
        # When using strict mode, the provider API enforces the schema automatically
        llm_provider = (
            getattr(self.config, "llm_provider", None)
            if hasattr(self.config, "llm_provider")
            else self.config.get("llm_provider")
        )
        response_format = (
            getattr(self.config, "response_format", None)
            if hasattr(self.config, "response_format")
            else (
                self.config.get("response_format")
                if isinstance(self.config, dict)
                else None
            )
        )
        structured_output_mode = (
            getattr(self.config, "structured_output_mode", "auto")
            if hasattr(self.config, "structured_output_mode")
            else (
                self.config.get("structured_output_mode", "auto")
                if isinstance(self.config, dict)
                else "auto"
            )
        )

        # Check if using structured outputs (json_schema mode via response_format)
        using_structured_outputs = False
        if structured_output_mode == "off":
            using_structured_outputs = False
        elif response_format and isinstance(response_format, dict):
            using_structured_outputs = response_format.get("type") == "json_schema"
        elif (
            structured_output_mode == "auto"
            and llm_provider == "openai"
            and self.signature
        ):
            # Will auto-configure structured outputs in generate_signature_workflow()
            using_structured_outputs = True

        if (
            hasattr(self.signature, "output_fields")
            and self.signature.output_fields
            and not using_structured_outputs
        ):
            parts.append("\n---")
            parts.append(
                "\nIMPORTANT: You must respond with a valid JSON object containing exactly these fields:"
            )
            json_example = {}
            for field_name, field_def in self.signature.output_fields.items():
                field_type = field_def.get("type", str)
                # Generate example values based on type
                if field_type == str:
                    json_example[field_name] = f"<your {field_name} here>"
                elif field_type == float:
                    json_example[field_name] = 0.0
                elif field_type == int:
                    json_example[field_name] = 0
                elif field_type == bool:
                    json_example[field_name] = False
                elif field_type == list:
                    json_example[field_name] = []
                elif field_type == dict:
                    json_example[field_name] = {}
                else:
                    json_example[field_name] = f"<{field_name}>"

            import json as json_module

            parts.append(
                f"\nExpected JSON format:\n```json\n{json_module.dumps(json_example, indent=2)}\n```"
            )
            parts.append(
                "\nDo not include any explanation or text outside the JSON object."
            )

        # Join all parts
        if parts:
            return "\n".join(parts)

        # Fallback
        return "You are a helpful AI assistant."
