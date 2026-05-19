"""Tier-1 unit coverage for the 3 ``kaizen.nodes.rag.multimodal`` nodes.

F8 shard B4. The value-anchor (verbatim from the workstream brief): "the RAG
capability the user chose to preserve is provably correct, not merely
importable."

The shipped default code path of ``VisualQuestionAnsweringNode`` and
``ImageTextMatchingNode`` is deterministic rule-based compute — there is NO LLM
key in the ``[rag]`` extra and neither node hard-requires one. ``run()`` is a
real simulated-VQA / similarity-scoring path. These tests exercise that real
path: no mocking of the VQA / matching core (there is nothing to mock).

``MultimodalRAGNode`` is a ``WorkflowNode``; its ``run()`` executes a
sub-workflow built by ``_create_workflow()``. Tier-1 covers its construction
and the graph SHAPE (node count, ``get_parameters``, ``to_dict``); the
``code=`` PythonCodeNode templates are exercised directly in the Tier-2a file.

One test per documented behavior; assertions are structural (output keys,
score ranges/ordering, list lengths, typed raises).
"""

from __future__ import annotations

import pytest

from kaizen.nodes.rag.multimodal import (
    ImageTextMatchingNode,
    MultimodalRAGNode,
    VisualQuestionAnsweringNode,
)

pytestmark = pytest.mark.unit


# ==========================================================================
# VisualQuestionAnsweringNode
# ==========================================================================

# The keys VQA.run() always returns. `image_path` echoes the documented input
# so the result truthfully reports which image the node was asked about.
_VQA_KEYS = {
    "answer",
    "confidence",
    "image_caption",
    "detected_objects",
    "model_used",
    "image_path",
}


class TestVisualQuestionAnsweringNode:
    """run() golden path + documented edge cases for VQA."""

    def test_run_what_components_question_detects_objects(self):
        """A 'what components' question routes to the components branch."""
        node = VisualQuestionAnsweringNode()
        result = node.run(
            image_path="architecture_diagram.png",
            question="What components are shown in this diagram?",
        )
        assert set(result.keys()) == _VQA_KEYS
        assert "interconnected components" in result["answer"]
        assert result["detected_objects"] == [
            "input_layer",
            "hidden_units",
            "output_layer",
            "connections",
        ]
        assert result["confidence"] == 0.85

    def test_run_how_many_question_routes_to_count_branch(self):
        """A 'how many' question routes to the 6-element count branch."""
        node = VisualQuestionAnsweringNode()
        result = node.run(image_path="x.png", question="How many elements are there?")
        assert len(result["detected_objects"]) == 6
        assert result["confidence"] == 0.85

    def test_run_unrecognized_question_uses_low_confidence_fallback(self):
        """A question matching no branch falls back to 0.7 confidence."""
        node = VisualQuestionAnsweringNode()
        result = node.run(image_path="x.png", question="Explain the philosophy here")
        assert result["confidence"] == 0.7
        assert result["detected_objects"] == []

    def test_run_caption_generated_when_captioning_enabled(self):
        """enable_captioning=True (default) produces a non-empty caption."""
        node = VisualQuestionAnsweringNode(enable_captioning=True)
        result = node.run(image_path="x.png", question="What components are shown?")
        assert result["image_caption"] != ""
        assert "components" in result["image_caption"]

    def test_run_caption_empty_when_captioning_disabled(self):
        """enable_captioning=False suppresses the caption."""
        node = VisualQuestionAnsweringNode(enable_captioning=False)
        result = node.run(image_path="x.png", question="What components are shown?")
        assert result["image_caption"] == ""

    def test_run_model_used_reflects_constructor_model(self):
        """model_used echoes the model passed at construction (from .env-free
        default — no hardcoded model string in the node)."""
        node = VisualQuestionAnsweringNode(model="custom-vqa-v2")
        result = node.run(image_path="x.png", question="What is shown?")
        assert result["model_used"] == "custom-vqa-v2"

    def test_run_echoes_image_path_in_result(self):
        """The result echoes the documented `image_path` input so it truthfully
        reports which image the node was asked about (the simulated VQA scores
        `question` only and cannot read pixels — but it must not silently drop
        a documented required input)."""
        node = VisualQuestionAnsweringNode()
        result = node.run(
            image_path="architecture_diagram.png",
            question="What components are shown?",
        )
        assert result["image_path"] == "architecture_diagram.png"

    def test_run_missing_question_kwarg_does_not_crash(self):
        """An absent question kwarg defaults to '' and routes to the fallback."""
        node = VisualQuestionAnsweringNode()
        result = node.run(image_path="x.png")
        assert set(result.keys()) == _VQA_KEYS
        assert result["confidence"] == 0.7

    def test_run_none_question_does_not_crash(self):
        """A present-but-None question is coerced to '' — no AttributeError.

        kwargs.get('question', '') would return None here (the default applies
        only to MISSING keys); the node coerces via `or ''`.
        """
        node = VisualQuestionAnsweringNode()
        result = node.run(image_path="x.png", question=None)
        assert set(result.keys()) == _VQA_KEYS

    def test_run_none_image_path_does_not_crash(self):
        """A present-but-None image_path is tolerated (image_path is never
        dereferenced as a string in run())."""
        node = VisualQuestionAnsweringNode()
        result = node.run(image_path=None, question="What components are shown?")
        assert set(result.keys()) == _VQA_KEYS

    def test_run_unicode_question_does_not_crash(self):
        """A unicode question is handled by the lower-cased keyword matcher."""
        node = VisualQuestionAnsweringNode()
        result = node.run(image_path="x.png", question="¿Qué se muestra aquí? 図を説明")
        assert set(result.keys()) == _VQA_KEYS

    def test_get_parameters_declares_required_image_and_question(self):
        """image_path and question are required; the rest are optional."""
        params = VisualQuestionAnsweringNode().get_parameters()
        assert params["image_path"].required is True
        assert params["question"].required is True
        assert params["model"].required is False
        assert params["enable_captioning"].required is False


