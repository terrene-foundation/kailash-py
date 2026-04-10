# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Data types and protocols for the ontology registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Concept:
    """An immutable concept registered in the ontology.

    Attributes:
        name: Unique concept identifier (e.g. ``"refund"``).
        description: Human-readable description used to generate the
            concept's embedding.
        category: Optional grouping label (e.g. ``"billing"``).
        aliases: Additional surface forms that should map to this concept.
            Each alias generates its own embedding row so lookups against
            any phrasing resolve to the same concept.
        embedding: The embedding vector for the concept's description,
            stored as an immutable tuple.  ``None`` before the concept
            has been embedded.
    """

    name: str
    description: str
    category: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    embedding: tuple[float, ...] | None = None


@dataclass(frozen=True)
class ConceptMatch:
    """A scored match returned by :meth:`OntologyRegistry.classify`.

    Attributes:
        concept: The matched :class:`Concept`.
        score: Cosine similarity score in ``[0, 1]``.
        matched_text: The input text that produced this match.
    """

    concept: Concept
    score: float
    matched_text: str


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for pluggable embedding backends.

    Any object exposing an ``embed`` method with the signature below
    satisfies this protocol structurally -- no inheritance required.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text.

        Args:
            texts: Batch of strings to embed.

        Returns:
            List of embedding vectors (one per input text), each a list
            of floats.
        """
        ...  # pragma: no cover


class SentenceTransformerProvider:
    """Default :class:`EmbeddingProvider` backed by ``sentence-transformers``.

    ``sentence-transformers`` is an **optional** dependency.  The import
    is deferred to the first call to :meth:`embed` so that importing
    ``kaizen.ontology`` never fails.  If the package is missing, a loud
    :class:`ImportError` tells the user exactly how to install it.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None  # lazy-loaded

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "SentenceTransformerProvider requires the sentence-transformers "
                "package. Install it with:\n\n"
                "    pip install sentence-transformers\n\n"
                "Or supply a custom EmbeddingProvider to OntologyRegistry."
            )
        self._model = SentenceTransformer(self._model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed *texts* using a local sentence-transformer model."""
        self._ensure_model()
        embeddings = self._model.encode(  # type: ignore[union-attr]
            texts, convert_to_numpy=True, show_progress_bar=False
        )
        return embeddings.tolist()
