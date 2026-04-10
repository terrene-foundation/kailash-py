# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for OntologyRegistry -- embedding-backed concept classification.

Uses a deterministic mock EmbeddingProvider so tests run without
sentence-transformers or any network access.  The mock assigns each
unique text a distinct random-but-stable embedding vector (seeded),
which gives meaningful cosine similarity behaviour for the test
assertions.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from kaizen.ontology import OntologyRegistry
from kaizen.ontology.types import Concept, ConceptMatch, EmbeddingProvider

# ------------------------------------------------------------------
# Mock embedding provider
# ------------------------------------------------------------------


class _MockEmbeddingProvider:
    """Deterministic embedding provider for unit tests.

    Generates a 32-dim embedding per text using a seeded PRNG keyed on
    the text's hash.  Identical texts always produce identical vectors;
    different texts produce (almost certainly) different vectors.

    This satisfies the ``EmbeddingProvider`` protocol structurally.
    """

    DIMS = 32

    def __init__(self) -> None:
        self.call_count = 0
        self.last_texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        self.last_texts = texts
        result: list[list[float]] = []
        for text in texts:
            seed = int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**31)
            rng = np.random.RandomState(seed)
            vec = rng.randn(self.DIMS).astype(np.float64)
            # L2-normalize so cosine similarity == dot product
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            result.append(vec.tolist())
        return result


@pytest.fixture()
def provider() -> _MockEmbeddingProvider:
    return _MockEmbeddingProvider()


@pytest.fixture()
def registry(provider: _MockEmbeddingProvider) -> OntologyRegistry:
    return OntologyRegistry(provider=provider)


# ------------------------------------------------------------------
# Protocol conformance
# ------------------------------------------------------------------


def test_mock_satisfies_protocol(provider: _MockEmbeddingProvider) -> None:
    """The mock must satisfy the EmbeddingProvider protocol."""
    assert isinstance(provider, EmbeddingProvider)


# ------------------------------------------------------------------
# register / list / remove
# ------------------------------------------------------------------


def test_register_concept_returns_concept(registry: OntologyRegistry) -> None:
    concept = registry.register_concept("refund", "Customer wants money back")
    assert isinstance(concept, Concept)
    assert concept.name == "refund"
    assert concept.description == "Customer wants money back"
    assert concept.category is None
    assert concept.aliases == ()
    assert concept.embedding is not None
    assert len(concept.embedding) == _MockEmbeddingProvider.DIMS


def test_register_concept_with_category_and_aliases(
    registry: OntologyRegistry,
) -> None:
    concept = registry.register_concept(
        "refund",
        "Customer wants money back",
        category="billing",
        aliases=["money back", "return payment"],
    )
    assert concept.category == "billing"
    assert concept.aliases == ("money back", "return payment")


def test_register_empty_name_raises(registry: OntologyRegistry) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        registry.register_concept("", "some description")


def test_list_concepts_empty(registry: OntologyRegistry) -> None:
    assert registry.list_concepts() == []


def test_list_concepts_returns_all(registry: OntologyRegistry) -> None:
    registry.register_concept("a", "concept a")
    registry.register_concept("b", "concept b")
    registry.register_concept("c", "concept c")
    names = [c.name for c in registry.list_concepts()]
    assert names == ["a", "b", "c"]


def test_remove_concept_existing(registry: OntologyRegistry) -> None:
    registry.register_concept("refund", "Customer wants money back")
    assert registry.remove_concept("refund") is True
    assert registry.list_concepts() == []


def test_remove_concept_nonexistent(registry: OntologyRegistry) -> None:
    assert registry.remove_concept("nope") is False


def test_remove_preserves_other_concepts(registry: OntologyRegistry) -> None:
    registry.register_concept("a", "concept a")
    registry.register_concept("b", "concept b")
    registry.register_concept("c", "concept c")
    registry.remove_concept("b")
    names = [c.name for c in registry.list_concepts()]
    assert names == ["a", "c"]


def test_register_replaces_existing(registry: OntologyRegistry) -> None:
    registry.register_concept("x", "first version")
    registry.register_concept("x", "second version", category="updated")
    concepts = registry.list_concepts()
    assert len(concepts) == 1
    assert concepts[0].description == "second version"
    assert concepts[0].category == "updated"


# ------------------------------------------------------------------
# classify
# ------------------------------------------------------------------


def test_classify_empty_registry(registry: OntologyRegistry) -> None:
    assert registry.classify("anything") == []


def test_classify_returns_scored_matches(registry: OntologyRegistry) -> None:
    registry.register_concept("refund", "Customer wants a monetary refund")
    registry.register_concept("shipping", "Package delivery and tracking")
    registry.register_concept("account", "User account management")

    matches = registry.classify("refund", top_k=3, threshold=0.0)
    assert len(matches) > 0
    assert all(isinstance(m, ConceptMatch) for m in matches)
    # Best match for the literal word "refund" should be the refund concept
    # because the mock produces identical embeddings for identical text substrings
    # (the description contains "refund" but the query IS "refund")
    assert matches[0].score >= matches[-1].score  # sorted descending
    assert matches[0].matched_text == "refund"


