# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Ollama provider for local LLM and embedding operations.

Runs models locally via Ollama with support for both chat and embedding
operations using various open-source models.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, List

from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import ProviderCapability, UnifiedAIProvider
from kaizen.providers.types import Message, StreamEvent

logger = logging.getLogger(__name__)


class OllamaProvider(UnifiedAIProvider):
    """Ollama provider for both LLM and embedding operations.

    Prerequisites:
        * Install Ollama: https://ollama.ai
        * Pull models: ``ollama pull llama3.1:8b-instruct-q8_0``
        * Ensure Ollama service is running

    Supported LLM models:
        * llama3.1:* (various quantizations)
        * mixtral:* (various quantizations)
        * mistral:* (various quantizations)
        * qwen2.5:* (various sizes and quantizations)

    Supported embedding models:
        * snowflake-arctic-embed2 (1024 dimensions)
        * avr/sfr-embedding-mistral (4096 dimensions)
        * nomic-embed-text (768 dimensions)
        * mxbai-embed-large (1024 dimensions)
    """

    MODELS = ["llama3.1:*", "mixtral:*", "mistral:*", "qwen2.5:*"]

    def __init__(self) -> None:
        super().__init__()
        self._model_cache: dict[str, dict[str, Any]] = {}

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import os

            import ollama

            host = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST")
            client = ollama.Client(host=host) if host else ollama.Client()
            client.list()
            self._available = True
        except Exception:
            self._available = False
        return self._available

    # ------------------------------------------------------------------
    # SPEC-02 capability declaration
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.CHAT_SYNC,
            ProviderCapability.CHAT_ASYNC,
            ProviderCapability.CHAT_STREAM,
            ProviderCapability.EMBEDDINGS,
            ProviderCapability.VISION,
        }

    def _get_client(self, backend_config: dict[str, Any] | None = None) -> Any:
        """Get or create an Ollama client."""
        import os

        import ollama

        if backend_config:
            host = backend_config.get("host", "localhost")
            port = backend_config.get("port")
            if port:
                host = (
                    f"http://{host}:{port}"
                    if not host.startswith("http")
                    else f"{host}:{port}"
                )
            elif backend_config.get("base_url"):
                host = backend_config["base_url"]
            return ollama.Client(host=host)

        if self._client is None:
            host = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST")
            self._client = ollama.Client(host=host) if host else ollama.Client()
        return self._client

    def chat(self, messages: List[Message], **kwargs: Any) -> dict[str, Any]:
        try:
            import ollama

            model = kwargs.get("model", "llama3.1:8b-instruct-q8_0")
            generation_config = kwargs.get("generation_config", {})
            backend_config = kwargs.get("backend_config", {})

            per_request_base_url = kwargs.get("base_url")
            if per_request_base_url and not backend_config:
                backend_config = {"base_url": per_request_base_url}

            if backend_config:
                self._client = self._get_client(backend_config)
            elif self._client is None:
                self._get_client()

            options = {
                "temperature": generation_config.get("temperature", 0.7),
                "top_p": generation_config.get("top_p", 0.9),
                "top_k": generation_config.get("top_k"),
                "repeat_penalty": generation_config.get("repeat_penalty"),
                "seed": generation_config.get("seed"),
                "stop": generation_config.get("stop"),
                "tfs_z": generation_config.get("tfs_z", 1.0),
                "num_predict": generation_config.get("max_tokens", 500),
                "num_ctx": generation_config.get("num_ctx"),
                "num_batch": generation_config.get("num_batch"),
                "num_thread": generation_config.get("num_thread"),
                "typical_p": generation_config.get("typical_p"),
                "mirostat": generation_config.get("mirostat"),
                "mirostat_tau": generation_config.get("mirostat_tau"),
                "mirostat_eta": generation_config.get("mirostat_eta"),
            }
            options = {k: v for k, v in options.items() if v is not None}

            processed_messages = self._process_messages(messages)

            response = self._client.chat(
                model=model, messages=processed_messages, options=options
            )

            prompt_tokens = response.get("prompt_eval_count") or 0
            completion_tokens = response.get("eval_count") or 0

            return {
                "id": f"ollama_{hash(str(messages))}",
                "content": response["message"]["content"],
                "role": "assistant",
                "model": model,
                "created": response.get("created_at"),
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                "metadata": {
                    "duration_ms": (response.get("total_duration") or 0) / 1e6,
                    "load_duration_ms": (response.get("load_duration") or 0) / 1e6,
                    "eval_duration_ms": (response.get("eval_duration") or 0) / 1e6,
                },
            }

        except ImportError:
            raise RuntimeError(
                "Ollama library not installed. Install with: pip install ollama"
            )
        except Exception as e:
            logger.error("Ollama error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Ollama"))

    # ------------------------------------------------------------------
    # Chat (streaming) — SPEC-02 StreamingProvider protocol
    # ------------------------------------------------------------------

    async def stream_chat(
        self, messages: List[Message], **kwargs: Any
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream tokens from the Ollama async chat endpoint.

        Uses ``ollama.AsyncClient`` with ``stream=True`` to iterate the real
        per-token deltas emitted by the local Ollama service.
        """
        import os

        import ollama

        model = kwargs.get("model", "llama3.1:8b-instruct-q8_0")
        generation_config = dict(kwargs.get("generation_config", {}) or {})
        backend_config = kwargs.get("backend_config") or {}

        per_request_base_url = kwargs.get("base_url")
        host: str | None = None
        if per_request_base_url:
            host = per_request_base_url
        elif backend_config.get("base_url"):
            host = backend_config["base_url"]
        else:
            host = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST")

        async_client = ollama.AsyncClient(host=host) if host else ollama.AsyncClient()

        options = {
            "temperature": generation_config.get("temperature"),
            "top_p": generation_config.get("top_p"),
            "top_k": generation_config.get("top_k"),
            "repeat_penalty": generation_config.get("repeat_penalty"),
            "seed": generation_config.get("seed"),
            "stop": generation_config.get("stop"),
            "num_predict": generation_config.get("max_tokens"),
            "num_ctx": generation_config.get("num_ctx"),
        }
        options = {k: v for k, v in options.items() if v is not None}

        processed_messages = self._process_messages(messages)

        logger.debug(
            "ollama.stream_chat.start model=%s host=%s", model, host or "default"
        )

        accumulated_text = ""
        prompt_tokens = 0
        completion_tokens = 0
        finish_reason = "stop"

        try:
            stream = await async_client.chat(
                model=model,
                messages=processed_messages,
                options=options,
                stream=True,
            )

            async for chunk in stream:
                msg = chunk.get("message") if isinstance(chunk, dict) else None
                text_piece = msg.get("content") if msg else None
                if text_piece:
                    accumulated_text += text_piece
                    yield StreamEvent(
                        event_type="text_delta",
                        delta_text=text_piece,
                        content=accumulated_text,
                        model=model,
                    )
                # Final chunk carries the done flag and counters.
                if isinstance(chunk, dict) and chunk.get("done"):
                    prompt_tokens = chunk.get("prompt_eval_count") or 0
                    completion_tokens = chunk.get("eval_count") or 0
                    done_reason = chunk.get("done_reason")
                    if done_reason:
                        finish_reason = str(done_reason)

            logger.debug(
                "ollama.stream_chat.done model=%s chars=%d prompt_tokens=%d completion_tokens=%d",
                model,
                len(accumulated_text),
                prompt_tokens,
                completion_tokens,
            )

            yield StreamEvent(
                event_type="done",
                content=accumulated_text,
                finish_reason=finish_reason,
                model=model,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            )
        except Exception as exc:  # pragma: no cover - re-raise sanitised
            logger.error("ollama.stream_chat.error error=%s", exc, exc_info=True)
            raise RuntimeError(sanitize_provider_error(exc, "Ollama"))

    def _process_messages(self, messages: List[Message]) -> list:
        """Process messages for vision content."""
        processed = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                text_parts: list[str] = []
                images: list[bytes] = []
                for item in msg["content"]:
                    if item["type"] == "text":
                        text_parts.append(item["text"])
                    elif item["type"] == "image":
                        from kaizen.nodes.ai.vision_utils import encode_image

                        if "path" in item:
                            with open(item["path"], "rb") as f:
                                images.append(f.read())
                        else:
                            import base64

                            base64_data = item.get("base64", "")
                            images.append(base64.b64decode(base64_data))
                    else:
                        content_type = item.get("type", "unknown")
                        if content_type not in ("text", "image"):
                            import warnings

                            warnings.warn(
                                f"Unhandled content type '{content_type}' in OllamaProvider. "
                                "Only 'text' and 'image' are supported. This content will be skipped.",
                                UserWarning,
                                stacklevel=2,
                            )

                message_dict: dict[str, Any] = {
                    "role": msg["role"],
                    "content": " ".join(text_parts),
                }
                if images:
                    message_dict["images"] = images
                processed.append(message_dict)
            else:
                processed.append(msg)
        return processed

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        try:
            import ollama

            model = kwargs.get("model", "snowflake-arctic-embed2")
            normalize = kwargs.get("normalize", False)
            backend_config = kwargs.get("backend_config", {})

            if backend_config and not hasattr(self, "_client"):
                self._client = self._get_client(backend_config)
            elif not hasattr(self, "_client") or self._client is None:
                self._get_client()

            embeddings = []
            for text in texts:
                response = self._client.embeddings(model=model, prompt=text)
                embedding = response.get("embedding", [])

                if normalize and embedding:
                    magnitude = sum(x * x for x in embedding) ** 0.5
                    if magnitude > 0:
                        embedding = [x / magnitude for x in embedding]

                embeddings.append(embedding)
            return embeddings

        except ImportError:
            raise RuntimeError(
                "Ollama library not installed. Install with: pip install ollama"
            )
        except Exception as e:
            logger.error("Ollama embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Ollama"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        if model in self._model_cache:
            return self._model_cache[model]

        known_models = {
            "snowflake-arctic-embed2": {"dimensions": 1024, "max_tokens": 512},
            "avr/sfr-embedding-mistral": {"dimensions": 4096, "max_tokens": 512},
            "nomic-embed-text": {"dimensions": 768, "max_tokens": 8192},
            "mxbai-embed-large": {"dimensions": 1024, "max_tokens": 512},
        }

        if model in known_models:
            info = known_models[model].copy()
            info["description"] = f"Ollama embedding model: {model}"
            info["capabilities"] = {
                "batch_processing": True,
                "gpu_acceleration": True,
                "normalize": True,
            }
            self._model_cache[model] = info
            return info

        return {
            "dimensions": 1536,
            "max_tokens": 512,
            "description": f"Ollama model: {model}",
            "capabilities": {"batch_processing": True},
        }
