"""Regression: ``kaizen.nodes.rag.similarity`` nodes crash on None content.

F8 shard B1 surfaced this defect. Six of the seven similarity retrieval nodes
extracted document content via ``doc.get("content", "")`` — but the ``""``
default applies ONLY when the key is MISSING. A document with the key present
and the value ``None`` (``{"content": None}``) returns ``None``, and the
subsequent ``.lower()`` / ``.split()`` raised ``AttributeError``. The broad
``except`` swallowed the crash into an ``error`` result key — a silent-fallback
defect: the node advertises graceful handling of malformed documents, and a
present-but-None content is malformed-but-present.

Fix: ``(doc.get("content") or "")`` coerces a None content to an empty string
on every scoring-path extraction site. ``HybridFusionNode`` was unaffected (it
only ``hash()``-es content, and ``hash(None)`` is valid).

These are behavioral regression tests: they call ``run()`` and assert the
absence of the ``error`` key plus correct scoring of the well-formed siblings.
"""

from __future__ import annotations

import pytest

from kaizen.nodes.rag.similarity import (
    ColBERTRetrievalNode,
    CrossEncoderRerankNode,
    DenseRetrievalNode,
    MultiVectorRetrievalNode,
    PropositionBasedRetrievalNode,
    SparseRetrievalNode,
)

pytestmark = pytest.mark.regression


_GOOD_DOC = {"content": "machine learning trains models on data", "id": "good"}
_NONE_DOC = {"content": None, "id": "none-content"}


@pytest.mark.parametrize(
    "node",
    [
        DenseRetrievalNode(),
        SparseRetrievalNode(),
        ColBERTRetrievalNode(),
        MultiVectorRetrievalNode(),
    ],
    ids=["dense", "sparse", "colbert", "multivector"],
)
def test_query_documents_node_handles_none_content(node):
    """Dense/Sparse/ColBERT/MultiVector: a None-content doc must not crash
    run() and must not poison the well-formed sibling's scoring."""
    result = node.run(
        query="machine learning",
        documents=[_NONE_DOC, _GOOD_DOC],
        k=5,
    )
    assert "error" not in result, f"None content crashed run(): {result.get('error')}"
    # The well-formed doc still scores and is returned; the None doc is dropped.
    assert {r["id"] for r in result["results"]} == {"good"}
    assert result["total_results"] == 1


def test_proposition_node_handles_none_content():
    result = PropositionBasedRetrievalNode().run(
        query="machine learning",
        documents=[
            _NONE_DOC,
            {"content": "Machine learning trains models on real data.", "id": "good"},
        ],
        k=5,
    )
    assert "error" not in result, f"None content crashed run(): {result.get('error')}"
    assert {r["id"] for r in result["results"]} == {"good"}


def test_cross_encoder_node_handles_none_content():
    result = CrossEncoderRerankNode().run(
        query="machine learning",
        initial_results={"results": [_NONE_DOC, _GOOD_DOC], "scores": [0.5, 0.9]},
        k=5,
    )
    assert "error" not in result, f"None content crashed run(): {result.get('error')}"
    # Cross-encoder reranks every input doc; both are returned, neither crashes.
    assert result["total_results"] == 2


def test_none_content_only_corpus_returns_empty_not_error():
    """A corpus consisting solely of None-content docs degrades to an empty
    result — NOT an error result."""
    result = DenseRetrievalNode().run(
        query="machine learning",
        documents=[_NONE_DOC, {"content": None, "id": "none-2"}],
        k=5,
    )
    assert "error" not in result
    assert result["results"] == []
    assert result["total_results"] == 0
