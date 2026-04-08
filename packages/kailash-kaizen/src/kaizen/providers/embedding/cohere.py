# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cohere provider for embedding operations.

Supports Cohere's embedding models including multilingual variants.
"""

from __future__ import annotations

import logging
from typing import Any

from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class CohereProvider(EmbeddingProvider):
    """Cohere provider for embedding operations.

    Prerequisites:
        * ``COHERE_API_KEY`` environment variable
        * ``pip install cohere``

    Supported embedding models:
        * embed-english-v3.0 (1024 dimensions)
        * embed-multilingual-v3.0 (1024 dimensions)
        * embed-english-light-v3.0 (384 dimensions)
        * embed-multilingual-light-v3.0 (384 dimensions)
    """

    MODELS = [
        "embed-english-v3.0",
        "embed-multilingual-v3.0",
        "embed-english-light-v3.0",
        "embed-multilingual-light-v3.0",
    ]

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        import os

        self._available = bool(os.getenv("COHERE_API_KEY"))
        return self._available

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        try:
            import cohere

            model = kwargs.get("model", "embed-english-v3.0")
            input_type = kwargs.get("input_type", "search_document")
            truncate = kwargs.get("truncate", "END")

            if self._client is None:
                self._client = cohere.Client()

            response = self._client.embed(
                texts=texts, model=model, input_type=input_type, truncate=truncate
            )
            return response.embeddings

        except ImportError:
            raise RuntimeError(
                "Cohere library not installed. Install with: pip install cohere"
            )
        except Exception as e:
            logger.error("Cohere embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Cohere"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        models = {
            "embed-english-v3.0": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "English embedding model v3",
                "capabilities": {
                    "input_types": [
                        "search_query",
                        "search_document",
                        "classification",
                        "clustering",
                    ],
                    "languages": ["en"],
                },
            },
            "embed-multilingual-v3.0": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "Multilingual embedding model v3",
                "capabilities": {
                    "input_types": [
                        "search_query",
                        "search_document",
                        "classification",
                        "clustering",
                    ],
                    "languages": [
                        "en",
                        "es",
                        "fr",
                        "de",
                        "it",
                        "pt",
                        "ja",
                        "ko",
                        "zh",
                        "ar",
                        "hi",
                        "tr",
                    ],
                },
            },
            "embed-english-light-v3.0": {
                "dimensions": 384,
                "max_tokens": 512,
                "description": "Lightweight English embedding model v3",
                "capabilities": {
                    "input_types": [
                        "search_query",
                        "search_document",
                        "classification",
                        "clustering",
                    ],
                    "languages": ["en"],
                },
            },
            "embed-multilingual-light-v3.0": {
                "dimensions": 384,
                "max_tokens": 512,
                "description": "Lightweight multilingual embedding model v3",
                "capabilities": {
                    "input_types": [
                        "search_query",
                        "search_document",
                        "classification",
                        "clustering",
                    ],
                    "languages": [
                        "en",
                        "es",
                        "fr",
                        "de",
                        "it",
                        "pt",
                        "ja",
                        "ko",
                        "zh",
                        "ar",
                        "hi",
                        "tr",
                    ],
                },
            },
        }
        return models.get(
            model,
            {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": f"Cohere embedding model: {model}",
                "capabilities": {},
            },
        )
