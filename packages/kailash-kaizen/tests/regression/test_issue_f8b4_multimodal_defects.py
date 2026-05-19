"""Regression: latent ``kaizen.nodes.rag.multimodal`` crashes on malformed input.

F8 shard B4 surfaced six crash sites across the three multimodal RAG node
classes via behavioral coverage — three in ``run()`` paths, three in the
``MultimodalRAGNode`` ``_create_workflow()`` codegen templates. Per the
B1/B2/B3 two-path lesson, both the ``run()`` paths and the ``code=`` codegen
templates were grepped for each pattern and fixed in the same shard.

Defect 1 — VisualQuestionAnsweringNode.run() None-question crash.
  ``run()`` did ``kwargs.get("question", "")`` then ``question.lower()``. The
  ``""`` default applies ONLY to a MISSING key; an explicit ``question=None``
  returned ``None`` and ``.lower()`` raised ``AttributeError``.
  Fix: ``kwargs.get("question") or ""``.

Defect 2 — ImageTextMatchingNode.run() non-dict collection-element crash.
  ``run()`` iterated ``collection`` calling ``item.get("tags", ...)``. A
  non-dict element (collections are arbitrary user input) raised
  ``AttributeError`` ('str' object has no attribute 'get').
  Fix: ``isinstance(item, dict)`` skip; ``total_searched`` still reports the
  raw collection length.

Defect 3 — doc_preprocessor codegen non-dict / None-content crash.
  The ``doc_preprocessor`` ``code=`` template iterated ``documents`` calling
  ``doc.get("type", ...)`` (loop body) AND a stats-block list comprehension
  ``[d for d in documents if d.get("type") == "multimodal"]`` — two non-dict
  crash sites. Content keys also used ``doc.get("content", "")`` (None-bypass).
  Fix: ``isinstance`` guards on both sites; ``doc.get("content") or ""``.

Defect 4 — multimodal_encoder codegen None-image-path crash.
  ``image_encoder(image_path)`` did ``image_path.lower()``; a present-but-None
  ``path`` raised ``AttributeError``.
  Fix: coerce to ``""`` at the encoder boundary.

Defect 5 — multimodal_encoder codegen None-content concat crash.
  ``content = doc.get("content", "") + " " + doc.get("title", "")`` raised
  ``TypeError`` (unsupported operand type(s) for +: 'NoneType' and 'str') on a
  present-but-None content/title.
  Fix: ``(doc.get("content") or "")`` at every concat site; coerce non-strings
  at the ``text_encoder`` boundary.

Defect 6 — cross_modal_retriever codegen None-query crash.
  The retriever's visual-term boost did ``query.lower()`` on the ``query``
  workflow input; a None query raised ``AttributeError``.
  Fix: ``(query if isinstance(query, str) else "").lower()``.

Defects 1 + 2 are ``run()``-path defects; defects 3-6 are
``_create_workflow()`` codegen-template defects.

All tests are behavioral — they call ``run()`` or exec the real rendered
codegen template against malformed input and assert success / typed outputs,
not source-grep.
"""

from __future__ import annotations

import numpy as np
import pytest

from kaizen.nodes.rag.multimodal import (
    ImageTextMatchingNode,
    MultimodalRAGNode,
    VisualQuestionAnsweringNode,
)

pytestmark = pytest.mark.regression


_VQA_KEYS = {
    "answer",
    "confidence",
    "image_caption",
    "detected_objects",
    "model_used",
    "image_path",
}
_ITM_KEYS = {"matches", "similarity_scores", "match_type", "model", "total_searched"}


# --------------------------------------------------------------------------
# Defect 1 — VisualQuestionAnsweringNode.run() None question
# --------------------------------------------------------------------------


def test_issue_f8b4_vqa_none_question_does_not_crash():
    """Defect 1: ``question=None`` must not raise AttributeError.

    Pre-fix ``question.lower()`` raised 'NoneType' object has no attribute
    'lower' — the kwargs.get default applies only to MISSING keys.
    """
    result = VisualQuestionAnsweringNode().run(image_path="x.png", question=None)
    assert set(result.keys()) == _VQA_KEYS


def test_issue_f8b4_vqa_missing_question_kwarg_does_not_crash():
    """Defect 1 sibling: an absent question kwarg defaults to '' cleanly."""
    result = VisualQuestionAnsweringNode().run(image_path="x.png")
    assert set(result.keys()) == _VQA_KEYS


# --------------------------------------------------------------------------
# Defect 2 — ImageTextMatchingNode.run() non-dict collection element
# --------------------------------------------------------------------------


def test_issue_f8b4_itm_non_dict_collection_element_is_skipped():
    """Defect 2: a non-dict collection element must be skipped, not crashed on.

    Pre-fix ``item.get("tags", ...)`` raised 'str'/'int' object has no
    attribute 'get'. Collections are arbitrary user input.
    """
    collection = ["bare-string", {"caption": "architecture diagram", "tags": []}, 99]
    result = ImageTextMatchingNode().run(query="architecture", collection=collection)
    assert set(result.keys()) == _ITM_KEYS
    # Only the single dict element is matchable.
    assert len(result["matches"]) == 1
    # total_searched reports how many were searched (the raw input length).
    assert result["total_searched"] == 3


def test_issue_f8b4_itm_all_non_dict_collection_returns_empty():
    """Defect 2 edge: an all-non-dict collection yields zero matches."""
    result = ImageTextMatchingNode().run(query="architecture", collection=[1, 2, 3])
    assert result["matches"] == []
    assert result["total_searched"] == 3


