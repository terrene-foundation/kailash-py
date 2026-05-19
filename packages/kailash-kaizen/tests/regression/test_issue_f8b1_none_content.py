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


# --------------------------------------------------------------------------
# Codegen-path coverage — the `_create_workflow()` PythonCodeNode templates
# --------------------------------------------------------------------------
#
# Each similarity node exposes a `_create_workflow()` that builds a workflow
# whose PythonCodeNode bodies are f-string code templates. Those templates
# carried the SAME `doc.get("content", "")` defect as the direct run() path
# (`calculate_bm25_scores` / `calculate_tfidf_scores` in the sparse template,
# `get_token_embeddings` + `create_multi_representations` in the colbert /
# multivector templates). A `{"content": None}` document routed through the
# generated code crashed with the identical `AttributeError`.
#
# The test executes the REAL generated code string (extracted from
# `_create_workflow()`) against a None-content corpus and asserts no crash.
# `_run_codegen_template` runs the exact code the template produces in a
# single namespace dict (globals == locals, so the template's nested function
# definitions resolve their free names correctly) and returns the `result`
# the template assigns.


def _run_codegen_template(code: str, **inputs: object) -> dict:
    """Execute a `_create_workflow()` PythonCodeNode code template.

    `code` is run with `inputs` pre-bound in a single namespace dict; the
    template's trailing `result = {...}` assignment is read back from that
    same dict and returned.
    """
    namespace: dict = dict(inputs)
    exec(code, namespace)  # noqa: S102 — executes the SDK's own generated template
    return namespace["result"]


def test_sparse_codegen_template_handles_none_content():
    """SparseRetrievalNode._create_workflow()'s sparse_retriever PythonCodeNode
    template (calculate_bm25_scores) must not crash on None-content docs."""
    wf = SparseRetrievalNode(use_query_expansion=False)._create_workflow()
    code = wf.nodes["sparse_retriever"].config["code"]
    corpus = [_NONE_DOC, {"content": "machine learning models train", "id": "g"}]
    result = _run_codegen_template(
        code, query_data={"query": "machine learning", "documents": corpus}
    )
    sparse_results = result["sparse_results"]
    # The well-formed doc still scores; the None-content doc is handled cleanly.
    assert sparse_results["total_matches"] == 1
    assert len(sparse_results["results"]) == 1


def test_colbert_codegen_template_handles_none_content():
    """ColBERTRetrievalNode._create_workflow()'s token_embedder PythonCodeNode
    template (get_token_embeddings) must not crash on None-content docs."""
    wf = ColBERTRetrievalNode()._create_workflow()
    code = wf.nodes["token_embedder"].config["code"]
    corpus = [_NONE_DOC, {"content": "machine learning", "id": "g"}]
    result = _run_codegen_template(
        code, input_data={"query": "machine learning", "documents": corpus}
    )
    token_data = result["token_data"]
    # Both docs are tokenised; the None-content doc yields an empty token list.
    assert len(token_data["doc_token_embeddings"]) == 2


def test_multivector_codegen_template_handles_none_content():
    """MultiVectorRetrievalNode._create_workflow()'s doc_processor PythonCodeNode
    template (create_multi_representations) must not crash on None-content."""
    wf = MultiVectorRetrievalNode()._create_workflow()
    code = wf.nodes["doc_processor"].config["code"]
    corpus = [_NONE_DOC, {"content": "machine learning models", "id": "g"}]
    result = _run_codegen_template(code, documents=corpus)
    multi_docs = result["multi_docs"]
    assert len(multi_docs) == 2
    # The None-content doc's representations are all empty strings, not None.
    none_doc = next(d for d in multi_docs if d["id"] == "none-content")
    assert none_doc["representations"]["full"] == ""