# ==========================================================================
# ImageTextMatchingNode
# ==========================================================================

_ITM_KEYS = {
    "matches",
    "similarity_scores",
    "match_type",
    "model",
    "total_searched",
}

_COLLECTION = [
    {"caption": "neural network architecture", "tags": ["diagram", "ml"]},
    {"caption": "a photo of a cat", "tags": ["photo"]},
    {"caption": "transformer architecture overview", "tags": ["diagram"]},
    {"caption": "unrelated landscape image", "tags": ["photo"]},
]


class TestImageTextMatchingNode:
    """run() golden path + documented edge cases for image-text matching."""

    def test_run_text_query_returns_ranked_matches(self):
        """A text query returns matches sorted by descending score."""
        node = ImageTextMatchingNode()
        result = node.run(query="architecture diagram", collection=_COLLECTION, top_k=4)
        assert set(result.keys()) == _ITM_KEYS
        assert result["match_type"] == "text_to_image"
        scores = result["similarity_scores"]
        assert scores == sorted(scores, reverse=True)
        assert result["total_searched"] == 4

    def test_run_architecture_diagram_query_scores_diagram_highest(self):
        """'architecture' + a 'diagram'-tagged item yields the top 0.9 score."""
        node = ImageTextMatchingNode()
        result = node.run(query="architecture diagram", collection=_COLLECTION)
        assert result["similarity_scores"][0] == 0.9

    def test_run_top_k_bounds_result_length(self):
        """top_k caps the number of returned matches."""
        node = ImageTextMatchingNode()
        result = node.run(query="architecture", collection=_COLLECTION, top_k=2)
        assert len(result["matches"]) == 2
        assert len(result["similarity_scores"]) == 2

    def test_run_non_string_query_routes_to_image_to_text(self):
        """A non-str query (an image reference dict) selects image_to_text."""
        node = ImageTextMatchingNode()
        result = node.run(query={"image": "ref.png"}, collection=_COLLECTION)
        assert result["match_type"] == "image_to_text"
        assert all(s == 0.5 for s in result["similarity_scores"])

    def test_run_empty_collection_returns_empty_matches(self):
        """An empty collection yields empty matches, not a crash."""
        node = ImageTextMatchingNode()
        result = node.run(query="architecture", collection=[])
        assert result["matches"] == []
        assert result["similarity_scores"] == []
        assert result["total_searched"] == 0

    def test_run_missing_collection_kwarg_does_not_crash(self):
        """An absent collection kwarg defaults to an empty list."""
        node = ImageTextMatchingNode()
        result = node.run(query="architecture")
        assert result["matches"] == []

    def test_run_non_dict_collection_element_is_skipped(self):
        """A non-dict element in the collection is skipped, not crashed on.

        Collection elements are arbitrary user input; a bare string has no
        `.get`. total_searched still reports the raw collection length.
        """
        node = ImageTextMatchingNode()
        collection = ["not-a-dict", {"caption": "architecture diagram", "tags": []}, 42]
        result = node.run(query="architecture", collection=collection)
        # Only the one dict element is matchable.
        assert len(result["matches"]) == 1
        # total_searched reflects how many were *searched* (the raw input).
        assert result["total_searched"] == 3

    def test_run_doc_with_none_caption_does_not_crash(self):
        """A present-but-None caption is tolerated by the str() coercion."""
        node = ImageTextMatchingNode()
        collection = [{"caption": None, "tags": None}]
        result = node.run(query="architecture", collection=collection)
        assert set(result.keys()) == _ITM_KEYS
        assert len(result["matches"]) == 1

    def test_run_unicode_query_does_not_crash(self):
        """A unicode text query is lower-cased and matched without error."""
        node = ImageTextMatchingNode()
        result = node.run(query="アーキテクチャ 図", collection=_COLLECTION)
        assert set(result.keys()) == _ITM_KEYS
        assert result["match_type"] == "text_to_image"

    def test_run_model_reflects_constructor_matching_model(self):
        """The returned model echoes the matching_model from construction."""
        node = ImageTextMatchingNode(matching_model="align-v2")
        result = node.run(query="architecture", collection=_COLLECTION)
        assert result["model"] == "align-v2"

    def test_get_parameters_declares_required_query_and_collection(self):
        """query and collection are required; top_k is optional."""
        params = ImageTextMatchingNode().get_parameters()
        assert params["query"].required is True
        assert params["collection"].required is True
        assert params["top_k"].required is False