# --------------------------------------------------------------------------
# Codegen-template helper — see Tier-2a file for the no-return rationale.
# --------------------------------------------------------------------------


def _exec_codegen_fn(node_id, fn_name, extra_ns=None):
    """exec a MultimodalRAGNode codegen template and return its function.

    The codegen functions build a local ``result`` dict but never ``return``
    it; this helper appends ``return result`` so the function's logic is
    behaviorally observable. ``extra_ns`` injects free variables the template
    reads (e.g. the ``query`` workflow input of cross_modal_retriever).
    """
    workflow = MultimodalRAGNode()._create_workflow()  # type: ignore[attr-defined]
    code = workflow.nodes[node_id].config["code"]
    namespace: dict = {"np": np}
    if extra_ns:
        namespace.update(extra_ns)
    exec(code + "\n    return result\n", namespace)
    return namespace[fn_name]


# --------------------------------------------------------------------------
# Defect 3 — doc_preprocessor codegen non-dict / None-content
# --------------------------------------------------------------------------


def test_issue_f8b4_doc_preprocessor_non_dict_in_loop_body_is_skipped():
    """Defect 3a: a non-dict document is skipped by the loop-body guard.

    Pre-fix the loop's ``doc.get("type", "text")`` raised AttributeError.
    """
    fn = _exec_codegen_fn("doc_preprocessor", "preprocess_documents")
    result = fn(["not-a-dict", {"type": "text", "content": "real", "id": "t1"}])
    assert len(result["preprocessed_docs"]["text_documents"]) == 1


def test_issue_f8b4_doc_preprocessor_non_dict_in_stats_comprehension_is_skipped():
    """Defect 3b: a non-dict document is skipped by the stats-block
    ``multimodal_docs`` list comprehension.

    Pre-fix ``[d for d in documents if d.get("type") == "multimodal"]`` raised
    AttributeError even when the loop-body guard was already present — the
    comprehension iterated the RAW documents list. This is the third non-dict
    site in the doc_preprocessor template.
    """
    fn = _exec_codegen_fn("doc_preprocessor", "preprocess_documents")
    result = fn(["not-a-dict", 42, {"type": "multimodal", "content": "c", "id": "m1"}])
    stats = result["preprocessed_docs"]["stats"]
    assert stats["multimodal_docs"] == 1


def test_issue_f8b4_doc_preprocessor_none_content_coerced_to_empty():
    """Defect 3c: a present-but-None content is coerced to '' by the
    preprocessor (``doc.get("content") or ""``)."""
    fn = _exec_codegen_fn("doc_preprocessor", "preprocess_documents")
    result = fn([{"type": "text", "content": None, "id": "t1"}])
    assert result["preprocessed_docs"]["text_documents"][0]["content"] == ""


# --------------------------------------------------------------------------
# Defect 4 — multimodal_encoder codegen None image path
# --------------------------------------------------------------------------


def test_issue_f8b4_multimodal_encoder_none_image_path_does_not_crash():
    """Defect 4: a present-but-None image ``path`` must not crash
    ``image_encoder``'s ``.lower()``.

    Pre-fix this raised 'NoneType' object has no attribute 'lower'.
    """
    fn = _exec_codegen_fn("multimodal_encoder", "encode_multimodal")
    encoded = fn(
        text_docs=[],
        image_docs=[{"id": "i1", "path": None, "caption": "c"}],
        query="q",
        modality_analysis={},
    )
    assert len(encoded["encoded_data"]["image_embeddings"]) == 1


# --------------------------------------------------------------------------
# Defect 5 — multimodal_encoder codegen None content concat
# --------------------------------------------------------------------------


def test_issue_f8b4_multimodal_encoder_none_content_does_not_crash():
    """Defect 5: a present-but-None content/title must not crash the ``+``
    concatenation in the encoder's text-doc loop.

    Pre-fix this raised TypeError (unsupported operand type(s) for +:
    'NoneType' and 'str').
    """
    fn = _exec_codegen_fn("multimodal_encoder", "encode_multimodal")
    encoded = fn(
        text_docs=[{"id": "t1", "content": None, "title": None}],
        image_docs=[],
        query="q",
        modality_analysis={},
    )
    assert len(encoded["encoded_data"]["text_embeddings"]) == 1


def test_issue_f8b4_multimodal_encoder_none_caption_does_not_crash():
    """Defect 5 sibling: a present-but-None caption/ocr_text must not crash the
    image-doc text-content concatenation."""
    fn = _exec_codegen_fn("multimodal_encoder", "encode_multimodal")
    encoded = fn(
        text_docs=[],
        image_docs=[{"id": "i1", "path": "p.png", "caption": None, "ocr_text": None}],
        query="q",
        modality_analysis={},
    )
    assert len(encoded["encoded_data"]["image_embeddings"]) == 1


# --------------------------------------------------------------------------
# Defect 6 — cross_modal_retriever codegen None query
# --------------------------------------------------------------------------


def test_issue_f8b4_cross_modal_retriever_none_query_does_not_crash():
    """Defect 6: a None ``query`` workflow input must not crash the retriever's
    ``query.lower()`` visual-term boost.

    Pre-fix this raised 'NoneType' object has no attribute 'lower'.
    """
    fn = _exec_codegen_fn(
        "cross_modal_retriever", "retrieve_multimodal", extra_ns={"query": None}
    )
    encoded_data = {
        "query_embedding": [0.5] * 10,
        "text_embeddings": [],
        "image_embeddings": [
            {"id": "i1", "embedding": [0.5] * 10, "path": "p.png", "caption": "c"}
        ],
    }
    result = fn(encoded_data, {})
    assert len(result["retrieval_results"]["image_results"]) == 1
