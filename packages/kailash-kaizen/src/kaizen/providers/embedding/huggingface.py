# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""HuggingFace provider for embedding operations.

Supports both the HuggingFace Inference API and local models via
transformers + torch.
"""

from __future__ import annotations

import logging
from typing import Any

from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class HuggingFaceProvider(EmbeddingProvider):
    """HuggingFace provider for embedding operations.

    Prerequisites for API:
        * ``HUGGINGFACE_API_KEY`` environment variable
        * ``pip install requests``

    Prerequisites for local:
        * ``pip install transformers torch``

    Supported embedding models:
        * sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)
        * sentence-transformers/all-mpnet-base-v2 (768 dimensions)
        * BAAI/bge-large-en-v1.5 (1024 dimensions)
        * thenlper/gte-large (1024 dimensions)
    """

    MODELS = [
        "sentence-transformers/all-MiniLM-L6-v2",
        "sentence-transformers/all-mpnet-base-v2",
        "BAAI/bge-large-en-v1.5",
        "thenlper/gte-large",
    ]

    def __init__(self) -> None:
        super().__init__()
        self._models: dict[str, Any] = {}
        self._available_api: bool | None = None
        self._available_local: bool | None = None

    def is_available(self) -> bool:
        if self._available_api is None:
            try:
                import os

                self._available_api = bool(os.getenv("HUGGINGFACE_API_KEY"))
            except Exception:
                self._available_api = False

        if self._available_local is None:
            try:
                import importlib.util

                torch_spec = importlib.util.find_spec("torch")
                transformers_spec = importlib.util.find_spec("transformers")
                self._available_local = (
                    torch_spec is not None and transformers_spec is not None
                )
            except ImportError:
                self._available_local = False

        return self._available_api or self._available_local

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        model = kwargs.get("model", "sentence-transformers/all-MiniLM-L6-v2")
        use_api = kwargs.get("use_api", self._available_api)
        normalize = kwargs.get("normalize", True)

        if use_api and self._available_api:
            return self._embed_api(texts, model, normalize)
        elif self._available_local:
            device = kwargs.get("device", "cpu")
            return self._embed_local(texts, model, device, normalize)
        else:
            raise RuntimeError(
                "Neither HuggingFace API nor local transformers available"
            )

    def _embed_api(
        self, texts: list[str], model: str, normalize: bool
    ) -> list[list[float]]:
        try:
            import os

            import requests

            api_key = os.getenv("HUGGINGFACE_API_KEY")
            headers = {"Authorization": f"Bearer {api_key}"}
            api_url = f"https://api-inference.huggingface.co/models/{model}"

            embeddings = []
            for text in texts:
                response = requests.post(
                    api_url, headers=headers, json={"inputs": text}
                )
                if response.status_code != 200:
                    raise RuntimeError(
                        f"HuggingFace API error: HTTP {response.status_code}"
                    )

                embedding = response.json()
                if isinstance(embedding, list) and isinstance(embedding[0], list):
                    embedding = embedding[0]

                if normalize:
                    magnitude = sum(x * x for x in embedding) ** 0.5
                    if magnitude > 0:
                        embedding = [x / magnitude for x in embedding]

                embeddings.append(embedding)
            return embeddings

        except Exception as e:
            logger.error("HuggingFace API error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "HuggingFace"))

    def _embed_local(
        self, texts: list[str], model: str, device: str, normalize: bool
    ) -> list[list[float]]:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            if model not in self._models:
                tokenizer = AutoTokenizer.from_pretrained(model)
                model_obj = AutoModel.from_pretrained(model)
                model_obj.to(device)
                # Switch PyTorch model to evaluation mode (not Python eval)
                model_obj.train(False)
                self._models[model] = (tokenizer, model_obj)

            tokenizer, model_obj = self._models[model]

            embeddings = []
            with torch.no_grad():
                for text in texts:
                    inputs = tokenizer(
                        text, padding=True, truncation=True, return_tensors="pt"
                    ).to(device)
                    outputs = model_obj(**inputs)

                    attention_mask = inputs["attention_mask"]
                    token_embeddings = outputs.last_hidden_state
                    input_mask_expanded = (
                        attention_mask.unsqueeze(-1)
                        .expand(token_embeddings.size())
                        .float()
                    )
                    embedding = torch.sum(
                        token_embeddings * input_mask_expanded, 1
                    ) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)
                    embedding = embedding.squeeze().cpu().numpy().tolist()

                    if normalize:
                        magnitude = sum(x * x for x in embedding) ** 0.5
                        if magnitude > 0:
                            embedding = [x / magnitude for x in embedding]

                    embeddings.append(embedding)
            return embeddings

        except ImportError:
            raise RuntimeError(
                "Transformers library not installed. Install with: pip install transformers torch"
            )
        except Exception as e:
            logger.error("HuggingFace local error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "HuggingFace"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        models = {
            "sentence-transformers/all-MiniLM-L6-v2": {
                "dimensions": 384,
                "max_tokens": 256,
                "description": "Efficient sentence transformer model",
                "capabilities": {
                    "languages": ["en"],
                    "use_cases": ["semantic_search", "clustering", "classification"],
                },
            },
            "sentence-transformers/all-mpnet-base-v2": {
                "dimensions": 768,
                "max_tokens": 384,
                "description": "High-quality sentence transformer model",
                "capabilities": {
                    "languages": ["en"],
                    "use_cases": ["semantic_search", "clustering", "classification"],
                },
            },
            "BAAI/bge-large-en-v1.5": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "BAAI General Embedding model",
                "capabilities": {
                    "languages": ["en"],
                    "use_cases": ["retrieval", "reranking", "classification"],
                },
            },
            "thenlper/gte-large": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "General Text Embeddings model",
                "capabilities": {
                    "languages": ["en"],
                    "use_cases": ["retrieval", "similarity", "clustering"],
                },
            },
        }
        return models.get(
            model,
            {
                "dimensions": 768,
                "max_tokens": 512,
                "description": f"HuggingFace model: {model}",
                "capabilities": {},
            },
        )
