"""
Thin LLM client abstraction for the kaizen-agents orchestration layer.

Wraps the OpenAI API for structured and unstructured completions. Model
selection reads from environment variables (.env is the single source of
truth per project rules).

Supported environment variables (checked in order):
    OPENAI_PROD_MODEL  -- production model name
    DEFAULT_LLM_MODEL  -- fallback model name
    (hardcoded)        -- "gpt-4o" if neither is set

Requires:
    OPENAI_API_KEY     -- must be set in the environment
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI


def _resolve_model() -> str:
    """Resolve the model name from environment variables.

    Priority:
        1. OPENAI_PROD_MODEL
        2. DEFAULT_LLM_MODEL
        3. "gpt-4o" (hardcoded fallback)
    """
    return (
        os.environ.get("OPENAI_PROD_MODEL")
        or os.environ.get("DEFAULT_LLM_MODEL")
        or "gpt-4o"
    )


@dataclass
class LLMResponse:
    """Wrapper around an LLM completion result.

    Attributes:
        content: The text content of the assistant's reply.
        tool_calls: Any tool calls the model wants to make (OpenAI format).
        raw: The raw response object from the provider for debugging.
        model: The model that generated this response.
        usage: Token usage dict with prompt_tokens, completion_tokens, total_tokens.
    """

    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: Any = None
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)


class LLMClient:
    """Thin wrapper around the OpenAI chat completion API.

    Provides two calling patterns:
        - complete(): Free-form completion with optional tool definitions
        - complete_structured(): JSON-schema-constrained structured output

    The client is stateless and safe to share across threads. Each call is
    independent.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        """Initialise the LLM client.

        Args:
            api_key: OpenAI API key. Falls back to OPENAI_API_KEY env var.
            model: Model name. Falls back to env-based resolution.
            base_url: Override base URL (for proxies or compatible APIs).
            temperature: Sampling temperature. Default 0.0 for deterministic output.
            max_tokens: Maximum tokens in the response.

        Raises:
            ValueError: If no API key is available.
        """
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "No OpenAI API key provided. Set OPENAI_API_KEY in your environment "
                "or pass api_key explicitly."
            )

        self._model = model or _resolve_model()
        self._temperature = temperature
        self._max_tokens = max_tokens

        client_kwargs: dict[str, Any] = {"api_key": resolved_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)

    @property
    def model(self) -> str:
        """The model name used for completions."""
        return self._model

    def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Run a single chat completion.

        Args:
            messages: List of message dicts with "role" and "content" keys.
            tools: Optional list of tool definitions in OpenAI function-calling format.
            response_format: Optional response format constraint (e.g. {"type": "json_object"}).
            temperature: Override the default temperature for this call.
            max_tokens: Override the default max_tokens for this call.

        Returns:
            An LLMResponse with the assistant's reply and any tool calls.
        """
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
                tool_calls_parsed.append(
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                )

        usage_dict: dict[str, int] = {}
        if response.usage:
            usage_dict = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls_parsed,
            raw=response,
            model=response.model,
            usage=usage_dict,
        )

    def complete_structured(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        schema_name: str = "response",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Run a chat completion with structured output (JSON schema).

        Uses OpenAI's structured output feature to constrain the response
        to match the provided JSON schema exactly.

        Args:
            messages: List of message dicts with "role" and "content" keys.
            schema: A JSON Schema dict defining the expected output structure.
            schema_name: Name for the schema (used in the API request).
            temperature: Override the default temperature for this call.
            max_tokens: Override the default max_tokens for this call.

        Returns:
            A parsed dict matching the provided schema.

        Raises:
            ValueError: If the model's response cannot be parsed as valid JSON.
        """
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        }

        llm_response = self.complete(
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = llm_response.content.strip()
        if not content:
            raise ValueError("LLM returned empty content for structured output request")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM response is not valid JSON: {exc}. Content: {content[:500]}"
            ) from exc

        if not isinstance(parsed, dict):
            raise ValueError(
                f"Expected a JSON object, got {type(parsed).__name__}: {content[:500]}"
            )

        return parsed