# ==========================================================================
# MultimodalRAGNode — construction + workflow graph shape
# ==========================================================================


class TestMultimodalRAGNodeConstruction:
    """MultimodalRAGNode is a WorkflowNode; Tier-1 covers construction + the
    sub-workflow graph SHAPE. The codegen code= templates are exercised
    directly in the Tier-2a integration file."""

    def test_constructs_with_defaults(self):
        """The node constructs and builds its sub-workflow with no arguments.

        Config attrs are read via ``node.config[...]`` — the ``@register_node``
        decorator type-erases the class to ``Node`` for the type checker, so a
        direct ``node.image_encoder`` access reports reportAttributeAccessIssue.
        """
        node = MultimodalRAGNode()
        assert node.config["image_encoder"] == "clip-base"
        assert node.config["enable_ocr"] is True
        assert node.config["fusion_strategy"] == "weighted"

    def test_constructs_with_custom_parameters(self):
        """Constructor parameters are stored in the node config."""
        node = MultimodalRAGNode(
            image_encoder="blip-large",
            enable_ocr=False,
            fusion_strategy="concat",
        )
        assert node.config["image_encoder"] == "blip-large"
        assert node.config["enable_ocr"] is False
        assert node.config["fusion_strategy"] == "concat"

    def test_create_workflow_builds_six_node_graph(self):
        """The multimodal RAG sub-workflow wires exactly six nodes:
        query_analyzer, doc_preprocessor, multimodal_encoder,
        cross_modal_retriever, response_generator, result_formatter."""
        node = MultimodalRAGNode()
        # _create_workflow is a private helper; the type checker cannot see
        # through the @register_node decorator's type erasure on the public
        # class, so the call site is explicitly ignored.
        workflow = node._create_workflow()  # type: ignore[attr-defined]
        assert set(workflow.nodes.keys()) == {
            "query_analyzer",
            "doc_preprocessor",
            "multimodal_encoder",
            "cross_modal_retriever",
            "response_generator",
            "result_formatter",
        }

    def test_get_parameters_returns_non_empty_mapping(self):
        """get_parameters exposes the wrapped sub-workflow's input surface."""
        params = MultimodalRAGNode().get_parameters()
        assert len(params) > 0

    def test_to_dict_exposes_wrapped_workflow(self):
        """to_dict serialises the node including its wrapped sub-workflow."""
        data = MultimodalRAGNode().to_dict()
        assert data["type"] == "MultimodalRAGNode"
        assert "wrapped_workflow" in data
