# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Google Gemini provider for LLM and embedding operations.

Uses the Google GenAI SDK (google-genai) for accessing Gemini models.
Supports chat completions, text embeddings, vision, audio, tool calling,
and structured output via response_format translation.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, AsyncGenerator, List

from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import ProviderCapability, UnifiedAIProvider
from kaizen.providers.types import Message, StreamEvent

logger = logging.getLogger(__name__)


class GoogleGeminiProvider(UnifiedAIProvider):
    """Google Gemini provider for LLM and embedding operations.

    Prerequisites:
        * ``pip install google-genai``
        * ``GOOGLE_API_KEY`` or ``GEMINI_API_KEY`` environment variable
        * OR Vertex AI with ``GOOGLE_CLOUD_PROJECT``

    Supported LLM models:
        * gemini-2.5-flash (latest, recommended)
        * gemini-2.0-flash (fast, efficient)
        * gemini-1.5-pro (high capability)
        * gemini-1.5-flash (balanced)

    Supported embedding models:
        * text-embedding-004 (768 dimensions, recommended)
        * embedding-001 (768 dimensions, legacy)
    """

    MODELS = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ]

    def __init__(self, use_async: bool = False) -> None:
        super().__init__()
        self._use_async = use_async
        self._sync_client: Any = None
        self._async_client: Any = None
        self._model_cache: dict[str, dict[str, Any]] = {}

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        import os

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        self._available = bool(api_key or project)
        return self._available

    # ------------------------------------------------------------------
    # SPEC-02 capability declaration
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "google"

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.CHAT_SYNC,
            ProviderCapability.CHAT_ASYNC,
            ProviderCapability.CHAT_STREAM,
            ProviderCapability.TOOLS,
            ProviderCapability.STRUCTURED_OUTPUT,
            ProviderCapability.EMBEDDINGS,
            ProviderCapability.VISION,
            ProviderCapability.AUDIO,
            ProviderCapability.BYOK,
        }

    def _get_client(self) -> Any:
        if self._sync_client is not None:
            return self._sync_client
        try:
            import os

            from google import genai

            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

            if project:
                self._sync_client = genai.Client(
                    vertexai=True, project=project, location=location
                )
            elif api_key:
                self._sync_client = genai.Client(api_key=api_key)
            else:
                raise RuntimeError(
                    "No Google credentials found. Set GOOGLE_API_KEY, GEMINI_API_KEY, "
                    "or GOOGLE_CLOUD_PROJECT environment variable."
                )
            return self._sync_client
        except ImportError:
            raise RuntimeError(
                "Google GenAI library not installed. Install with: pip install google-genai"
            )

    def _convert_messages_to_contents(
        self, messages: List[Message]
    ) -> tuple[list, str | None]:
        from google.genai import types

        contents: list[Any] = []
        system_instruction: str | None = None

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                if isinstance(content, str):
                    system_instruction = content
                elif isinstance(content, list):
                    text_parts = [
                        item.get("text", "")
                        for item in content
                        if item.get("type") == "text"
                    ]
                    system_instruction = " ".join(text_parts)
                continue

            genai_role = "model" if role == "assistant" else "user"

            if isinstance(content, list):
                parts: list[Any] = []
                for item in content:
                    if item.get("type") == "text":
                        parts.append(types.Part.from_text(text=item.get("text", "")))
                    elif item.get("type") == "image":
                        if "path" in item:
                            from kaizen.nodes.ai.vision_utils import (
                                encode_image,
                                get_media_type,
                            )

                            base64_data = encode_image(item["path"])
                            media_type = get_media_type(item["path"])
                            parts.append(
                                types.Part.from_bytes(
                                    data=__import__("base64").b64decode(base64_data),
                                    mime_type=media_type,
                                )
                            )
                        elif "base64" in item:
                            media_type = item.get("media_type", "image/jpeg")
                            parts.append(
                                types.Part.from_bytes(
                                    data=__import__("base64").b64decode(item["base64"]),
                                    mime_type=media_type,
                                )
                            )
                    elif item.get("type") == "image_url":
                        url = item.get("image_url", {}).get("url", "")
                        if url.startswith("data:"):
                            import re

                            match = re.match(
                                r"data:([^;]+);base64,(.+)", url, re.DOTALL
                            )
                            if match:
                                media_type, base64_data = match.groups()
                                parts.append(
                                    types.Part.from_bytes(
                                        data=__import__("base64").b64decode(
                                            base64_data
                                        ),
                                        mime_type=media_type,
                                    )
                                )
                    elif item.get("type") == "audio":
                        if "path" in item:
                            from kaizen.nodes.ai.audio_utils import (
                                encode_audio,
                                get_audio_media_type,
                            )

                            base64_data = encode_audio(item["path"])
                            media_type = get_audio_media_type(item["path"])
                            parts.append(
                                types.Part.from_bytes(
                                    data=__import__("base64").b64decode(base64_data),
                                    mime_type=media_type,
                                )
                            )
                        elif "base64" in item:
                            media_type = item.get("media_type", "audio/mpeg")
                            parts.append(
                                types.Part.from_bytes(
                                    data=__import__("base64").b64decode(item["base64"]),
                                    mime_type=media_type,
                                )
                            )
                        elif "bytes" in item:
                            media_type = item.get("media_type", "audio/mpeg")
                            parts.append(
                                types.Part.from_bytes(
                                    data=item["bytes"], mime_type=media_type
                                )
                            )
                    elif item.get("type") == "audio_url":
                        url = item.get("audio_url", {}).get("url", "")
                        if url.startswith("data:audio"):
                            import re

                            match = re.match(
                                r"data:([^;]+);base64,(.+)", url, re.DOTALL
                            )
                            if match:
                                media_type, base64_data = match.groups()
                                parts.append(
                                    types.Part.from_bytes(
                                        data=__import__("base64").b64decode(
                                            base64_data
                                        ),
                                        mime_type=media_type,
                                    )
                                )
                    else:
                        content_type = item.get("type", "unknown")
                        import warnings

                        warnings.warn(
                            f"Unhandled content type '{content_type}' in message. "
                            "This content will be skipped. Supported types: text, image, image_url, audio, audio_url.",
                            UserWarning,
                            stacklevel=2,
                        )

                if parts:
                    contents.append(types.Content(role=genai_role, parts=parts))
            else:
                contents.append(
                    types.Content(
                        role=genai_role,
                        parts=[types.Part.from_text(text=content)],
                    )
                )

        return contents, system_instruction

    def _convert_tools(self, tools: list) -> list:
        if not tools:
            return []
        from google.genai import types

        function_declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                function_declarations.append(
                    types.FunctionDeclaration(
                        name=func.get("name", ""),
                        description=func.get("description", ""),
                        parameters=func.get("parameters", {}),
                    )
                )

        if function_declarations:
            return [types.Tool(function_declarations=function_declarations)]
        return []

    def _format_tool_calls(self, response: Any) -> list:
        tool_calls = []
        if not hasattr(response, "candidates") or not response.candidates:
            return tool_calls

        candidate = response.candidates[0]
        if not hasattr(candidate, "content") or not candidate.content:
            return tool_calls

        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append(
                    {
                        "id": f"call_{hashlib.md5(fc.name.encode()).hexdigest()[:8]}",
                        "type": "function",
                        "function": {
                            "name": fc.name,
                            "arguments": (
                                __import__("json").dumps(dict(fc.args))
                                if fc.args
                                else "{}"
                            ),
                        },
                    }
                )
        return tool_calls

    def _build_config_params(self, generation_config: dict) -> dict:
        config_params: dict[str, Any] = {}
        if "temperature" in generation_config:
            config_params["temperature"] = generation_config["temperature"]
        if "max_tokens" in generation_config:
            config_params["max_output_tokens"] = generation_config["max_tokens"]
        if "max_output_tokens" in generation_config:
            config_params["max_output_tokens"] = generation_config["max_output_tokens"]
        if "top_p" in generation_config:
            config_params["top_p"] = generation_config["top_p"]
        if "top_k" in generation_config:
            config_params["top_k"] = generation_config["top_k"]
        if "stop" in generation_config:
            config_params["stop_sequences"] = generation_config["stop"]

        response_format = generation_config.get("response_format")
        if response_format and isinstance(response_format, dict):
            response_type = response_format.get("type")
            if response_type == "json_schema":
                config_params["response_mime_type"] = "application/json"
                json_schema = response_format.get("json_schema", {})
                if "schema" in json_schema:
                    config_params["response_json_schema"] = json_schema["schema"]
            elif response_type == "json_object":
                config_params["response_mime_type"] = "application/json"

        return config_params

    def _extract_response(self, response: Any, model: str) -> dict[str, Any]:
        content_text = ""
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    content_text += part.text

        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = {
                "prompt_tokens": getattr(
                    response.usage_metadata, "prompt_token_count", 0
                ),
                "completion_tokens": getattr(
                    response.usage_metadata, "candidates_token_count", 0
                ),
                "total_tokens": getattr(
                    response.usage_metadata, "total_token_count", 0
                ),
            }

        finish_reason = "stop"
        if response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "finish_reason"):
                fr = str(candidate.finish_reason).lower()
                if "tool" in fr or "function" in fr:
                    finish_reason = "tool_calls"
                elif "max" in fr or "length" in fr:
                    finish_reason = "length"
                elif "safety" in fr:
                    finish_reason = "content_filter"

        return {
            "id": f"gemini-{hashlib.md5(content_text.encode()).hexdigest()[:12]}",
            "content": content_text,
            "role": "assistant",
            "model": model,
            "created": __import__("time").time(),
            "tool_calls": self._format_tool_calls(response),
            "finish_reason": finish_reason,
            "usage": usage,
            "metadata": {"provider": "google_gemini"},
        }

    def chat(self, messages: List[Message], **kwargs: Any) -> dict[str, Any]:
        try:
            from google.genai import types

            model = kwargs.get("model", "gemini-2.0-flash")
            generation_config = kwargs.get("generation_config", {})
            tools = kwargs.get("tools", [])

            per_request_api_key = kwargs.get("api_key")
            if per_request_api_key:
                from google import genai

                client = genai.Client(api_key=per_request_api_key)
            else:
                client = self._get_client()

            contents, system_instruction = self._convert_messages_to_contents(messages)
            config_params = self._build_config_params(generation_config)

            # SPEC-02 #340: Gemini API rejects response_mime_type/response_json_schema
            # when tools are present. Strip them and emit a WARN log so callers know.
            if tools and (
                "response_mime_type" in config_params
                or "response_json_schema" in config_params
            ):
                stripped_keys = [
                    k
                    for k in ("response_mime_type", "response_json_schema")
                    if k in config_params
                ]
                logger.warning(
                    "gemini.response_format_stripped stripped=%s reason=mutually_exclusive_with_tools",
                    stripped_keys,
                    extra={
                        "event": "gemini.response_format_stripped",
                        "reason": "mutually_exclusive_with_tools",
                        "stripped": stripped_keys,
                    },
                )
                config_params.pop("response_mime_type", None)
                config_params.pop("response_json_schema", None)

            request_config = types.GenerateContentConfig(**config_params)

            if system_instruction:
                request_config.system_instruction = system_instruction
            if tools:
                request_config.tools = self._convert_tools(tools)

            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=request_config,
            )
            return self._extract_response(response, model)

        except ImportError:
            raise RuntimeError(
                "Google GenAI library not installed. Install with: pip install google-genai"
            )
        except Exception as e:
            logger.error("Google Gemini error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Google Gemini"))

    async def chat_async(
        self, messages: List[Message], **kwargs: Any
    ) -> dict[str, Any]:
        try:
            from google.genai import types

            model = kwargs.get("model", "gemini-2.0-flash")
            generation_config = kwargs.get("generation_config", {})
            tools = kwargs.get("tools", [])

            per_request_api_key = kwargs.get("api_key")
            if per_request_api_key:
                from google import genai

                client = genai.Client(api_key=per_request_api_key)
            else:
                client = self._get_client()

            contents, system_instruction = self._convert_messages_to_contents(messages)
            config_params = self._build_config_params(generation_config)

            # SPEC-02 #340: Gemini API rejects response_mime_type/response_json_schema
            # when tools are present. Strip them and emit a WARN log so callers know.
            if tools and (
                "response_mime_type" in config_params
                or "response_json_schema" in config_params
            ):
                stripped_keys = [
                    k
                    for k in ("response_mime_type", "response_json_schema")
                    if k in config_params
                ]
                logger.warning(
                    "gemini.response_format_stripped stripped=%s reason=mutually_exclusive_with_tools",
                    stripped_keys,
                    extra={
                        "event": "gemini.response_format_stripped",
                        "reason": "mutually_exclusive_with_tools",
                        "stripped": stripped_keys,
                    },
                )
                config_params.pop("response_mime_type", None)
                config_params.pop("response_json_schema", None)

            request_config = types.GenerateContentConfig(**config_params)

            if system_instruction:
                request_config.system_instruction = system_instruction
            if tools:
                request_config.tools = self._convert_tools(tools)

            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=request_config,
            )
            return self._extract_response(response, model)

        except ImportError:
            raise RuntimeError(
                "Google GenAI library not installed. Install with: pip install google-genai"
            )
        except Exception as e:
            logger.error("Google Gemini async error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Google Gemini"))

    # ------------------------------------------------------------------
    # Chat (streaming) — SPEC-02 StreamingProvider protocol
    # ------------------------------------------------------------------

    async def stream_chat(
        self, messages: List[Message], **kwargs: Any
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream tokens from the Google GenAI async streaming endpoint.

        Iterates the real ``client.aio.models.generate_content_stream``
        response chunks, yielding a :class:`StreamEvent` for every incoming
        text delta and a final ``done`` event with accumulated text and
        usage metadata.
        """
        # Unconditional import — ModuleNotFoundError propagates as a clear
        # error instead of leaving ``types`` possibly unbound for Pyright.
        from google.genai import types

        model = kwargs.get("model", "gemini-2.0-flash")
        generation_config = dict(kwargs.get("generation_config", {}) or {})
        tools = kwargs.get("tools", [])

        per_request_api_key = kwargs.get("api_key")
        if per_request_api_key:
            from google import genai

            client = genai.Client(api_key=per_request_api_key)
        else:
            client = self._get_client()

        contents, system_instruction = self._convert_messages_to_contents(messages)
        config_params = self._build_config_params(generation_config)

        # #340 mutual exclusion — tools and response_json_schema are incompatible.
        if tools and (
            "response_mime_type" in config_params
            or "response_json_schema" in config_params
        ):
            stripped = [
                k
                for k in ("response_mime_type", "response_json_schema")
                if k in config_params
            ]
            logger.warning(
                "gemini.response_format_stripped stripped=%s reason=mutually_exclusive_with_tools",
                stripped,
                extra={
                    "event": "gemini.response_format_stripped",
                    "reason": "mutually_exclusive_with_tools",
                    "stripped": stripped,
                },
            )
            config_params.pop("response_mime_type", None)
            config_params.pop("response_json_schema", None)

        request_config = types.GenerateContentConfig(**config_params)
        if system_instruction:
            request_config.system_instruction = system_instruction
        if tools:
            request_config.tools = self._convert_tools(tools)

        logger.debug("google.stream_chat.start model=%s", model)

        accumulated_text = ""
        last_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        finish_reason = "stop"

        try:
            stream = await client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=request_config,
            )

            async for chunk in stream:
                # Gemini chunks expose a ``text`` attribute summarising the
                # new delta. Fall back to candidate.parts for safety.
                text_piece = getattr(chunk, "text", None)
                if not text_piece:
                    candidates = getattr(chunk, "candidates", None) or []
                    if candidates and getattr(candidates[0], "content", None):
                        parts = candidates[0].content.parts or []
                        text_piece = "".join(
                            getattr(p, "text", "") or "" for p in parts
                        )

                if text_piece:
                    accumulated_text += text_piece
                    yield StreamEvent(
                        event_type="text_delta",
                        delta_text=text_piece,
                        content=accumulated_text,
                        model=model,
                    )

                usage_metadata = getattr(chunk, "usage_metadata", None)
                if usage_metadata is not None:
                    last_usage = {
                        "prompt_tokens": getattr(
                            usage_metadata, "prompt_token_count", 0
                        )
                        or 0,
                        "completion_tokens": getattr(
                            usage_metadata, "candidates_token_count", 0
                        )
                        or 0,
                        "total_tokens": getattr(usage_metadata, "total_token_count", 0)
                        or 0,
                    }

                candidates = getattr(chunk, "candidates", None) or []
                if candidates:
                    fr = getattr(candidates[0], "finish_reason", None)
                    if fr is not None:
                        fr_str = str(fr).lower()
                        if "tool" in fr_str or "function" in fr_str:
                            finish_reason = "tool_calls"
                        elif "max" in fr_str or "length" in fr_str:
                            finish_reason = "length"
                        elif "safety" in fr_str:
                            finish_reason = "content_filter"
                        else:
                            finish_reason = "stop"

            logger.debug(
                "google.stream_chat.done model=%s chars=%d finish=%s",
                model,
                len(accumulated_text),
                finish_reason,
            )

            yield StreamEvent(
                event_type="done",
                content=accumulated_text,
                finish_reason=finish_reason,
                model=model,
                usage=last_usage,
            )
        except Exception as exc:  # pragma: no cover - re-raise sanitised
            logger.error("google.stream_chat.error error=%s", exc, exc_info=True)
            raise RuntimeError(sanitize_provider_error(exc, "Google Gemini"))

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        try:
            from google.genai import types

            model = kwargs.get("model", "text-embedding-004")
            task_type = kwargs.get("task_type")
            client = self._get_client()

            config_params: dict[str, Any] = {}
            if task_type:
                config_params["task_type"] = task_type
            config = (
                types.EmbedContentConfig(**config_params) if config_params else None
            )

            embeddings = []
            for text in texts:
                response = client.models.embed_content(
                    model=model, contents=text, config=config
                )
                if response.embeddings:
                    embeddings.append(list(response.embeddings[0].values))
                else:
                    embeddings.append([])
            return embeddings

        except ImportError:
            raise RuntimeError(
                "Google GenAI library not installed. Install with: pip install google-genai"
            )
        except Exception as e:
            logger.error("Google Gemini embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Google Gemini"))

    async def embed_async(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        try:
            from google.genai import types

            model = kwargs.get("model", "text-embedding-004")
            task_type = kwargs.get("task_type")
            client = self._get_client()

            config_params: dict[str, Any] = {}
            if task_type:
                config_params["task_type"] = task_type
            config = (
                types.EmbedContentConfig(**config_params) if config_params else None
            )

            embeddings = []
            for text in texts:
                response = await client.aio.models.embed_content(
                    model=model, contents=text, config=config
                )
                if response.embeddings:
                    embeddings.append(list(response.embeddings[0].values))
                else:
                    embeddings.append([])
            return embeddings

        except ImportError:
            raise RuntimeError(
                "Google GenAI library not installed. Install with: pip install google-genai"
            )
        except Exception as e:
            logger.error("Google Gemini async embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Google Gemini"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        if model in self._model_cache:
            return self._model_cache[model]

        known_models = {
            "text-embedding-004": {
                "dimensions": 768,
                "max_tokens": 2048,
                "description": "Google's latest text embedding model",
                "capabilities": {"variable_dimensions": False},
            },
            "embedding-001": {
                "dimensions": 768,
                "max_tokens": 2048,
                "description": "Google's legacy embedding model",
                "capabilities": {"variable_dimensions": False},
            },
        }

        if model in known_models:
            self._model_cache[model] = known_models[model]
            return known_models[model]

        return {
            "dimensions": 768,
            "max_tokens": 2048,
            "description": f"Google Gemini model: {model}",
            "capabilities": {},
        }
