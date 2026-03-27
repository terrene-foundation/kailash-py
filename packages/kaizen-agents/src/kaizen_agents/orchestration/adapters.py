# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Structured LLM adapter for the orchestration layer.

Provides a :class:`StructuredLLMAdapter` protocol and per-provider
implementations for structured (JSON schema) and unstructured completions.
The orchestration planner, designer, and recovery modules use this protocol
instead of importing a specific provider SDK.

This module extends the ``LLMClient`` in ``kaizen_agents.llm`` with
multi-provider support.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class StructuredResponse:
    """Result from a structured or unstructured LLM completion.

    Attributes:
        content: Text content of the response.
        parsed: Parsed JSON dict (for structured completions).
        tool_calls: Tool calls in OpenAI-compatible format.
        model: The model that produced this response.
        usage: Token usage statistics.
    """

    content: str = ""
    parsed: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)


@runtime_checkable
class StructuredLLMAdapter(Protocol):
    """Protocol for synchronous structured LLM completions.

    Used by orchestration modules (planner, designer, recovery) that need
    structured JSON output from the LLM.
    """

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> StructuredResponse:
        """Run a single chat completion.

        Parameters
        ----------
        messages:
            Conversation messages.
        tools:
            Optional tool definitions.
        response_format:
            Optional response format constraint.
        temperature:
            Override temperature.
        max_tokens:
            Override max tokens.
        """
        ...  # pragma: no cover

    def complete_structured(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        schema_name: str = "response",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Run a structured completion constrained by a JSON schema.

        Parameters
        ----------
        messages:
            Conversation messages.
        schema:
            JSON Schema dict for the expected output.
        schema_name:
            Name for the schema.
        temperature:
            Override temperature.
        max_tokens:
            Override max tokens.

        Returns
        -------
        Parsed dict matching the provided schema.
        """
        ...  # pragma: no cover


class OpenAIStructuredAdapter:
    """Structured LLM adapter for OpenAI models.

    Wraps the synchronous ``openai.OpenAI`` client.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "No OpenAI API key provided.  Set OPENAI_API_KEY in your "
                "environment or pass api_key explicitly."
            )

        self._model = model or (
            os.environ.get("OPENAI_PROD_MODEL")
            or os.environ.get("DEFAULT_LLM_MODEL")
            or "gpt-4o"
        )
        self._temperature = temperature
        self._max_tokens = max_tokens

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "The openai package is required.  "
                "Install it with: pip install openai"
            ) from exc

        client_kwargs: dict[str, Any] = {"api_key": resolved_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> StructuredResponse:
        """Run a chat completion via the OpenAI API."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens or self._max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        tool_calls_parsed: list[dict[str, Any]] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls_parsed.append({
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })

        usage_dict: dict[str, int] = {}
        if response.usage:
            usage_dict = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return StructuredResponse(
            content=message.content or "",
            tool_calls=tool_calls_parsed,
            model=response.model,
            usage=usage_dict,
        )

    def complete_structured(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        schema_name: str = "response",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Run a structured completion via OpenAI's JSON schema mode."""
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        }

        result = self.complete(
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = result.content.strip()
        if not content:
            raise ValueError("LLM returned empty content for structured output request")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM response is not valid JSON: {exc}.  Content: {content[:500]}"
            ) from exc

        if not isinstance(parsed, dict):
            raise ValueError(
                f"Expected a JSON object, got {type(parsed).__name__}: {content[:500]}"
            )

        return parsed


class AnthropicStructuredAdapter:
    """Structured LLM adapter for Anthropic Claude models.

    Wraps the synchronous ``anthropic.Anthropic`` client.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "No Anthropic API key provided.  Set ANTHROPIC_API_KEY in your "
                "environment or pass api_key explicitly."
            )

        self._model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self._temperature = temperature
        self._max_tokens = max_tokens

        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "The anthropic package is required.  "
                "Install it with: pip install anthropic"
            ) from exc

        self._client = anthropic.Anthropic(api_key=resolved_key)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> StructuredResponse:
        """Run a chat completion via the Anthropic API."""
        # Separate system message
        system_prompt = ""
        api_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content", "")
            else:
                api_messages.append(msg)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens or self._max_tokens,
            "temperature": temperature if temperature is not None else self._temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        if tools:
            anthropic_tools = []
            for tool in tools:
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })
            kwargs["tools"] = anthropic_tools

        response = self._client.messages.create(**kwargs)

        content_text = ""
        tool_calls: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", "") == "text":
                content_text += getattr(block, "text", "")
            elif getattr(block, "type", "") == "tool_use":
                tool_calls.append({
                    "id": getattr(block, "id", ""),
                    "type": "function",
                    "function": {
                        "name": getattr(block, "name", ""),
                        "arguments": json.dumps(getattr(block, "input", {})),
                    },
                })

        usage_dict: dict[str, int] = {}
        if response.usage:
            usage_dict = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }

        return StructuredResponse(
            content=content_text,
            tool_calls=tool_calls,
            model=response.model,
            usage=usage_dict,
        )

    def complete_structured(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        schema_name: str = "response",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Run a structured completion via Anthropic.

        Anthropic does not have native JSON schema mode, so we inject the
        schema into the system prompt and parse the response.
        """
        schema_instruction = (
            f"You MUST respond with a valid JSON object matching this schema:\n"
            f"```json\n{json.dumps(schema, indent=2)}\n```\n"
            f"Respond with ONLY the JSON object, no other text."
        )

        augmented_messages = list(messages)
        # Inject schema instruction into system message or prepend as user
        if augmented_messages and augmented_messages[0].get("role") == "system":
            augmented_messages[0] = {
                "role": "system",
                "content": augmented_messages[0]["content"] + "\n\n" + schema_instruction,
            }
        else:
            augmented_messages.insert(0, {"role": "user", "content": schema_instruction})

        result = self.complete(
            messages=augmented_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = result.content.strip()
        # Strip markdown code fence if present
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        if not content:
            raise ValueError("LLM returned empty content for structured output request")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM response is not valid JSON: {exc}.  Content: {content[:500]}"
            ) from exc

        if not isinstance(parsed, dict):
            raise ValueError(
                f"Expected a JSON object, got {type(parsed).__name__}: {content[:500]}"
            )

        return parsed


def get_structured_adapter(
    provider: str = "",
    *,
    model: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> StructuredLLMAdapter:
    """Create a structured LLM adapter for the given provider.

    Parameters
    ----------
    provider:
        Provider name: ``"openai"``, ``"anthropic"``.  Empty string or
        ``"openai"`` defaults to OpenAI.
    model:
        Model name override.
    api_key:
        API key override.
    **kwargs:
        Extra keyword arguments forwarded to the adapter constructor.

    Returns
    -------
    A :class:`StructuredLLMAdapter` instance.
    """
    provider = (provider or "openai").lower().strip()

    if provider == "openai":
        return OpenAIStructuredAdapter(
            api_key=api_key,
            model=model,
            **kwargs,
        )

    if provider == "anthropic":
        return AnthropicStructuredAdapter(
            api_key=api_key,
            model=model,
            **kwargs,
        )

    raise ValueError(
        f"Unknown structured adapter provider '{provider}'.  "
        f"Supported: openai, anthropic"
    )
