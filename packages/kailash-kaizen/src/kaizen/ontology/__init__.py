# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Ontology module -- embedding-backed concept classification primitive.

Provides an in-memory concept registry that uses cosine similarity over
embeddings to classify free-text inputs against a known concept vocabulary.
Replaces brittle keyword/regex/dict lookups with semantic matching that
degrades gracefully when input schemas drift.

Quick start::

    from kaizen.ontology import OntologyRegistry

    registry = OntologyRegistry(provider=my_embedding_provider)
    registry.register_concept("refund", "Customer wants money back", category="billing")
    matches = registry.classify("I'd like to return this and get my money back")
"""

from kaizen.ontology.registry import OntologyRegistry
from kaizen.ontology.types import Concept, ConceptMatch, EmbeddingProvider

__all__ = [
    "Concept",
    "ConceptMatch",
    "EmbeddingProvider",
    "OntologyRegistry",
]