def test_classify_threshold_filtering(registry: OntologyRegistry) -> None:
    registry.register_concept("a", "alpha concept about something")
    registry.register_concept("b", "beta concept about another thing")

    # With threshold=1.0, only exact embedding matches pass (practically none)
    matches = registry.classify("unrelated query text", threshold=1.0)
    assert matches == []


def test_classify_top_k_limits_results(registry: OntologyRegistry) -> None:
    for i in range(10):
        registry.register_concept(f"c{i}", f"concept number {i}")

    matches = registry.classify("concept", top_k=3, threshold=0.0)
    assert len(matches) <= 3


def test_classify_self_similarity(
    registry: OntologyRegistry, provider: _MockEmbeddingProvider
) -> None:
    """Classifying with the exact description text should produce score ~1.0."""
    desc = "Customer wants a monetary refund"
    registry.register_concept("refund", desc)
    matches = registry.classify(desc, top_k=1, threshold=0.0)
    assert len(matches) == 1
    assert matches[0].concept.name == "refund"
    # The mock produces identical embeddings for identical text, so cosine = 1.0
    assert matches[0].score == pytest.approx(1.0, abs=1e-5)


# ------------------------------------------------------------------
# classify_batch
# ------------------------------------------------------------------


def test_classify_batch_empty_texts(registry: OntologyRegistry) -> None:
    assert registry.classify_batch([]) == []


def test_classify_batch_empty_registry(registry: OntologyRegistry) -> None:
    result = registry.classify_batch(["a", "b"])
    assert result == [[], []]


def test_classify_batch_returns_per_text_results(
    registry: OntologyRegistry,
) -> None:
    registry.register_concept("billing", "Invoice and payment issues")
    registry.register_concept("tech", "Technical support and troubleshooting")

    results = registry.classify_batch(
        ["payment problem", "software crash"],
        top_k=2,
        threshold=0.0,
    )
    assert len(results) == 2
    assert all(isinstance(r, list) for r in results)
    assert all(isinstance(m, ConceptMatch) for r in results for m in r)
    # Each result should carry the correct matched_text
    for i, text in enumerate(["payment problem", "software crash"]):
        for m in results[i]:
            assert m.matched_text == text


# ------------------------------------------------------------------
# save / load persistence roundtrip
# ------------------------------------------------------------------


def test_save_load_roundtrip(
    registry: OntologyRegistry,
    provider: _MockEmbeddingProvider,
    tmp_path: Path,
) -> None:
    registry.register_concept(
        "refund",
        "Customer wants money back",
        category="billing",
        aliases=["money back"],
    )
    registry.register_concept("shipping", "Package delivery")

    save_path = tmp_path / "ontology.json"
    registry.save(save_path)

    # Load into a new registry (with the same provider for future ops)
    loaded = OntologyRegistry.load(save_path, provider=provider)

    # Concepts roundtrip
    assert len(loaded.list_concepts()) == 2
    names = {c.name for c in loaded.list_concepts()}
    assert names == {"refund", "shipping"}

    refund = next(c for c in loaded.list_concepts() if c.name == "refund")
    assert refund.category == "billing"
    assert refund.aliases == ("money back",)
    assert refund.embedding is not None

    # Classification still works on the loaded registry
    matches = loaded.classify("Customer wants money back", top_k=1, threshold=0.0)
    assert len(matches) == 1
    assert matches[0].concept.name == "refund"
    assert matches[0].score == pytest.approx(1.0, abs=1e-5)


def test_load_nonexistent_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        OntologyRegistry.load(tmp_path / "nope.json")


def test_load_invalid_version(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"version": 999}', encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported.*version"):
        OntologyRegistry.load(bad)


# ------------------------------------------------------------------
# aliases expand the match surface
# ------------------------------------------------------------------


def test_alias_expands_match_surface(
    registry: OntologyRegistry,
) -> None:
    """An alias text should match the parent concept with high score."""
    registry.register_concept(
        "refund",
        "Customer requesting a monetary refund",
        aliases=["money back"],
    )
    # Query with the exact alias text
    matches = registry.classify("money back", top_k=1, threshold=0.0)
    assert len(matches) == 1
    assert matches[0].concept.name == "refund"
    # Exact alias match => cosine ~ 1.0
    assert matches[0].score == pytest.approx(1.0, abs=1e-5)


# ------------------------------------------------------------------
# edge cases
# ------------------------------------------------------------------


def test_remove_then_classify(registry: OntologyRegistry) -> None:
    """Removing all concepts leaves classify returning empty."""
    registry.register_concept("a", "alpha")
    registry.remove_concept("a")
    assert registry.classify("alpha") == []


def test_frozen_dataclass_immutability() -> None:
    """Concept and ConceptMatch are frozen dataclasses."""
    c = Concept(name="x", description="desc")
    with pytest.raises(AttributeError):
        c.name = "y"  # type: ignore[misc]

    m = ConceptMatch(concept=c, score=0.5, matched_text="test")
    with pytest.raises(AttributeError):
        m.score = 0.9  # type: ignore[misc]
