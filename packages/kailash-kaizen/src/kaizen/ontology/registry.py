# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""OntologyRegistry -- embedding-backed concept classification primitive.

Replaces keyword/regex/dict classification with cosine-similarity lookup
over an in-memory concept vocabulary.  Uses numpy for brute-force cosine
similarity, which is fast enough for < 10K concepts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from kaizen.ontology.types import (
    Concept,
    ConceptMatch,
    EmbeddingProvider,
    SentenceTransformerProvider,
)

logger = logging.getLogger(__name__)


class OntologyRegistry:
    """In-memory concept registry with embedding-backed classification.

    The registry stores :class:`Concept` objects, embeds their descriptions
    (and aliases) via a pluggable :class:`EmbeddingProvider`, and answers
    ``classify`` queries by cosine similarity over the stored embeddings.

    Args:
        provider: An :class:`EmbeddingProvider` instance.  Defaults to
            :class:`SentenceTransformerProvider` (requires the optional
            ``sentence-transformers`` package).

    Example::

        from kaizen.ontology import OntologyRegistry

        registry = OntologyRegistry(provider=my_provider)
        registry.register_concept(
            "refund", "Customer requesting a monetary refund",
            category="billing", aliases=["money back", "return payment"],
        )
        matches = registry.classify("I want my money back please")
        print(matches[0].concept.name, matches[0].score)
    """

    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self._provider: EmbeddingProvider = provider or SentenceTransformerProvider()
        # Concept name -> Concept (canonical store)
        self._concepts: dict[str, Concept] = {}
        # Parallel arrays: one embedding row per (concept, text) pair.
        # _index_concepts[i] is the concept name for row i.
        self._index_concepts: list[str] = []
        self._index_texts: list[str] = []
        self._embeddings: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_concept(
        self,
        name: str,
        description: str,
        category: str | None = None,
        aliases: list[str] | None = None,
    ) -> Concept:
        """Register a new concept (or replace an existing one).

        The concept's description and every alias are embedded immediately.

        Args:
            name: Unique concept name.
            description: Natural-language description (used for embedding).
            category: Optional grouping label.
            aliases: Optional list of surface-form synonyms.

        Returns:
            The newly created :class:`Concept`.

        Raises:
            ValueError: If *name* is empty.
        """
        if not name:
            raise ValueError("Concept name must not be empty")

        alias_tuple = tuple(aliases) if aliases else ()

        # If the concept already exists, remove its index rows first so
        # we can re-embed cleanly.
        if name in self._concepts:
            self._remove_index_rows(name)

        # Build the list of texts to embed: description + aliases
        texts_to_embed = [description] + list(alias_tuple)
        embeddings = self._provider.embed(texts_to_embed)
        description_embedding = tuple(embeddings[0])

        concept = Concept(
            name=name,
            description=description,
            category=category,
            aliases=alias_tuple,
            embedding=description_embedding,
        )
        self._concepts[name] = concept

        # Append rows to the parallel index arrays
        new_vectors = np.array(embeddings, dtype=np.float32)
        for i, text in enumerate(texts_to_embed):
            self._index_concepts.append(name)
            self._index_texts.append(text)

        if self._embeddings is None:
            self._embeddings = new_vectors
        else:
            self._embeddings = np.vstack([self._embeddings, new_vectors])

        logger.info(
            "ontology.concept.registered",
            extra={
                "concept": name,
                "category": category,
                "alias_count": len(alias_tuple),
                "index_rows": len(texts_to_embed),
            },
        )
        return concept

    def classify(
        self,
        text: str,
        *,
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> list[ConceptMatch]:
        """Classify a single text against the registered concepts.

        Args:
            text: Free-text input to classify.
            top_k: Maximum number of matches to return.
            threshold: Minimum cosine similarity to include in results.

        Returns:
            Scored :class:`ConceptMatch` list, sorted descending by score.
            Empty if no concepts are registered or nothing exceeds the
            threshold.
        """
        if self._embeddings is None or len(self._index_concepts) == 0:
            return []

        query_embedding = np.array(self._provider.embed([text])[0], dtype=np.float32)
        similarities = _cosine_similarity(query_embedding, self._embeddings)

        return self._build_matches(similarities, text, top_k=top_k, threshold=threshold)

    def classify_batch(
        self,
        texts: list[str],
        *,
        top_k: int = 3,
        threshold: float = 0.3,
    ) -> list[list[ConceptMatch]]:
        """Classify multiple texts in a single embedding call.

        Args:
            texts: List of free-text inputs.
            top_k: Maximum matches per input.
            threshold: Minimum cosine similarity per match.

        Returns:
            One :class:`ConceptMatch` list per input text.
        """
        if not texts:
            return []
        if self._embeddings is None or len(self._index_concepts) == 0:
            return [[] for _ in texts]

        query_embeddings = np.array(self._provider.embed(texts), dtype=np.float32)

        results: list[list[ConceptMatch]] = []
        for i, text in enumerate(texts):
            sims = _cosine_similarity(query_embeddings[i], self._embeddings)
            results.append(
                self._build_matches(sims, text, top_k=top_k, threshold=threshold)
            )
        return results

    def remove_concept(self, name: str) -> bool:
        """Remove a concept by name.

        Args:
            name: The concept name to remove.

        Returns:
            ``True`` if the concept existed and was removed, ``False``
            otherwise.
        """
        if name not in self._concepts:
            return False

        self._remove_index_rows(name)
        del self._concepts[name]

        logger.info(
            "ontology.concept.removed",
            extra={"concept": name},
        )
        return True

    def list_concepts(self) -> list[Concept]:
        """Return all registered concepts in insertion order."""
        return list(self._concepts.values())

    def save(self, path: Path) -> None:
        """Persist the registry to a JSON file.

        The file contains the concept metadata **and** their embeddings so
        that :meth:`load` can reconstruct the registry without re-embedding.

        Args:
            path: Destination file path (parent directory must exist).
        """
        data: dict[str, Any] = {
            "version": 1,
            "concepts": [],
            "index_concepts": self._index_concepts,
            "index_texts": self._index_texts,
            "embeddings": (
                self._embeddings.tolist() if self._embeddings is not None else []
            ),
        }
        for concept in self._concepts.values():
            data["concepts"].append(
                {
                    "name": concept.name,
                    "description": concept.description,
                    "category": concept.category,
                    "aliases": list(concept.aliases),
                    "embedding": (
                        list(concept.embedding) if concept.embedding else None
                    ),
                }
            )

        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(
            "ontology.registry.saved",
            extra={"path": str(path), "concept_count": len(self._concepts)},
        )

    @classmethod
    def load(
        cls, path: Path, provider: EmbeddingProvider | None = None
    ) -> "OntologyRegistry":
        """Load a registry from a JSON file created by :meth:`save`.

        The provider is only needed for subsequent ``register_concept``
        or ``classify`` calls that require new embeddings.  The loaded
        embeddings are used as-is.

        Args:
            path: Source file path.
            provider: Optional embedding provider for future operations.

        Returns:
            A reconstructed :class:`OntologyRegistry`.

        Raises:
            FileNotFoundError: If *path* does not exist.
            ValueError: If the file format is invalid.
        """
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("version")
        if version != 1:
            raise ValueError(f"Unsupported ontology registry format version: {version}")

        registry = cls(provider=provider)

        for entry in raw["concepts"]:
            embedding = tuple(entry["embedding"]) if entry.get("embedding") else None
            concept = Concept(
                name=entry["name"],
                description=entry["description"],
                category=entry.get("category"),
                aliases=tuple(entry.get("aliases", [])),
                embedding=embedding,
            )
            registry._concepts[concept.name] = concept

        registry._index_concepts = raw["index_concepts"]
        registry._index_texts = raw["index_texts"]
        embeddings_list = raw.get("embeddings", [])
        if embeddings_list:
            registry._embeddings = np.array(embeddings_list, dtype=np.float32)
        else:
            registry._embeddings = None

        logger.info(
            "ontology.registry.loaded",
            extra={"path": str(path), "concept_count": len(registry._concepts)},
        )
        return registry

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _remove_index_rows(self, name: str) -> None:
        """Remove all index rows belonging to *name*."""
        keep = [i for i, n in enumerate(self._index_concepts) if n != name]
        self._index_concepts = [self._index_concepts[i] for i in keep]
        self._index_texts = [self._index_texts[i] for i in keep]
        if self._embeddings is not None and keep:
            self._embeddings = self._embeddings[keep]
        elif not keep:
            self._embeddings = None

    def _build_matches(
        self,
        similarities: np.ndarray,
        text: str,
        *,
        top_k: int,
        threshold: float,
    ) -> list[ConceptMatch]:
        """Deduplicate by concept name (keep best score) and rank."""
        # Best score per concept
        best: dict[str, float] = {}
        for i, score in enumerate(similarities):
            cname = self._index_concepts[i]
            if score >= threshold:
                if cname not in best or score > best[cname]:
                    best[cname] = float(score)

        # Sort by score descending, take top_k
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return [
            ConceptMatch(
                concept=self._concepts[cname],
                score=score,
                matched_text=text,
            )
            for cname, score in ranked
        ]


# ------------------------------------------------------------------
# Numpy cosine similarity helper
# ------------------------------------------------------------------


def _cosine_similarity(query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between a single query and a matrix of docs.

    Both inputs are expected to be 1-D (query) and 2-D (docs x dim).
    Returns a 1-D array of similarities, one per doc row.
    """
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0.0:
        return np.zeros(doc_vecs.shape[0], dtype=np.float32)

    doc_norms = np.linalg.norm(doc_vecs, axis=1)
    # Avoid division by zero for any zero-vector rows
    safe_norms = np.where(doc_norms == 0.0, 1.0, doc_norms)

    similarities = np.dot(doc_vecs, query_vec) / (safe_norms * query_norm)
    # Zero out rows that had zero-norm docs
    similarities = np.where(doc_norms == 0.0, 0.0, similarities)
    return similarities
